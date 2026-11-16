"""Test plans: which questions to ask, of which engines, under which conditions.

A plan expands to cells:
  prompts x wording variants x engines x models x search on/off x regions x languages
  x personas x samples
Engines without a key are skipped (listed in the estimate) and cost nothing.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.engines import ENGINES, Engine, Location
from app.models import AiPrompt, Persona, PromptVariant, Sku

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "ja": "Japanese"}
COUNTRY_NAMES = {"US": "the United States", "IN": "India", "GB": "the United Kingdom", "CA": "Canada", "AU": "Australia", "DE": "Germany", "FR": "France"}

# Rough token sizes per call, for estimates only. Web search adds retrieved pages to the input.
EST_INPUT_TOKENS = 250
EST_SEARCH_INPUT_TOKENS = 4000
EST_OUTPUT_TOKENS = 700


class EngineChoice(BaseModel):
    engine: str
    models: list[str] = Field(min_length=1)

    @field_validator("engine")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in ENGINES:
            raise ValueError(f"unknown engine {v!r}; expected one of {', '.join(ENGINES)}")
        return v


class RegionChoice(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    city: str | None = None
    languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1)


class PlanConfig(BaseModel):
    prompt_ids: list[int] = Field(min_length=1)
    engines: list[EngineChoice] = Field(min_length=1)
    search_modes: list[bool] = Field(default_factory=lambda: [True], min_length=1)
    regions: list[RegionChoice] = Field(min_length=1)
    persona_ids: list[int | None] = Field(default_factory=lambda: [None], min_length=1)  # None = no persona
    variants: str = "all"  # all | first
    samples: int = Field(default=3, ge=1, le=10)


@dataclass
class Cell:
    prompt: AiPrompt
    variant: PromptVariant | None
    template: str
    engine: Engine
    model: str
    search: bool
    region: RegionChoice
    language: str
    persona: Persona | None
    sample: int

    @property
    def location(self) -> Location:
        return Location(country=self.region.country.upper(), city=self.region.city)


def expand(session: Session, cfg: PlanConfig) -> list[Cell]:
    prompts = session.scalars(
        select(AiPrompt).options(selectinload(AiPrompt.variants)).where(AiPrompt.id.in_(cfg.prompt_ids)).order_by(AiPrompt.id)
    ).all()
    personas = {p.id: p for p in session.scalars(select(Persona).where(Persona.id.in_([p for p in cfg.persona_ids if p])))}
    cells: list[Cell] = []
    for prompt in prompts:
        for choice in cfg.engines:
            engine = ENGINES[choice.engine]
            modes = cfg.search_modes if engine.search_toggle else [True]
            for model in choice.models:
                for search in dict.fromkeys(modes):
                    for region in cfg.regions:
                        for language in region.languages:
                            for template, variant in wordings(prompt, language, cfg.variants):
                                for pid in cfg.persona_ids:
                                    persona = personas.get(pid) if pid else None
                                    if pid and persona is None:
                                        continue
                                    for sample in range(1, cfg.samples + 1):
                                        cells.append(Cell(prompt, variant, template, engine, model, search, region, language, persona, sample))
    return cells


def wordings(prompt: AiPrompt, language: str, mode: str) -> list[tuple[str, PromptVariant | None]]:
    """Wordings in the requested language; fall back to English plus an 'answer in X' line."""
    same = [(v.text, v) for v in prompt.variants if v.language == language]
    if language == "en":
        same = [(prompt.text, None), *same]
    if not same:
        english = [(prompt.text, None), *[(v.text, v) for v in prompt.variants if v.language == "en"]]
        lang = LANGUAGE_NAMES.get(language, language)
        same = [(f"{t}\n\nPlease answer in {lang}.", v) for t, v in english]
    return same[:1] if mode == "first" else same


def render(session: Session, cell: Cell) -> str:
    """The exact text sent: persona context, the question, and the region when the API can't take it."""
    p = cell.prompt
    sku = session.get(Sku, p.sku_id) if p.sku_id else None
    values = {
        "brand": sku.brand.name if sku else "",
        "product": sku.name if sku else "",
        "category": p.category or (sku.line if sku and sku.line else "cleanser"),
        "competitor": p.competitor or "",
        "retailer": p.retailer or "",
        "city": cell.region.city or COUNTRY_NAMES.get(cell.region.country.upper(), cell.region.country),
        "country": COUNTRY_NAMES.get(cell.region.country.upper(), cell.region.country),
    }
    question = cell.template
    for key, value in values.items():
        question = question.replace("{" + key + "}", value)
    parts = []
    if cell.persona:
        parts.append(cell.persona.context.strip())
    if cell.engine.location_mode(cell.search, cell.location) == "prompt-only":
        where = f"{cell.region.city}, " if cell.region.city else ""
        parts.append(f"I'm in {where}{values['country']}.")
    parts.append(question.strip())
    return " ".join(parts)


def estimate(session: Session, cfg: PlanConfig, env: dict[str, str]) -> dict[str, Any]:
    cells = expand(session, cfg)
    by_engine: dict[str, dict[str, Any]] = {}
    for c in cells:
        e = by_engine.setdefault(
            c.engine.name,
            {"engine": c.engine.name, "label": c.engine.label, "status": c.engine.status(env), "calls": 0, "est_usd": 0.0},
        )
        e["calls"] += 1
        p = c.engine.price(c.model)
        tokens_in = EST_INPUT_TOKENS + (EST_SEARCH_INPUT_TOKENS if c.search else 0)
        e["est_usd"] += tokens_in / 1e6 * p.input_per_mtok + EST_OUTPUT_TOKENS / 1e6 * p.output_per_mtok + (p.per_search if c.search else 0)
    engines = list(by_engine.values())
    for e in engines:
        e["est_usd"] = round(e["est_usd"], 2)
    live = [e for e in engines if e["status"] == "live"]
    return {
        "cells": len(cells),
        "runnable_calls": sum(e["calls"] for e in live),
        "est_usd": round(sum(e["est_usd"] for e in live), 2),
        "est_usd_all_engines": round(sum(e["est_usd"] for e in engines), 2),
        "engines": engines,
        "note": "Approximate: list prices and typical token counts. Web search adds retrieved pages to the input.",
    }
