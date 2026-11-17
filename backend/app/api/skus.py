from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.common import DB, conflict_out, conflict_query, get_or_404, page_label, sku_out, truth_statuses
from app.config import PLACEHOLDER_USER
from app.models import ApprovedClaim, Brand, Conflict, ConflictStatus, Organisation, Page, Sku
from app.pipeline.compare import COMPARED_FIELDS, LIST_FIELDS
from app.pipeline.run import latest_extractions, run_for_sku, truth_for_sku
from app.schemas import BrandOut, ClaimIn, ClaimOut, ConflictOut, RunOut, SkuIn, SkuOut, SkuPatch
from app.pipeline.truth import inferred_claims, inferred_for
from app.services.scoring import UNRESOLVED, drift, sku_tallies
from app.services.workflow import log

router = APIRouter()

RED = {"contradiction", "risky", "outdated"}


def validate_claim(field: str, value: Any) -> Any:
    if field not in COMPARED_FIELDS:
        raise HTTPException(422, f"unknown field {field!r}; expected one of {', '.join(COMPARED_FIELDS)}")
    if field == "name":
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, "name must be a non-empty string")
        return value.strip()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise HTTPException(422, f"{field} must be a list of strings")
    cleaned = [v.strip() for v in value if v.strip()]
    if field == "ingredients" and not cleaned:
        raise HTTPException(422, "ingredients cannot be empty")
    return cleaned


def current_claims(session, sku_id: int) -> list[ApprovedClaim]:
    rows = session.scalars(
        select(ApprovedClaim).where(ApprovedClaim.sku_id == sku_id).order_by(ApprovedClaim.id)
    )
    latest: dict[str, ApprovedClaim] = {}
    for row in rows:
        latest[row.field] = row
    return [latest[f] for f in COMPARED_FIELDS if f in latest]


def _sku_query():
    return select(Sku).options(selectinload(Sku.brand)).order_by(Sku.name)


@router.get("/brands", response_model=list[BrandOut])
def list_brands(session: DB) -> list[Brand]:
    return list(session.scalars(select(Brand).order_by(Brand.name)))


@router.get("/skus", response_model=list[SkuOut])
def list_skus(session: DB, q: str | None = None, brand_id: int | None = None) -> list[SkuOut]:
    stmt = _sku_query()
    if brand_id is not None:
        stmt = stmt.where(Sku.brand_id == brand_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.join(Brand).where(or_(Sku.name.ilike(like), Sku.gtin.ilike(like), Brand.name.ilike(like)))
    skus = session.scalars(stmt).all()
    tallies = sku_tallies(session, [s.id for s in skus])
    truth = truth_statuses(session, [s.id for s in skus])
    return [sku_out(s, tallies.get(s.id), truth[s.id]) for s in skus]


@router.post("/skus", response_model=SkuOut, status_code=201)
def create_sku(body: SkuIn, session: DB) -> SkuOut:
    if body.brand_id is not None:
        brand = get_or_404(session, Brand, body.brand_id, "brand")
    elif body.brand_name and body.brand_name.strip():
        brand = session.scalar(select(Brand).where(func.lower(Brand.name) == body.brand_name.strip().lower()))
        if brand is None:
            # TODO(auth): use the signed-in user's organisation.
            org = session.scalar(select(Organisation).order_by(Organisation.id))
            if org is None:
                org = Organisation(name="Default")
                session.add(org)
                session.flush()
            brand = Brand(organisation_id=org.id, name=body.brand_name.strip())
            session.add(brand)
            session.flush()
    else:
        raise HTTPException(422, "brand_id or brand_name is required")

    claims = {f: validate_claim(f, v) for f, v in body.claims.items()}
    sku = Sku(
        organisation_id=brand.organisation_id,
        brand_id=brand.id,
        name=body.name.strip(),
        gtin=body.gtin or None,
        line=body.line or None,
    )
    session.add(sku)
    session.flush()
    for field, value in claims.items():
        session.add(
            ApprovedClaim(
                organisation_id=sku.organisation_id,
                sku_id=sku.id,
                field=field,
                value=value,
                evidence_url=body.evidence_url,
                approved_by=PLACEHOLDER_USER,
            )
        )
    log(session, organisation_id=sku.organisation_id, sku_id=sku.id, action="sku_created", detail={"name": sku.name})
    session.commit()
    session.refresh(sku)
    return sku_out(sku, None, truth_statuses(session, [sku.id])[sku.id])


@router.get("/truth-sheets")
def truth_sheet_summary(session: DB, brand_id: int | None = None) -> list[dict[str, Any]]:
    """Per SKU: which fields have approved claims and when the last was approved (one query, for the list page)."""
    stmt = select(ApprovedClaim.sku_id, func.array_agg(func.distinct(ApprovedClaim.field)), func.max(ApprovedClaim.created_at)).group_by(ApprovedClaim.sku_id)
    if brand_id is not None:
        stmt = stmt.where(ApprovedClaim.sku_id.in_(select(Sku.id).where(Sku.brand_id == brand_id)))
    return [{"sku_id": sku_id, "fields": sorted(fields), "last_approved": last} for sku_id, fields, last in session.execute(stmt)]


@router.get("/skus/{sku_id}", response_model=SkuOut)
def get_sku(sku_id: int, session: DB) -> SkuOut:
    sku = get_or_404(session, Sku, sku_id, "SKU")
    return sku_out(sku, sku_tallies(session, [sku.id]).get(sku.id), truth_statuses(session, [sku.id])[sku.id])


@router.patch("/skus/{sku_id}", response_model=SkuOut)
def update_sku(sku_id: int, body: SkuPatch, session: DB) -> SkuOut:
    sku = get_or_404(session, Sku, sku_id, "SKU")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(sku, key, value.strip() if isinstance(value, str) else value)
    if changes:
        log(session, organisation_id=sku.organisation_id, sku_id=sku.id, action="sku_updated", detail=changes)
    session.commit()
    return get_sku(sku_id, session)


@router.delete("/skus/{sku_id}", status_code=204)
def delete_sku(sku_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, Sku, sku_id, "SKU"))
    session.commit()
    return Response(status_code=204)


@router.get("/skus/{sku_id}/claims", response_model=list[ClaimOut])
def list_claims(sku_id: int, session: DB) -> list[ApprovedClaim]:
    get_or_404(session, Sku, sku_id, "SKU")
    return current_claims(session, sku_id)


@router.put("/skus/{sku_id}/claims/{field}", response_model=ClaimOut)
def set_claim(sku_id: int, field: str, body: ClaimIn, session: DB) -> ApprovedClaim:
    """Approve a new value for a field. Earlier values are kept as history."""
    sku = get_or_404(session, Sku, sku_id, "SKU")
    value = validate_claim(field, body.value)
    claim = ApprovedClaim(
        organisation_id=sku.organisation_id,
        sku_id=sku.id,
        field=field,
        value=value,
        evidence_url=body.evidence_url,
        approved_by=PLACEHOLDER_USER,
    )
    session.add(claim)
    if field == "name":
        sku.name = value
    log(session, organisation_id=sku.organisation_id, sku_id=sku.id, action="claim_approved", detail={"field": field})
    session.commit()
    run_for_sku(session, sku, actor=PLACEHOLDER_USER)  # recompute conflicts and score straight away
    session.refresh(claim)
    return claim


@router.delete("/skus/{sku_id}/claims/{field}", status_code=204)
def delete_claim(sku_id: int, field: str, session: DB) -> Response:
    sku = get_or_404(session, Sku, sku_id, "SKU")
    if field == "name":
        raise HTTPException(422, "the product name cannot be removed")
    deleted = session.execute(
        delete(ApprovedClaim).where(ApprovedClaim.sku_id == sku_id, ApprovedClaim.field == field)
    ).rowcount
    if not deleted:
        raise HTTPException(404, "no approved claim for that field")
    log(session, organisation_id=sku.organisation_id, sku_id=sku.id, action="claim_removed", detail={"field": field})
    session.commit()
    run_for_sku(session, sku, actor=PLACEHOLDER_USER)  # recompute (may fall back to inferred truth)
    return Response(status_code=204)


@router.get("/skus/{sku_id}/conflicts", response_model=list[ConflictOut])
def list_sku_conflicts(sku_id: int, session: DB) -> list[ConflictOut]:
    get_or_404(session, Sku, sku_id, "SKU")
    rows = session.scalars(
        conflict_query().where(Conflict.sku_id == sku_id).order_by(Conflict.severity.desc(), Conflict.id)
    )
    return [conflict_out(c) for c in rows]


@router.post("/skus/{sku_id}/run", response_model=RunOut)
def run_sku(sku_id: int, session: DB) -> RunOut:
    """Re-check: compare stored extractions against the truth and reconcile conflicts."""
    sku = get_or_404(session, Sku, sku_id, "SKU")
    result = run_for_sku(session, sku, actor=PLACEHOLDER_USER)
    tally = sku_tallies(session, [sku.id]).get(sku.id)
    return RunOut(
        new=len(result.new),
        reopened=len(result.reopened),
        resolved=len(result.resolved),
        unresolved=tally.unresolved if tally else 0,
        score=tally.score if tally else None,
        drift_score=drift(tally.score) if tally else None,
        truth_status=truth_statuses(session, [sku.id])[sku.id][0],
    )


class TruthSheetIn(BaseModel):
    claims: dict[str, Any]
    evidence_url: str | None = None


@router.get("/skus/{sku_id}/inferred-truth")
def get_inferred_truth(sku_id: int, session: DB) -> dict[str, Any]:
    """The provisional truth for a SKU without a truth sheet: values, how much of the page weight
    agrees with each, and how it was inferred. Empty once a truth sheet is approved."""
    get_or_404(session, Sku, sku_id, "SKU")
    row = inferred_for(session, sku_id)
    status = truth_statuses(session, [sku_id])[sku_id][0]
    if row is None:
        return {"status": status, "method": None, "sources": 0, "fields": {}, "agreement": {}}
    return {"status": status, "method": row.method, "sources": row.sources, "fields": inferred_claims(session, sku_id),
            "agreement": row.agreement, "updated_at": row.updated_at}


@router.post("/skus/{sku_id}/truth-sheet", response_model=SkuOut)
def save_truth_sheet(sku_id: int, body: TruthSheetIn, session: DB) -> SkuOut:
    """Approve several fields at once (e.g. the inferred values, as reviewed), then recompute
    conflicts and score immediately. The inferred truth is cleared and its recommendation resolves."""
    sku = get_or_404(session, Sku, sku_id, "SKU")
    claims = {f: validate_claim(f, v) for f, v in body.claims.items() if v not in (None, "", [])}
    if not any(f != "name" for f in claims):
        raise HTTPException(422, "approve at least one field besides the name")
    for field, value in claims.items():
        session.add(ApprovedClaim(organisation_id=sku.organisation_id, sku_id=sku.id, field=field, value=value,
                                  evidence_url=body.evidence_url, approved_by=PLACEHOLDER_USER))
        if field == "name":
            sku.name = value
    log(session, organisation_id=sku.organisation_id, sku_id=sku.id, action="truth_sheet_approved", detail={"fields": sorted(claims)})
    session.commit()
    run_for_sku(session, sku, actor=PLACEHOLDER_USER)
    return get_sku(sku_id, session)


@router.get("/skus/{sku_id}/matrix")
def sku_matrix(sku_id: int, session: DB) -> dict[str, Any]:
    """Claim fields x sources. Each cell: value, quote, state (match|warn|bad|na), conflicts."""
    sku = get_or_404(session, Sku, sku_id, "SKU")
    claims = current_claims(session, sku_id)
    truth = truth_for_sku(session, sku)
    status = truth_statuses(session, [sku.id])[sku.id]
    inferred = inferred_for(session, sku.id)
    evidence = next((c.evidence_url for c in claims if c.evidence_url), None)

    conflicts = session.scalars(
        select(Conflict).where(Conflict.sku_id == sku_id, Conflict.status != ConflictStatus.verified)
    ).all()
    by_cell: dict[tuple[int, str], list[Conflict]] = {}
    for c in conflicts:
        by_cell.setdefault((c.page_id, c.field), []).append(c)

    sources = []
    extractions = latest_extractions(session, sku_id)
    pages = {p.id: p for p in session.scalars(select(Page).where(Page.id.in_(extractions)))}
    for page_id, extraction in sorted(extractions.items(), key=lambda kv: -pages[kv[0]].weight):
        page = pages[page_id]
        cells = {}
        for field in COMPARED_FIELDS:
            extracted = extraction.fields.get(field) or {}
            cell_conflicts = sorted(by_cell.get((page_id, field), []), key=lambda c: -c.severity)
            open_verdicts = {c.verdict.value for c in cell_conflicts if c.status in UNRESOLVED}
            empty_truth = truth.get(field) in (None, "", [])
            if open_verdicts & RED:
                state = "bad"
            elif open_verdicts:
                state = "warn"
            elif extracted.get("value") in (None, "", []) and empty_truth:
                state = "na"
            else:
                state = "match"
            cells[field] = {
                "value": extracted.get("value"),
                "quote": extracted.get("quote"),
                "state": state,
                "conflicts": [
                    {"id": c.id, "verdict": c.verdict.value, "severity": c.severity, "status": c.status.value}
                    for c in cell_conflicts
                ],
            }
        sources.append(
            {
                "page_id": page.id,
                "label": page_label(page),
                "url": page.url,
                "source_type": page.source_type,
                "weight": page.weight,
                "fetched_at": extraction.snapshot.fetched_at,
                "cells": cells,
            }
        )

    return {
        "sku": sku_out(sku, sku_tallies(session, [sku.id]).get(sku.id), status).model_dump(),
        "fields": list(COMPARED_FIELDS),
        "list_fields": list(LIST_FIELDS),
        "truth": {
            "label": f"{sku.brand.name} site (approved)" if status[0] == "approved" else "Inferred truth, unverified",
            "url": evidence,
            "values": {f: truth.get(f) for f in COMPARED_FIELDS},
            "status": status[0],
            "method": status[1],
            "agreement": inferred.agreement if inferred else {},
        },
        "sources": sources,
    }
