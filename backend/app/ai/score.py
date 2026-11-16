"""AEO score: one 0-100 number per brand (and per brand x engine) from AI answers.

Components, each 0..1, averaged over all answers in scope (an answer that doesn't name the
brand counts as 0):

  mention      the answer names the brand
  recommended  the answer recommends it
  prominence   how early it is first named: 1 at the very start, 0 at the very end
  word_share   share of brand-related words that are about this brand (sentences that name
               several brands are split between them)
  sentiment    (sentiment + 1) / 2 when named, so -1..1 becomes 0..1

score = 100 x sum(weight x component). Weights are in WEIGHTS and returned with the result.
Uses the same answer selection as insights (real answers per engine once its key is set).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.analyse import Entity, load_entities
from app.ai.engines import ENGINES
from app.ai.insights import select_answers
from app.models import AiAnswer, Organisation
from app.services.trends import week_start

WEIGHTS = {"mention": 0.35, "recommended": 0.25, "prominence": 0.20, "word_share": 0.10, "sentiment": 0.10}
SENTENCE = re.compile(r"(?<=[.!?।])\s+|\n+")


@dataclass
class Tally:
    answers: int = 0
    mentioned: int = 0
    recommended: int = 0
    first_named: int = 0  # the first brand the answer names
    prominence: float = 0.0
    offsets: list[float] = field(default_factory=list)
    words: float = 0.0
    sentiment: float = 0.0

    def add(self, other: "Tally") -> None:
        self.answers += other.answers
        self.mentioned += other.mentioned
        self.recommended += other.recommended
        self.first_named += other.first_named
        self.prominence += other.prominence
        self.offsets += other.offsets
        self.words += other.words
        self.sentiment += other.sentiment


def _scan(a: AiAnswer, entities: list[Entity], patterns: dict[str, re.Pattern[str]]) -> dict[str, Tally]:
    """Per brand, this answer's contribution."""
    text = a.answer or ""
    length = max(len(text), 1)
    by_name = {m.name: m for m in a.mentions}
    out: dict[str, Tally] = {}
    first: dict[str, int] = {}
    for e in entities:
        t = Tally(answers=1)
        m = by_name.get(e.name)
        hit = patterns[e.name].search(text)
        if m or hit:
            t.mentioned = 1
            t.recommended = 1 if (m and m.recommended) else 0
            offset = hit.start() / length if hit else 1.0
            first[e.name] = hit.start() if hit else length
            t.prominence = 1 - offset
            t.offsets.append(offset)
            t.sentiment = ((m.sentiment if m else 0.0) + 1) / 2
        out[e.name] = t
    if first:
        out[min(first, key=first.get)].first_named = 1
    # Word share: sentences naming brands, words split between the brands named.
    for sentence in SENTENCE.split(text):
        named = [e.name for e in entities if e.name in first and patterns[e.name].search(sentence)]
        if named:
            words = len(sentence.split()) / len(named)
            for n in named:
                out[n].words += words
    return out


def _summary(name: str, is_own: bool, t: Tally, total_words: float) -> dict[str, Any]:
    n = t.answers or 1
    comp = {
        "mention": t.mentioned / n,
        "recommended": t.recommended / n,
        "prominence": t.prominence / n,
        "word_share": t.words / total_words if total_words else 0.0,
        "sentiment": t.sentiment / n,
    }
    score = 100 * sum(WEIGHTS[k] * v for k, v in comp.items())
    return {
        "name": name,
        "is_own": is_own,
        "score": round(score, 1),
        "components": {k: round(v, 3) for k, v in comp.items()},
        "answers": t.answers,
        "first_named": round(t.first_named / n, 3),
        "first_offset": round(sum(t.offsets) / len(t.offsets), 3) if t.offsets else None,
        "word_share": round(comp["word_share"], 3),
    }


def _scores(entities: list[Entity], tallies: dict[str, Tally]) -> list[dict[str, Any]]:
    total_words = sum(t.words for t in tallies.values())
    rows = [_summary(e.name, e.is_own, tallies.get(e.name, Tally()), total_words) for e in entities]
    return sorted(rows, key=lambda r: -r["score"])


def aeo_score(session: Session, **filters: Any) -> dict[str, Any]:
    answers, modes = select_answers(session, **filters)
    org = session.scalars(select(Organisation)).first()
    entities = load_entities(session, org.id)[0] if org else []
    patterns = {e.name: e.pattern() for e in entities}

    overall: dict[str, Tally] = defaultdict(Tally)
    per_engine: dict[str, dict[str, Tally]] = defaultdict(lambda: defaultdict(Tally))
    per_week: dict[str, dict[str, Tally]] = defaultdict(lambda: defaultdict(Tally))
    for a in answers:
        week = week_start(a.asked_at.date()).isoformat()
        for name, t in _scan(a, entities, patterns).items():
            overall[name].add(t)
            per_engine[a.engine or ""][name].add(t)
            per_week[week][name].add(t)

    brands = _scores(entities, overall) if answers else []
    trend = []
    for week, tallies in sorted(per_week.items()):
        point: dict[str, Any] = {"week": week, "answers": next(iter(tallies.values())).answers}
        for row in _scores(entities, tallies):
            point[row["name"]] = row["score"]
        trend.append(point)
    # Change: latest week vs the one before it.
    if len(trend) >= 2:
        for b in brands:
            b["change"] = round(trend[-1][b["name"]] - trend[-2][b["name"]], 1)
    labels = {k: e.label for k, e in ENGINES.items()}
    by_engine = [
        {"engine": eng, "label": labels.get(eng, eng), "brands": _scores(entities, tallies)}
        for eng, tallies in sorted(per_engine.items())
    ]
    own = [b for b in brands if b["is_own"]]
    rivals = [b for b in brands if not b["is_own"]]
    return {
        "answers": len(answers),
        "engines": modes,
        "demo": any(a.is_demo for a in answers),
        "weights": WEIGHTS,
        "brands": brands,
        "by_engine": by_engine,
        "trend": trend,
        "leader": brands[0]["name"] if brands else None,
        "best_own": own[0] if own else None,
        "top_rival": rivals[0] if rivals else None,
    }
