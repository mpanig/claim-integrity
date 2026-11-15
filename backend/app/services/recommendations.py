"""Rule-based recommendations: turn open conflicts and gaps into ranked actions.

priority = sum(severity x page weight) x ease
expected impact = score points the product gains once the action is done

Rules (first match wins for each conflict):
  contradiction                       -> remove the contradicted claim         (e-commerce, ease 0.9)
  risky clinical/testing claim        -> regulatory review                     (regulatory, ease 0.4)
  risky free-from claims (per SKU)    -> add true ones to the brand site       (brand web,  ease 0.7)
  other risky claim                   -> remove or approve                     (e-commerce, ease 0.7)
  outdated ingredient list            -> update the retailer ingredient list   (e-commerce, ease 0.8)
  name drift (per SKU)                -> unify the product name                (e-commerce, ease 0.9)
  other wording drift                 -> align the wording                     (e-commerce, ease 0.9)
  weaker (approved claim/seal absent) -> add it to the page                    (e-commerce, ease 0.8)
  missing                             -> add the information to the page       (e-commerce, ease 0.8)
Gaps:
  truth sheet without free-from, claims or seals -> complete the truth sheet  (brand web, ease 1.0)
  AI answers stating wrong facts                 -> publish correct info       (PR / editorial, ease 0.5)
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AiAnswer, ApprovedClaim, Conflict, ConflictStatus, Page, Sku, Verdict
from app.pipeline.compare import COMPARED_FIELDS
from app.services.scoring import MAX_SEVERITY, UNRESOLVED, Tally, sku_tallies

OWNER_TYPES = {
    "brand_web": "Brand web team",
    "ecommerce": "E-commerce / retailer team",
    "pr_editorial": "PR / editorial",
    "regulatory": "Regulatory",
}
CLINICAL = re.compile(r"clinic|dermatolog|tested|proven|hypoallergenic|protectant|%|hours?\b", re.I)
FIELD_WORDS = {
    "name": "product name",
    "ingredients": "ingredient list",
    "free_from": "free-from claims",
    "claims": "product claims",
    "seals": "seals and endorsements",
}


@dataclass
class Rec:
    key: str
    rule: str
    title: str
    why: str
    owner_type: str
    ease: float
    sku: Sku
    pages: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    weighted: float = 0.0  # sum of severity x page weight
    severity: int = 0
    is_demo: bool = False
    link: str | None = None  # for gaps that are fixed by editing, not by a task

    def add(self, c: Conflict, page: Page) -> None:
        self.conflicts.append(c)
        self.weighted += c.severity * page.weight
        self.severity = max(self.severity, c.severity)
        label = page.retailer or page.url
        if label not in self.pages:
            self.pages.append(label)


def _text(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if isinstance(v, dict):
        return str(v.get("claim") or "")
    return str(v)


def build(session: Session, brand_id: int | None = None) -> list[dict[str, Any]]:
    sku_q = select(Sku).options(selectinload(Sku.brand))
    if brand_id is not None:
        sku_q = sku_q.where(Sku.brand_id == brand_id)
    skus = {s.id: s for s in session.scalars(sku_q)}
    tallies = sku_tallies(session, list(skus))
    rows = session.execute(
        select(Conflict, Page)
        .join(Page, Conflict.page_id == Page.id)
        .where(Conflict.sku_id.in_(skus), Conflict.status.in_(UNRESOLVED))
        .order_by(Conflict.id)
    ).all()

    recs: dict[str, Rec] = {}

    def rec(key: str, **kw: Any) -> Rec:
        if key not in recs:
            recs[key] = Rec(key=key, **kw)
        return recs[key]

    for c, page in rows:
        sku = skus[c.sku_id]
        where = page.retailer or page.url
        v, value = c.verdict, _text(c.page_value)
        if v is Verdict.contradiction:
            r = rec(f"contradiction:{c.id}", rule="contradiction", sku=sku, owner_type="ecommerce", ease=0.9,
                    title=f"Remove “{value}” from {where}",
                    why=f"{where} makes a claim its own ingredient list disproves. This misleads shoppers and is the highest legal risk.")
        elif v is Verdict.risky and CLINICAL.search(value):
            r = rec(f"regulatory:{c.sku_id}:{value.lower()}", rule="regulatory_review", sku=sku, owner_type="regulatory", ease=0.4,
                    title=f"Regulatory review of “{value}”",
                    why=f"“{value}” is a clinical or testing claim that is not on the approved truth sheet. Claims like this need substantiation before they can be used.")
        elif v is Verdict.risky and c.field == "free_from":
            r = rec(f"free_from:{c.sku_id}", rule="add_free_from", sku=sku, owner_type="brand_web", ease=0.7,
                    title=f"Decide on free-from claims for {sku.name}",
                    why="Retail pages advertise free-from claims the brand has not approved. Add the true ones to the brand site and truth sheet so every page can use them, and ask retailers to remove the rest.")
        elif v is Verdict.risky:
            r = rec(f"risky:{c.id}", rule="remove_or_approve", sku=sku, owner_type="ecommerce", ease=0.7,
                    title=f"Remove or approve “{value}” on {where}",
                    why=f"{where} shows a claim that is not approved for this product.")
        elif v is Verdict.outdated:
            r = rec(f"outdated:{c.id}", rule="update_ingredients", sku=sku, owner_type="ecommerce", ease=0.8,
                    title=f"Update the ingredient list on {where}",
                    why=f"{where} still shows an older formula. Shoppers who check ingredients (allergies, parabens) see the wrong list. Send the retailer the current list from the brand site.")
        elif v is Verdict.drift and c.field == "name":
            r = rec(f"name:{c.sku_id}", rule="unify_name", sku=sku, owner_type="ecommerce", ease=0.9,
                    title=f"Unify the product name for {sku.name}",
                    why="Some pages use a different product name, which splits search results and reviews. Ask them to use the approved name.")
        elif v is Verdict.drift:
            r = rec(f"drift:{c.id}", rule="align_wording", sku=sku, owner_type="ecommerce", ease=0.9,
                    title=f"Align the {FIELD_WORDS[c.field]} wording on {where}",
                    why=f"{where} says “{value}” instead of the approved “{_text(c.truth_value)}”. Same meaning, but inconsistent wording weakens the brand and can overstate the claim.")
        elif v is Verdict.weaker:
            r = rec(f"weaker:{c.id}", rule="add_missing_claim", sku=sku, owner_type="ecommerce", ease=0.8,
                    title=f"Add “{_text(c.truth_value)}” to {where}",
                    why=f"{where} leaves out an approved claim, so shoppers there miss a reason to buy.")
        else:  # missing
            r = rec(f"missing:{c.id}", rule="add_missing_info", sku=sku, owner_type="ecommerce", ease=0.8,
                    title=f"Add the {FIELD_WORDS[c.field]} to {where}",
                    why=f"{where} shows no {FIELD_WORDS[c.field]} for this product.")
        r.add(c, page)

    # Gap: truth sheets with nothing approved for some claim types.
    approved: dict[int, set[str]] = defaultdict(set)
    for sku_id, fld in session.execute(
        select(ApprovedClaim.sku_id, ApprovedClaim.field).where(ApprovedClaim.sku_id.in_(skus))
    ):
        approved[sku_id].add(fld)
    for sku in skus.values():
        gaps = [f for f in ("free_from", "claims", "seals") if f not in approved[sku.id]]
        if gaps:
            r = rec(f"truth:{sku.id}", rule="complete_truth_sheet", sku=sku, owner_type="brand_web", ease=1.0,
                    title=f"Complete the truth sheet for {sku.name}",
                    why=f"No approved {', '.join(FIELD_WORDS[g] for g in gaps)} on record. Without them, any such claim on a retailer page is flagged as unapproved, and pages can't be asked to use the right wording.",
                    link=f"/products/{sku.id}/truth")
            r.weighted = 3.0 * len(gaps)  # a low, steady priority
            r.severity = 3

    # Gap: AI assistants stating wrong facts (TODO(llm): only demo answers exist today).
    from app.services.ai_visibility import compare_answer  # local import avoids a cycle
    from app.pipeline.run import truth_for_sku

    answers = session.scalars(select(AiAnswer).where(AiAnswer.sku_id.in_(skus))).all()
    by_sku: dict[int, list[AiAnswer]] = defaultdict(list)
    for a in answers:
        if compare_answer(truth_for_sku(session, skus[a.sku_id]), a.stated_facts):
            by_sku[a.sku_id].append(a)
    for sku_id, wrong in by_sku.items():
        sku = skus[sku_id]
        r = rec(f"ai:{sku_id}", rule="correct_ai_answers", sku=sku, owner_type="pr_editorial", ease=0.5,
                title=f"Correct what AI assistants say about {sku.name}",
                why=f"{len(wrong)} AI answer{'s' if len(wrong) != 1 else ''} state outdated or unapproved facts. Publish clear, current product information (brand site FAQ, PR, editorial) that assistants can pick up, and fix the retail pages they repeat.",
                link="/ai-visibility")
        r.weighted = 6.0 * len(wrong)
        r.severity = 6
        r.is_demo = all(a.is_demo for a in wrong)

    out = []
    for r in recs.values():
        tally = tallies.get(r.sku.id) or Tally()
        worst = MAX_SEVERITY * len(COMPARED_FIELDS) * tally.page_weight
        impact = round(100 * r.weighted / worst) if r.conflicts and worst else 0
        statuses = {c.status for c in r.conflicts}
        state = "todo" if not r.conflicts or ConflictStatus.open in statuses else "in_progress"
        out.append(
            {
                "key": r.key,
                "rule": r.rule,
                "title": r.title,
                "why": r.why,
                "owner_type": r.owner_type,
                "owner_label": OWNER_TYPES[r.owner_type],
                "ease": r.ease,
                "severity": r.severity,
                "priority": round(r.weighted * r.ease, 2),
                "impact_points": impact,
                "sku_id": r.sku.id,
                "sku_name": r.sku.name,
                "brand_name": r.sku.brand.name,
                "pages": sorted(r.pages),
                "conflict_ids": [c.id for c in r.conflicts],
                "state": state,
                "link": r.link,
                "is_demo": r.is_demo,
            }
        )
    return sorted(out, key=lambda x: (x["state"] != "todo", -x["priority"], x["title"]))
