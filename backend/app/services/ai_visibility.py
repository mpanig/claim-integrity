"""What AI assistants say about products, checked against the approved truth.

No assistant is queried yet. TODO(llm): add a runner that sends each AiPrompt to the
configured assistants and extracts stated_facts, once API keys exist. Until then the
only answers are demo rows (is_demo=True) from `seed --demo-history`.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import AiAnswer, AiPrompt, Conflict, Organisation, Page, Sku, Verdict
from app.pipeline.compare import (
    Finding,
    claim_key,
    compare_list,
    free_from_key,
    name_key,
    normalise_ingredient,
    seal_key,
)
from app.pipeline.run import truth_for_sku
from app.services.scoring import UNRESOLVED

LLM_CONFIGURED = False  # TODO(llm): true once assistants can be queried


def compare_answer(truth: dict[str, Any], facts: dict[str, Any]) -> list[Finding]:
    """Check facts an assistant stated. Leaving something out is not a finding;
    stating something wrong, unapproved or outdated is."""
    findings: list[Finding] = []
    if facts.get("name") and truth.get("name") and name_key(facts["name"]) != name_key(truth["name"]):
        findings.append(Finding("name", Verdict.drift, facts["name"], truth["name"]))
    known = {normalise_ingredient(i) for i in truth.get("ingredients") or []}
    for item in facts.get("contains") or []:
        if known and normalise_ingredient(item) not in known:
            findings.append(Finding("ingredients", Verdict.outdated, item, None))
    for field in ("free_from", "claims", "seals"):
        if facts.get(field):
            findings += [
                f for f in compare_list(field, truth.get(field) or [], facts[field]) if f.verdict is not Verdict.weaker
            ]
    return sorted(findings, key=lambda f: -f.severity)


_KEYS = {"free_from": free_from_key, "claims": claim_key, "seals": seal_key, "name": name_key}


def _echo_items(field: str, verdict: str, value: Any) -> list[str]:
    """Normalised items a finding is about, so an answer and a page issue can be matched."""
    if field == "ingredients" and verdict == "outdated":
        if isinstance(value, dict):  # page conflict: the extra ingredients on the page
            return list(value.get("not_in_truth") or [])
        return [normalise_ingredient(value)] if isinstance(value, str) else []
    if isinstance(value, str) and field in _KEYS:
        return [_KEYS[field](value)]
    return []


def overview(session: Session, brand_id: int | None = None) -> dict[str, Any]:
    prompts_q = select(AiPrompt).order_by(AiPrompt.id)
    answers_q = select(AiAnswer).options(selectinload(AiAnswer.prompt)).order_by(AiAnswer.asked_at.desc(), AiAnswer.id)
    skus = {s.id: s for s in session.scalars(select(Sku).options(selectinload(Sku.brand)))}
    if brand_id is not None:
        keep = {sid for sid, s in skus.items() if s.brand_id == brand_id}
        prompts_q = prompts_q.where((AiPrompt.brand_id == brand_id) | (AiPrompt.sku_id.in_(keep)) | (AiPrompt.brand_id.is_(None) & AiPrompt.sku_id.is_(None)))
    prompts = session.scalars(prompts_q).all()
    prompt_ids = [p.id for p in prompts]
    answers = session.scalars(answers_q.where(AiAnswer.prompt_id.in_(prompt_ids))).all()

    # Open page issues an answer may be repeating, keyed by the specific claim or ingredient.
    echoes: dict[tuple[int, str, str, str], set[str]] = {}
    for c, page in session.execute(
        select(Conflict, Page).join(Page, Conflict.page_id == Page.id).where(Conflict.status.in_(UNRESOLVED))
    ):
        for item in _echo_items(c.field, c.verdict.value, c.page_value):
            echoes.setdefault((c.sku_id, c.field, c.verdict.value, item), set()).add(page.retailer or page.url)

    truths: dict[int, dict[str, Any]] = {}
    out_answers, mentions = [], Counter()
    with_issues = checked = 0
    for a in answers:
        findings = []
        if a.sku_id in skus:
            truth = truths.setdefault(a.sku_id, truth_for_sku(session, skus[a.sku_id]))
            checked += 1
            for f in compare_answer(truth, a.stated_facts):
                findings.append(
                    {
                        "field": f.field,
                        "verdict": f.verdict.value,
                        "severity": f.severity,
                        "stated": f.page_value,
                        "approved": f.truth_value,
                        "echoes": sorted(
                            {
                                label
                                for item in _echo_items(f.field, f.verdict.value, f.page_value)
                                for label in echoes.get((a.sku_id, f.field, f.verdict.value, item), ())
                            }
                        ),
                    }
                )
            with_issues += bool(findings)
        mentions.update(a.mentioned_brands)
        out_answers.append(
            {
                "id": a.id,
                "prompt_id": a.prompt_id,
                "prompt": a.prompt.text,
                "sku_id": a.sku_id,
                "sku_name": skus[a.sku_id].name if a.sku_id in skus else None,
                "assistant": a.assistant,
                "answer": a.answer,
                "asked_at": a.asked_at.isoformat(),
                "stated_facts": a.stated_facts,
                "mentioned_brands": a.mentioned_brands,
                "findings": findings,
                "is_demo": a.is_demo,
            }
        )

    total = sum(mentions.values())
    return {
        "configured": LLM_CONFIGURED,
        "demo": any(a.is_demo for a in answers),
        "prompts": [
            {
                "id": p.id,
                "text": p.text,
                "sku_id": p.sku_id,
                "sku_name": skus[p.sku_id].name if p.sku_id in skus else None,
                "answers": sum(1 for a in answers if a.prompt_id == p.id),
            }
            for p in prompts
        ],
        "answers": out_answers,
        "accuracy": {"checked": checked, "with_issues": with_issues},
        "share_of_voice": [
            {"brand": b, "mentions": n, "share": round(100 * n / total)} for b, n in mentions.most_common()
        ],
    }


DEMO_ASSISTANTS = ("Assistant A (demo)", "Assistant B (demo)")


def generate_demo_answers(session: Session) -> int:
    """Write invented answers so the screen can be previewed. All rows are is_demo=True."""
    session.execute(delete(AiAnswer).where(AiAnswer.is_demo.is_(True)))
    org = session.scalar(select(Organisation).order_by(Organisation.id))
    skus = {s.brand.name: s for s in session.scalars(select(Sku).options(selectinload(Sku.brand)))}
    if org is None or not {"CeraVe", "Aveeno"} <= skus.keys():
        session.commit()
        return 0
    cerave, aveeno = skus["CeraVe"], skus["Aveeno"]

    def prompt(text: str, sku: Sku | None) -> AiPrompt:
        p = session.scalar(select(AiPrompt).where(AiPrompt.text == text))
        if p is None:
            p = AiPrompt(organisation_id=org.id, sku_id=sku.id if sku else None, brand_id=sku.brand_id if sku else None, text=text)
            session.add(p)
            session.flush()
        return p

    category = prompt("What's a good fragrance-free face cleanser for sensitive skin?", None)
    parabens = prompt(f"Does {cerave.name} contain parabens?", cerave)
    hypo = prompt(f"Is {aveeno.name} hypoallergenic?", aveeno)
    now = datetime.now(UTC)
    rows = [
        (category, None, 0, "Two widely recommended options are CeraVe Hydrating Facial Cleanser and Aveeno Calm + Restore Nourishing Oat Cleanser. Both are marketed for sensitive skin.", {}, ["CeraVe", "Aveeno"]),
        (category, None, 1, "Many dermatologists suggest CeraVe Hydrating Facial Cleanser; several other brands also make gentle cleansers.", {}, ["CeraVe", "Other brands"]),
        (parabens, cerave, 0, "Yes. Its ingredient list includes methylparaben and propylparaben. It is fragrance free.", {"contains": ["Methylparaben", "Propylparaben"], "free_from": ["Fragrance Free"]}, ["CeraVe"]),
        (parabens, cerave, 1, "The current formula is non-comedogenic and carries the National Eczema Association Seal of Acceptance.", {"claims": ["Non-comedogenic"], "seals": ["NEA Seal of Acceptance"]}, ["CeraVe"]),
        (hypo, aveeno, 0, "Yes, it is described as hypoallergenic and fragrance free, with colloidal oatmeal.", {"claims": ["Hypoallergenic"], "free_from": ["Fragrance Free"]}, ["Aveeno"]),
        (hypo, aveeno, 1, "It contains oat kernel flour and feverfew. I couldn't confirm a hypoallergenic claim from the brand.", {"contains": ["Avena Sativa (Oat) Kernel Flour"]}, ["Aveeno"]),
    ]
    for i, (p, sku, who, text, facts, brands) in enumerate(rows):
        session.add(
            AiAnswer(
                organisation_id=org.id,
                prompt_id=p.id,
                sku_id=sku.id if sku else None,
                assistant=DEMO_ASSISTANTS[who],
                answer=text,
                stated_facts=facts,
                mentioned_brands=brands,
                asked_at=now - timedelta(days=i),
                is_demo=True,
            )
        )
    session.commit()
    return len(rows)
