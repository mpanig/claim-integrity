"""Content brief: what a page should say so AI assistants answer one question well, for one brand.

Built only from the app's own data, no LLM: the truth sheet (approved facts only), the brand's
positioning and how AI perceives it now, facts AI gets wrong about the product, competitors
that own the attributes, related questions from discovery, sites AI cites when it recommends
a competitor instead, and the answer-readiness checklist.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.coverage import coverage
from app.ai.discovery import _similar, _tokens, discover
from app.ai.insights import insights
from app.ai.perception import ATTRIBUTES, perception
from app.ai.readiness import CHECKS
from app.models import Brand, Sku
from app.pipeline.run import truth_for_sku

FIELD_LABEL = {"claims": "Claims", "free_from": "Free from", "seals": "Seals and endorsements", "ingredients": "Ingredients (full INCI list)"}


def build_brief(session: Session, question: str, brand_id: int, sku_id: int | None = None) -> dict[str, Any]:
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise ValueError("brand not found")
    sku = session.get(Sku, sku_id) if sku_id else session.scalars(select(Sku).where(Sku.brand_id == brand_id).order_by(Sku.id)).first()
    truth = truth_for_sku(session, sku, include_inferred=False) if sku else {}
    per = perception(session)
    cov = coverage(session)
    me = next((b for b in per["brands"] if b["name"] == brand.name), None)
    labels = {k: v[0] for k, v in ATTRIBUTES.items()}

    emphasise = []
    for key in brand.positioning or []:
        rate = (me["attributes"][key]["rate"] if me else None) or 0
        leader = per["leaders"].get(key)
        emphasise.append({"attribute": labels[key], "ai_rate": rate, "leader": leader if leader != brand.name else None, "gap": rate < per["thresholds"]["weak"]})
    emphasise.sort(key=lambda e: (not e["gap"], e["ai_rate"]))

    facts = [{"label": FIELD_LABEL.get(k, k.replace("_", " ").capitalize()), "value": v} for k, v in truth.items() if k != "name" and v]

    wrong = []
    if sku:
        for w in insights(session, sku_id=sku.id)["wrong_claims"]:
            item = f"{w['field'].replace('_', ' ')}: {w['value']}"
            if item not in {x["claim"] for x in wrong}:
                wrong.append({"claim": item, "verdict": w["verdict"], "quote": w["quote"]})
            if len(wrong) >= 5:
                break

    q = _tokens(question)
    # Related questions: open ones, or ones about this brand; never about another brand's product.
    pool = [c for c in discover(session, per=per, cov=cov)["candidates"] if c.get("brand") in (None, brand.name) and c["text"].lower() != question.lower()]
    related = [c["text"] for c in sorted(pool, key=lambda c: -_similar(q, _tokens(c["text"])))][:5]
    gap_sites = [d["domain"] for d in sorted(cov["third_party"], key=lambda d: -d["gap"]) if d["gap"] > 0][:5]
    rivals = sorted({e["leader"] for e in emphasise if e["leader"]})
    product = sku.name if sku else brand.name

    brief = {
        "question": question,
        "brand": brand.name,
        "product": product,
        "answer_first": f"Open with a 40-60 word direct answer to “{question}” that names {product} and makes clear, in plain words: "
        + ("; ".join(e["attribute"].lower() for e in emphasise[:3]) if emphasise else "what it is and who it's for")
        + ". Only use facts from the approved list below.",
        "emphasise": emphasise,
        "facts": facts,
        "correct": wrong,
        "competitors": rivals,
        "related_questions": related,
        "sites": gap_sites,
        "structure": [{"label": label, "fix": fix} for label, _p, fix in CHECKS.values()],
    }
    brief["markdown"] = to_markdown(brief)
    return brief


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def to_markdown(b: dict[str, Any]) -> str:
    out = [f"# Content brief: {b['question']}", "", f"**Brand:** {b['brand']}  ", f"**Product:** {b['product']}", "", "## Answer first", "", b["answer_first"], ""]
    if b["emphasise"]:
        out += ["## Attributes to make unmistakable", ""]
        for e in b["emphasise"]:
            line = f"- **{e['attribute']}**: AI links it to {b['brand']} in {_pct(e['ai_rate'])} of answers"
            if e["leader"]:
                line += f"; {e['leader']} owns it today"
            out.append(line + (" (gap)" if e["gap"] else ""))
        out.append("")
    if b["facts"]:
        out += ["## Approved facts to state (truth sheet)", ""]
        for f in b["facts"]:
            v = f["value"]
            out.append(f"- **{f['label']}:** {', '.join(map(str, v)) if isinstance(v, list) else v}")
        out.append("")
    if b["correct"]:
        out += ["## What AI gets wrong today (state the correct fact plainly)", ""]
        out += [f"- {w['claim']} ({w['verdict']})" for w in b["correct"]]
        out.append("")
    if b["related_questions"]:
        out += ["## Answer these as H2 questions", ""] + [f"- {q}" for q in b["related_questions"]] + [""]
    if b["sites"]:
        out += ["## Earn mentions on", "", "Sites AI cites when it recommends a competitor instead of you:", ""] + [f"- {s}" for s in b["sites"]] + [""]
    out += ["## Page checklist", ""] + [f"- [ ] {s['label']}: {s['fix']}" for s in b["structure"]]
    return "\n".join(out) + "\n"
