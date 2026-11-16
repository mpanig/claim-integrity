"""Aggregate AI answers into rates with confidence intervals (never single answers).

Per engine, live answers are used when that engine has any; otherwise its demo answers
(flagged), so a filled-in key replaces demo data engine by engine.
"""

import math
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.engines import ENGINES
from app.models import AiAnswer, Conflict, Persona, Sku
from app.services.trends import week_start


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion k/n, as (low, high) in 0..1."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def rate(k: int, n: int) -> dict[str, Any]:
    low, high = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "low": low, "high": high}


def select_answers(
    session: Session,
    *,
    engines: list[str] | None = None,
    regions: list[str] | None = None,
    persona_id: int | None = None,
    prompt_id: int | None = None,
    language: str | None = None,
    search: bool | None = None,
    sku_id: int | None = None,
) -> tuple[list[AiAnswer], list[dict[str, Any]]]:
    q = (
        select(AiAnswer)
        .options(selectinload(AiAnswer.mentions), selectinload(AiAnswer.claims), selectinload(AiAnswer.citations))
        .where(AiAnswer.engine.is_not(None), AiAnswer.error.is_(None))
    )
    if engines:
        q = q.where(AiAnswer.engine.in_(engines))
    if regions:
        q = q.where(AiAnswer.region.in_(regions))
    if persona_id is not None:  # 0 = answers asked without a persona
        q = q.where(AiAnswer.persona_id.is_(None)) if persona_id == 0 else q.where(AiAnswer.persona_id == persona_id)
    if prompt_id:
        q = q.where(AiAnswer.prompt_id == prompt_id)
    if language:
        q = q.where(AiAnswer.language == language)
    if search is not None:
        q = q.where(AiAnswer.search_enabled.is_(search))
    if sku_id:
        q = q.where(AiAnswer.sku_id == sku_id)
    rows = session.scalars(q.order_by(AiAnswer.asked_at)).all()
    chosen, modes = [], []
    for name, engine in ENGINES.items():
        live = [a for a in rows if a.engine == name and not a.is_demo]
        demo = [a for a in rows if a.engine == name and a.is_demo]
        use = live or demo
        chosen += use
        modes.append({"engine": name, "label": engine.label, "mode": "live" if live else ("demo" if demo else "none"), "answers": len(use)})
    return chosen, modes


def insights(session: Session, **filters: Any) -> dict[str, Any]:
    answers, modes = select_answers(session, **filters)
    n = len(answers)
    personas = {p.id: p.name for p in session.scalars(select(Persona))}
    names: dict[str, bool] = {}
    for a in answers:
        for m in a.mentions:
            names[m.name] = m.is_own

    def mentions_of(a: AiAnswer, name: str):
        return next((m for m in a.mentions if m.name == name), None)

    total_mentions = sum(len(a.mentions) for a in answers)
    brands = []
    for name, own in names.items():
        hits = [mentions_of(a, name) for a in answers]
        hits = [m for m in hits if m]
        positions = [m.position for m in hits if m.position]
        brands.append(
            {
                "name": name,
                "is_own": own,
                "mention": rate(len(hits), n),
                "recommended": rate(sum(1 for m in hits if m.recommended), n),
                "share_of_voice": round(len(hits) / total_mentions, 3) if total_mentions else 0,
                "avg_position": round(sum(positions) / len(positions), 2) if positions else None,
                "top3": rate(sum(1 for p in positions if p <= 3), n),
                "sentiment": round(sum(m.sentiment for m in hits) / len(hits), 2) if hits else None,
            }
        )
    brands.sort(key=lambda b: -b["share_of_voice"])

    # Heatmap: rows engine x region, columns persona; value per brand.
    cells: dict[tuple[str, str, str], list[AiAnswer]] = defaultdict(list)
    for a in answers:
        cells[(a.engine or "", a.region or "", personas.get(a.persona_id, "No persona") if a.persona_id else "No persona")].append(a)
    heatmap = []
    for (engine, region, persona), group in sorted(cells.items()):
        for name in names:
            hits = [mentions_of(a, name) for a in group]
            heatmap.append(
                {
                    "engine": engine,
                    "region": region,
                    "persona": persona,
                    "brand": name,
                    "mention": rate(sum(1 for m in hits if m), len(group)),
                    "recommended": rate(sum(1 for m in hits if m and m.recommended), len(group)),
                }
            )

    rank = []
    for name in names:
        dist = Counter()
        for a in answers:
            m = mentions_of(a, name)
            if m:
                dist["5+" if (m.position or 0) >= 5 else (str(m.position) if m.position else "unranked")] += 1
        rank.append({"brand": name, "positions": {k: dist.get(k, 0) for k in ("1", "2", "3", "4", "5+", "unranked")}})

    skus = {s.id: s.name for s in session.scalars(select(Sku))}
    conflict_labels = {}
    acc: dict[int, dict[str, Any]] = {}
    wrong_examples = []
    for a in answers:
        for c in a.claims:
            e = acc.setdefault(c.sku_id, {"sku_id": c.sku_id, "sku_name": skus.get(c.sku_id, ""), "claims": 0, "correct": 0, "by_verdict": Counter(), "echoes": Counter()})
            e["claims"] += 1
            if c.verdict is None:
                e["correct"] += 1
            else:
                e["by_verdict"][c.verdict] += 1
                for cid in c.echo_conflict_ids or []:
                    e["echoes"][cid] += 1
                if len(wrong_examples) < 40:
                    wrong_examples.append({"answer_id": a.id, "engine": a.engine, "region": a.region, "sku_name": skus.get(c.sku_id, ""), "field": c.field, "value": c.value, "verdict": c.verdict, "quote": c.quote, "echoes": c.echo_conflict_ids, "is_demo": a.is_demo})
    ids = {cid for e in acc.values() for cid in e["echoes"]}
    if ids:
        for k in session.scalars(select(Conflict).where(Conflict.id.in_(ids))):
            conflict_labels[k.id] = f"{k.page.retailer or k.page.url}: {k.field}"
    accuracy = [
        {
            **{k: v for k, v in e.items() if k not in ("by_verdict", "echoes")},
            "accuracy": rate(e["correct"], e["claims"]),
            "by_verdict": dict(e["by_verdict"]),
            "echoes": [{"conflict_id": cid, "label": conflict_labels.get(cid, str(cid)), "answers": cnt} for cid, cnt in e["echoes"].most_common()],
        }
        for e in acc.values()
    ]

    domains, pages, types = Counter(), Counter(), Counter()
    titles, dtype = {}, {}
    for a in answers:
        for c in a.citations:
            domains[c.domain] += 1
            pages[c.url] += 1
            types[c.page_type] += 1
            titles[c.url] = c.title
            dtype[c.domain] = c.page_type
    cited = sum(domains.values())

    weekly: dict[str, list[AiAnswer]] = defaultdict(list)
    for a in answers:
        weekly[week_start(a.asked_at.date()).isoformat()].append(a)
    trend = []
    for wk, group in sorted(weekly.items()):
        point: dict[str, Any] = {"week": wk, "answers": len(group)}
        for name, own in names.items():
            if own:
                hits = [mentions_of(a, name) for a in group]
                point[name] = rate(sum(1 for m in hits if m), len(group))["rate"]
        trend.append(point)

    return {
        "answers": n,
        "engines": modes,
        "demo": any(a.is_demo for a in answers),
        "brands": brands,
        "heatmap": heatmap,
        "rank": rank,
        "accuracy": accuracy,
        "wrong_claims": wrong_examples,
        "citations": {
            "total": cited,
            "domains": [{"domain": d, "page_type": dtype[d], "count": c, "share": round(c / cited, 3)} for d, c in domains.most_common(15)],
            "pages": [{"url": u, "title": titles[u], "count": c} for u, c in pages.most_common(15)],
            "by_type": dict(types),
        },
        "trend": trend,
    }
