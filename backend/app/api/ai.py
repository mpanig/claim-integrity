"""AI answer engine API: engines, prompt library, test plans, runs, insights, answers."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.ai.discovery import discover
from app.ai.engines import ENGINES, engine_env
from app.ai.insights import insights, select_answers
from app.ai.plan import LANGUAGE_NAMES, PlanConfig, estimate
from app.ai.planned import planned
from app.ai.runner import execute
from app.ai.perception import ATTRIBUTES, perception
from app.ai.score import aeo_score
from app.api.common import DB, get_or_404
from app.db import SessionLocal
from app.models import (
    AiAnswer,
    AiPrompt,
    AiRun,
    Brand,
    Competitor,
    Organisation,
    Persona,
    PromptVariant,
    RunConfig,
    Sku,
)

router = APIRouter(prefix="/ai")

INTENTS = ["category", "problem", "attribute", "versus", "where_to_buy"]
STAGES = ["awareness", "consideration", "purchase"]


def _org_id(session) -> int:
    # TODO(auth): the signed-in user's organisation.
    org_id = session.scalar(select(Organisation.id).order_by(Organisation.id))
    if org_id is None:
        raise HTTPException(409, "add a product first")
    return org_id


# ---------------------------------------------------------------------------- engines


@router.get("/engines/planned")
def planned_engines() -> list[dict[str, Any]]:
    """Engines planned but not connected yet, and the key that will switch each on (never the key itself)."""
    return planned()


@router.get("/engines")
def engines() -> list[dict[str, Any]]:
    """Each engine's status. Shows whether a key is set, never the key."""
    env = engine_env()
    return [
        {
            "engine": e.name,
            "label": e.label,
            "env_key": e.env_key,
            "status": e.status(env),
            "default_models": list(e.default_models),
            "search": "toggle" if e.search_toggle else "always",
            "location": "api with web search" if e.location_in_api else "prompt only",
        }
        for e in ENGINES.values()
    ]


# ---------------------------------------------------------------------------- library


class PromptIn(BaseModel):
    text: str = Field(min_length=5, max_length=1000)
    intent: str = "category"
    funnel_stage: str = "consideration"
    sku_id: int | None = None
    category: str | None = None
    competitor: str | None = None


class VariantIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    language: str = Field(default="en", min_length=2, max_length=10)


class PersonaIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    context: str = Field(min_length=5, max_length=1000)


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = []


class AliasesIn(BaseModel):
    brand_id: int | None = None
    sku_id: int | None = None
    aliases: list[str]


@router.get("/library")
def library(session: DB) -> dict[str, Any]:
    prompts = session.scalars(select(AiPrompt).options(selectinload(AiPrompt.variants)).order_by(AiPrompt.id)).all()
    skus = {s.id: s for s in session.scalars(select(Sku))}
    return {
        "intents": INTENTS,
        "funnel_stages": STAGES,
        "languages": LANGUAGE_NAMES,
        "prompts": [
            {
                "id": p.id, "text": p.text, "intent": p.intent, "funnel_stage": p.funnel_stage, "category": p.category,
                "competitor": p.competitor, "sku_id": p.sku_id, "sku_name": skus[p.sku_id].name if p.sku_id in skus else None,
                "variants": [{"id": v.id, "language": v.language, "text": v.text} for v in p.variants],
            }
            for p in prompts
        ],
        "personas": [{"id": p.id, "name": p.name, "context": p.context} for p in session.scalars(select(Persona).order_by(Persona.id))],
        "competitors": [{"id": c.id, "name": c.name, "aliases": c.aliases} for c in session.scalars(select(Competitor).order_by(Competitor.name))],
        "brands": [{"id": b.id, "name": b.name, "aliases": b.aliases} for b in session.scalars(select(Brand).order_by(Brand.name))],
        "skus": [{"id": s.id, "name": s.name, "aliases": s.aliases} for s in skus.values()],
    }


@router.post("/prompts", status_code=201)
def add_prompt(body: PromptIn, session: DB) -> dict[str, Any]:
    if body.intent not in INTENTS or body.funnel_stage not in STAGES:
        raise HTTPException(422, f"intent must be one of {INTENTS}; funnel_stage one of {STAGES}")
    sku = get_or_404(session, Sku, body.sku_id, "SKU") if body.sku_id else None
    p = AiPrompt(
        organisation_id=sku.organisation_id if sku else _org_id(session), sku_id=sku.id if sku else None,
        brand_id=sku.brand_id if sku else None, text=body.text.strip(), intent=body.intent,
        funnel_stage=body.funnel_stage, category=body.category, competitor=body.competitor,
    )
    session.add(p)
    session.commit()
    return {"id": p.id}


@router.delete("/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, AiPrompt, prompt_id, "prompt"))
    session.commit()
    return Response(status_code=204)


@router.post("/prompts/{prompt_id}/variants", status_code=201)
def add_variant(prompt_id: int, body: VariantIn, session: DB) -> dict[str, Any]:
    get_or_404(session, AiPrompt, prompt_id, "prompt")
    v = PromptVariant(prompt_id=prompt_id, language=body.language, text=body.text.strip())
    session.add(v)
    session.commit()
    return {"id": v.id}


@router.delete("/variants/{variant_id}", status_code=204)
def delete_variant(variant_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, PromptVariant, variant_id, "variant"))
    session.commit()
    return Response(status_code=204)


@router.post("/personas", status_code=201)
def add_persona(body: PersonaIn, session: DB) -> dict[str, Any]:
    p = Persona(organisation_id=_org_id(session), name=body.name.strip(), context=body.context.strip())
    session.add(p)
    session.commit()
    return {"id": p.id}


@router.delete("/personas/{persona_id}", status_code=204)
def delete_persona(persona_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, Persona, persona_id, "persona"))
    session.commit()
    return Response(status_code=204)


@router.post("/competitors", status_code=201)
def add_competitor(body: CompetitorIn, session: DB) -> dict[str, Any]:
    c = Competitor(organisation_id=_org_id(session), name=body.name.strip(), aliases=[a.strip() for a in body.aliases if a.strip()] or [body.name.strip()])
    session.add(c)
    session.commit()
    return {"id": c.id}


@router.delete("/competitors/{competitor_id}", status_code=204)
def delete_competitor(competitor_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, Competitor, competitor_id, "competitor"))
    session.commit()
    return Response(status_code=204)


@router.put("/aliases")
def set_aliases(body: AliasesIn, session: DB) -> dict[str, Any]:
    if (body.brand_id is None) == (body.sku_id is None):
        raise HTTPException(422, "give exactly one of brand_id or sku_id")
    target = get_or_404(session, Brand, body.brand_id, "brand") if body.brand_id else get_or_404(session, Sku, body.sku_id, "SKU")
    target.aliases = [a.strip() for a in body.aliases if a.strip()]
    session.commit()
    return {"aliases": target.aliases}


# ---------------------------------------------------------------------------- plans and runs


class RunIn(BaseModel):
    config: dict[str, Any]
    budget_usd: float = Field(default=5.0, gt=0, le=1000)
    run_config_id: int | None = None


class ConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any]
    budget_usd: float = Field(default=5.0, gt=0, le=1000)
    schedule: str = "none"


def _plan(config: dict[str, Any]) -> PlanConfig:
    try:
        return PlanConfig.model_validate(config)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from e


@router.get("/configs")
def list_configs(session: DB) -> list[dict[str, Any]]:
    return [
        {"id": c.id, "name": c.name, "config": c.config, "budget_usd": c.budget_usd, "schedule": c.schedule, "last_run_at": c.last_run_at}
        for c in session.scalars(select(RunConfig).order_by(RunConfig.id))
    ]


@router.post("/configs", status_code=201)
def save_config(body: ConfigIn, session: DB) -> dict[str, Any]:
    if body.schedule not in ("none", "daily", "weekly"):
        raise HTTPException(422, "schedule must be none, daily or weekly")
    cfg = _plan(body.config)
    c = RunConfig(organisation_id=_org_id(session), name=body.name, config=cfg.model_dump(), budget_usd=body.budget_usd, schedule=body.schedule)
    session.add(c)
    session.commit()
    return {"id": c.id}


@router.post("/estimate")
def estimate_plan(body: RunIn, session: DB) -> dict[str, Any]:
    return estimate(session, _plan(body.config), engine_env())


def _run_in_background(run_id: int) -> None:
    with SessionLocal() as s:
        execute(s, s.get(AiRun, run_id))


@router.post("/runs", status_code=202)
def start_run(body: RunIn, background: BackgroundTasks, session: DB) -> dict[str, Any]:
    cfg = _plan(body.config)
    est = estimate(session, cfg, engine_env())
    if est["runnable_calls"] == 0:
        raise HTTPException(409, "No engine in this plan has an API key. Add a key in backend/.env (see Data sources).")
    run = AiRun(
        organisation_id=_org_id(session), run_config_id=body.run_config_id, config=cfg.model_dump(),
        budget_usd=body.budget_usd, est_cost_usd=est["est_usd"], planned_calls=est["runnable_calls"],
    )
    session.add(run)
    session.commit()
    background.add_task(_run_in_background, run.id)
    return {"id": run.id, "estimate": est}


def _run_out(r: AiRun) -> dict[str, Any]:
    return {
        "id": r.id, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
        "planned_calls": r.planned_calls, "done_calls": r.done_calls, "skipped": r.skipped, "errors": r.errors[-20:],
        "budget_usd": r.budget_usd, "est_cost_usd": r.est_cost_usd, "cost_usd": r.cost_usd, "analyser": r.analyser,
        "is_demo": r.is_demo, "run_config_id": r.run_config_id,
    }


@router.get("/runs")
def list_runs(session: DB, limit: int = 20) -> list[dict[str, Any]]:
    return [_run_out(r) for r in session.scalars(select(AiRun).order_by(AiRun.id.desc()).limit(limit))]


@router.get("/runs/{run_id}")
def get_run(run_id: int, session: DB) -> dict[str, Any]:
    return _run_out(get_or_404(session, AiRun, run_id, "run"))


# ---------------------------------------------------------------------------- results


def _filters(engine, region, persona_id, prompt_id, language, search, sku_id) -> dict[str, Any]:
    return {
        "engines": engine or None, "regions": region or None, "persona_id": persona_id, "prompt_id": prompt_id,
        "language": language, "search": search, "sku_id": sku_id,
    }


@router.get("/insights")
def get_insights(
    session: DB,
    engine: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    persona_id: int | None = None,
    prompt_id: int | None = None,
    language: str | None = None,
    search: bool | None = None,
    sku_id: int | None = None,
) -> dict[str, Any]:
    return insights(session, **_filters(engine, region, persona_id, prompt_id, language, search, sku_id))


@router.get("/score")
def get_score(
    session: DB,
    engine: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    persona_id: int | None = None,
    prompt_id: int | None = None,
    language: str | None = None,
    search: bool | None = None,
    sku_id: int | None = None,
) -> dict[str, Any]:
    """AEO score per brand, per brand x engine, weekly trend; prominence and word share."""
    return aeo_score(session, **_filters(engine, region, persona_id, prompt_id, language, search, sku_id))


@router.get("/perception")
def get_perception(
    session: DB,
    engine: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    persona_id: int | None = None,
    prompt_id: int | None = None,
    language: str | None = None,
    search: bool | None = None,
    sku_id: int | None = None,
) -> dict[str, Any]:
    """Attributes AI answers attach to each brand, vs each own brand's intended positioning."""
    return perception(session, **_filters(engine, region, persona_id, prompt_id, language, search, sku_id))


class PositioningIn(BaseModel):
    attributes: list[str] = Field(max_length=len(ATTRIBUTES))


@router.put("/brands/{brand_id}/positioning")
def set_positioning(brand_id: int, body: PositioningIn, session: DB) -> dict[str, Any]:
    """Intended positioning: the attributes this brand wants AI answers to associate with it."""
    brand = get_or_404(session, Brand, brand_id, "Brand")
    unknown = [a for a in body.attributes if a not in ATTRIBUTES]
    if unknown:
        raise HTTPException(422, f"Unknown attributes: {', '.join(unknown)}")
    brand.positioning = list(dict.fromkeys(body.attributes))
    session.commit()
    return {"brand_id": brand.id, "positioning": brand.positioning}


def _answer_brief(a: AiAnswer, personas: dict[int, str]) -> dict[str, Any]:
    return {
        "id": a.id, "prompt_id": a.prompt_id, "engine": a.engine, "model_requested": a.model_requested,
        "model_version": a.model_version, "search_enabled": a.search_enabled, "region": a.region, "city": a.city,
        "language": a.language, "location_mode": a.location_mode, "persona": personas.get(a.persona_id) if a.persona_id else None,
        "sample_index": a.sample_index, "asked_at": a.asked_at, "is_demo": a.is_demo, "analyser": a.analyser,
        "excerpt": a.answer[:240], "mentions": [m.name for m in a.mentions],
        "wrong_claims": sum(1 for c in a.claims if c.verdict), "citations": len(a.citations),
    }


@router.get("/answers")
def list_answers(
    session: DB,
    engine: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    persona_id: int | None = None,
    prompt_id: int | None = None,
    language: str | None = None,
    search: bool | None = None,
    sku_id: int | None = None,
    brand: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    answers, modes = select_answers(session, **_filters(engine, region, persona_id, prompt_id, language, search, sku_id))
    if brand:
        answers = [a for a in answers if any(m.name.lower() == brand.lower() for m in a.mentions)]
    answers.sort(key=lambda a: a.asked_at, reverse=True)
    personas = {p.id: p.name for p in session.scalars(select(Persona))}
    return {"total": len(answers), "engines": modes, "items": [_answer_brief(a, personas) for a in answers[offset : offset + limit]]}


@router.get("/answers/{answer_id}")
def get_answer(answer_id: int, session: DB) -> dict[str, Any]:
    a = get_or_404(session, AiAnswer, answer_id, "answer")
    personas = {p.id: p.name for p in session.scalars(select(Persona))}
    skus = {s.id: s.name for s in session.scalars(select(Sku))}
    return {
        **_answer_brief(a, personas),
        "prompt_text": a.prompt_text,
        "prompt": a.prompt.text,
        "answer": a.answer,
        "latency_ms": a.latency_ms,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
        "cost_usd": a.cost_usd,
        "temperature": a.temperature,
        "mentions_detail": [
            {"name": m.name, "is_own": m.is_own, "position": m.position, "recommended": m.recommended, "sentiment": m.sentiment, "quote": m.quote}
            for m in sorted(a.mentions, key=lambda m: (m.position or 99, m.name))
        ],
        "claims": [
            {"sku_name": skus.get(c.sku_id), "field": c.field, "value": c.value, "quote": c.quote, "verdict": c.verdict, "severity": c.severity, "echo_conflict_ids": c.echo_conflict_ids}
            for c in a.claims
        ],
        "citations_detail": [{"url": c.url, "domain": c.domain, "title": c.title, "page_type": c.page_type} for c in a.citations],
    }


@router.get("/summary")
def summary(session: DB) -> dict[str, Any]:
    """Counts for the overview header."""
    live = session.scalar(select(func.count()).select_from(AiAnswer).where(AiAnswer.engine.is_not(None), AiAnswer.is_demo.is_(False)))
    demo = session.scalar(select(func.count()).select_from(AiAnswer).where(AiAnswer.engine.is_not(None), AiAnswer.is_demo.is_(True)))
    return {"live_answers": live, "demo_answers": demo, "prompts": session.scalar(select(func.count()).select_from(AiPrompt))}


@router.get("/discovery")
def get_discovery(session: DB, llm: bool = False) -> dict[str, Any]:
    """Questions the library doesn't test yet, with an estimated importance and reasons.
    llm=true also asks Claude for more (needs ANTHROPIC_API_KEY; costs a little per call)."""
    return discover(session, llm=llm)
