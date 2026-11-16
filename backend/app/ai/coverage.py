"""From AI answers: which third-party sites shape them, and which use cases we're missing.

third_party  domains the answers cite (excluding brand sites), how often, and "gap" sites:
             cited in answers that recommend a competitor but don't mention any of our brands.
use_cases    per question type x persona: our best mention rate vs the leading competitor's.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.insights import rate, select_answers
from app.models import AiPrompt, Persona, Sku

INTENT_LABEL = {
    "category": "Best-of",
    "problem": "Problem-led",
    "attribute": "Product question",
    "versus": "Brand vs brand",
    "where_to_buy": "Where to buy",
}


def _topic(session: Session, p: AiPrompt) -> str:
    sku = session.get(Sku, p.sku_id) if p.sku_id else None
    if p.intent == "versus" and sku:
        return f"{sku.brand.name} vs {p.competitor or 'competitor'}"
    if p.intent in ("attribute", "where_to_buy") and sku:
        return sku.name
    return p.category or p.text[:50]


def coverage(session: Session, **filters: Any) -> dict[str, Any]:
    answers, modes = select_answers(session, **filters)
    prompts = {p.id: p for p in session.scalars(select(AiPrompt))}
    personas = {p.id: p.name for p in session.scalars(select(Persona))}

    domains: dict[str, dict[str, Any]] = {}
    for a in answers:
        ours = any(m.is_own for m in a.mentions)
        rival_rec = any(m.recommended and not m.is_own for m in a.mentions)
        for c in a.citations:
            if c.page_type == "brand":
                continue
            d = domains.setdefault(c.domain, {"domain": c.domain, "page_type": c.page_type, "citations": 0, "with_our_brand": 0, "gap": 0})
            d["citations"] += 1
            d["with_our_brand"] += 1 if ours else 0
            d["gap"] += 1 if (rival_rec and not ours) else 0
    third_party = sorted(domains.values(), key=lambda d: (-d["citations"], d["domain"]))

    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for a in answers:
        p = prompts.get(a.prompt_id)
        if p is None:
            continue
        use = f"{INTENT_LABEL.get(p.intent, p.intent)}: {_topic(session, p)}"
        groups[(use, personas.get(a.persona_id, "No persona") if a.persona_id else "No persona")].append(a)
    use_cases = []
    for (use, persona), group in groups.items():
        n = len(group)
        by_brand: dict[tuple[str, bool], int] = defaultdict(int)
        for a in group:
            for m in a.mentions:
                by_brand[(m.name, m.is_own)] += 1
        ours = max(((k, v) for k, v in by_brand.items() if k[1]), key=lambda kv: kv[1], default=None)
        rival = max(((k, v) for k, v in by_brand.items() if not k[1]), key=lambda kv: kv[1], default=None)
        our_rate = rate(ours[1], n) if ours else rate(0, n)
        rival_rate = rate(rival[1], n) if rival else rate(0, n)
        use_cases.append(
            {
                "use_case": use,
                "persona": persona,
                "answers": n,
                "our_brand": ours[0][0] if ours else None,
                "ours": our_rate,
                "top_competitor": rival[0][0] if rival else None,
                "competitor": rival_rate,
                "gap": round((rival_rate["rate"] or 0) - (our_rate["rate"] or 0), 3),
            }
        )
    use_cases.sort(key=lambda u: -u["gap"])
    return {"answers": len(answers), "engines": modes, "demo": any(a.is_demo for a in answers), "third_party": third_party[:30], "use_cases": use_cases}
