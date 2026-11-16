"""AEO alerts: compare the latest week of AI answers with the week before.

  aeo_score_drop           one of our brands' AEO score fell SCORE_DROP+ points (or ENGINE_DROP+ on one engine)
  aeo_overtaken            a competitor's AEO score moved above one of our brands (overall or on an engine)
  aeo_lost_recommendation  on a top prompt (best-of or problem-led), our brand's recommendation rate fell by
                           LOST_REC or more from at least REC_FLOOR
  aeo_wrong_fact           a wrong product fact that no earlier answer stated

Uses the same answers as the rest of AEO / GEO (per engine: real answers once its key is set,
otherwise demo). Alerts from demo answers are flagged and replaced on every evaluation; real
ones are de-duplicated by key (one per condition per week).
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.analyse import load_entities
from app.ai.engines import ENGINES
from app.ai.insights import select_answers
from app.ai.score import Tally, _scan, _scores
from app.models import AiPrompt, Alert, Brand, Organisation, Sku
from app.services.trends import week_start

SCORE_DROP, ENGINE_DROP = 3.0, 5.0
LOST_REC, REC_FLOOR = 0.2, 0.3
MIN_ANSWERS = 20  # per engine-week, before engine-level alerts fire
MIN_PROMPT = 5  # answers per prompt-week
TOP_INTENTS = ("category", "problem")


def evaluate(session: Session, *, env: dict[str, str] | None = None) -> list[Alert]:
    org = session.scalars(select(Organisation)).first()
    session.execute(delete(Alert).where(Alert.is_demo.is_(True), Alert.kind.like("aeo_%")))
    session.commit()
    if org is None:
        return []
    answers, _modes = select_answers(session, env=env)
    weeks = sorted({week_start(a.asked_at.date()) for a in answers})
    if len(weeks) < 2:
        return []
    cur, prev = weeks[-1], weeks[-2]
    demo = any(a.is_demo for a in answers if week_start(a.asked_at.date()) in (cur, prev))
    entities = load_entities(session, org.id)[0]
    patterns = {e.name: e.pattern() for e in entities}
    own = [e for e in entities if e.is_own]
    rivals = [e for e in entities if not e.is_own]
    brand_ids = {b.name: b.id for b in session.scalars(select(Brand))}
    labels = {k: e.label for k, e in ENGINES.items()}

    tallies: dict[tuple[Any, str], dict[str, Tally]] = defaultdict(lambda: defaultdict(Tally))
    counts: dict[tuple[Any, str], int] = defaultdict(int)
    rec: dict[tuple[Any, int, str], list[int]] = defaultdict(lambda: [0, 0])  # (week, prompt, brand) -> [recommended, answers]
    for a in answers:
        wk = week_start(a.asked_at.date())
        if wk not in (cur, prev):
            continue
        scan = _scan(a, entities, patterns)
        for scope in ("all", a.engine or ""):
            counts[(wk, scope)] += 1
            for name, t in scan.items():
                tallies[(wk, scope)][name].add(t)
        for e in own:
            r = rec[(wk, a.prompt_id, e.name)]
            r[1] += 1
            r[0] += 1 if any(m.name == e.name and m.recommended for m in a.mentions) else 0

    def scores(wk, scope) -> dict[str, float]:
        return {r["name"]: r["score"] for r in _scores(entities, tallies[(wk, scope)])}

    found: list[dict[str, Any]] = []
    scopes = ["all", *sorted({a.engine for a in answers if a.engine})]
    for scope in scopes:
        if scope != "all" and min(counts[(cur, scope)], counts[(prev, scope)]) < MIN_ANSWERS:
            continue
        now_s, was_s = scores(cur, scope), scores(prev, scope)
        where = "across engines" if scope == "all" else f"on {labels.get(scope, scope)}"
        for e in own:
            drop = was_s.get(e.name, 0) - now_s.get(e.name, 0)
            if drop >= (SCORE_DROP if scope == "all" else ENGINE_DROP):
                found.append({"kind": "aeo_score_drop", "brand": e.name, "key": f"{scope}",
                              "title": f"{e.name}'s AEO score fell {drop:.1f} points {where}",
                              "body": f"{was_s[e.name]:.1f} → {now_s[e.name]:.1f} week on week.", "link": "/aeo"})
            for r in rivals:
                if was_s.get(e.name, 0) >= was_s.get(r.name, 0) and now_s.get(r.name, 0) > now_s.get(e.name, 0):
                    found.append({"kind": "aeo_overtaken", "brand": e.name, "key": f"{scope}|{r.name}",
                                  "title": f"{r.name} overtook {e.name} {where}",
                                  "body": f"AEO score {r.name} {now_s[r.name]:.1f} vs {e.name} {now_s[e.name]:.1f} (last week {was_s.get(r.name, 0):.1f} vs {was_s.get(e.name, 0):.1f}).",
                                  "link": "/aeo" if scope == "all" else f"/aeo?engine={scope}"})

    top_prompts = {p.id: p for p in session.scalars(select(AiPrompt).where(AiPrompt.intent.in_(TOP_INTENTS)))}
    for pid, p in top_prompts.items():
        for e in own:
            k_now, n_now = rec[(cur, pid, e.name)]
            k_was, n_was = rec[(prev, pid, e.name)]
            if min(n_now, n_was) < MIN_PROMPT:
                continue
            was, now = k_was / n_was, k_now / n_now
            if was >= REC_FLOOR and was - now >= LOST_REC:
                found.append({"kind": "aeo_lost_recommendation", "brand": e.name, "key": f"{pid}",
                              "title": f"{e.name} lost recommendations on “{p.text[:80]}”",
                              "body": f"Recommended in {now:.0%} of answers this week, down from {was:.0%}.",
                              "link": f"/aeo/answers?prompt_id={pid}"})

    skus = {s.id: s for s in session.scalars(select(Sku))}
    seen_before: set[tuple] = set()
    for a in answers:
        if week_start(a.asked_at.date()) < cur:
            for c in a.claims:
                if c.verdict:
                    seen_before.add((c.sku_id, c.field, str(c.value)))
    new_facts: dict[tuple, int] = defaultdict(int)
    for a in answers:
        if week_start(a.asked_at.date()) == cur:
            for c in a.claims:
                key = (c.sku_id, c.field, str(c.value))
                if c.verdict and key not in seen_before:
                    new_facts[key] += 1
    for (sku_id, field, value), n in sorted(new_facts.items(), key=lambda kv: -kv[1])[:5]:
        sku = skus.get(sku_id)
        brand = sku.brand.name if sku else ""
        found.append({"kind": "aeo_wrong_fact", "brand": brand, "key": f"{sku_id}|{field}|{value}",
                      "title": f"New wrong fact about {sku.name if sku else 'a product'}: {field.replace('_', ' ')} “{value}”",
                      "body": f"Stated in {n} AI answer{'s' if n != 1 else ''} this week; no earlier answer said it. Correct it on the pages AI cites.",
                      "link": "/aeo"})

    existing = set(session.scalars(select(Alert.key).where(Alert.key.is_not(None))))
    out = []
    for f in found:
        key = f"{f['kind']}|{f['brand']}|{f['key']}|{cur.isoformat()}"
        if not demo and key in existing:
            continue
        a = Alert(organisation_id=org.id, sku_id=None, brand_id=brand_ids.get(f["brand"]), kind=f["kind"], title=f["title"][:300],
                  body=f["body"], link=f["link"], key=key, is_demo=demo, created_at=datetime.now(UTC))
        session.add(a)
        out.append(a)
    session.commit()
    return out
