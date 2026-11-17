"""Weekly report per brand, and a CSV of its issues."""

import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AuditEvent, Brand, Conflict, ConflictStatus, Page, Sku
from app.services.scoring import UNRESOLVED, Tally, drift, sku_tallies
from app.services.trends import week_start, weekly_trends

VERDICT_TEXT = {
    "contradiction": "Contradicts itself",
    "risky": "Unapproved claim",
    "outdated": "Outdated info",
    "weaker": "Approved claim missing",
    "missing": "Information missing",
    "drift": "Wording differs",
}
FIELD_TEXT = {
    "name": "Product name",
    "ingredients": "Ingredient list",
    "free_from": "Free-from claims",
    "claims": "Product claims",
    "seals": "Seals & endorsements",
}


def _value(v: Any) -> str:
    if isinstance(v, dict):
        if "claim" in v:
            return str(v["claim"])
        extra, gone = v.get("not_in_truth") or [], v.get("not_on_page") or []
        return f"extra: {', '.join(extra) or '-'}; missing: {', '.join(gone) or '-'}"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return "" if v is None else str(v)


def _change(now: int | None, before: int | None) -> int | None:
    return now - before if now is not None and before is not None else None


def weekly_report(session: Session, brand: Brand, today: date | None = None) -> dict[str, Any]:
    """This week (Monday to Sunday, UTC) for one brand, compared with last week."""
    today = today or datetime.now(UTC).date()
    start = week_start(today)
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_dt = start_dt + timedelta(days=7)

    skus = session.scalars(
        select(Sku).options(selectinload(Sku.brand)).where(Sku.brand_id == brand.id).order_by(Sku.name)
    ).all()
    sku_ids = [s.id for s in skus]
    tallies = sku_tallies(session, sku_ids)
    total = Tally()
    for t in tallies.values():
        total.add(t)
    trend = weekly_trends(session, list(skus), 2, today)
    last_week = trend["weeks"][0]

    new_issues = session.scalar(
        select(func.count())
        .select_from(Conflict)
        .where(Conflict.sku_id.in_(sku_ids), Conflict.detected_at >= start_dt, Conflict.detected_at < end_dt)
    )
    verified_events = session.scalars(
        select(AuditEvent).where(
            AuditEvent.sku_id.in_(sku_ids),
            AuditEvent.action == "status",
            AuditEvent.at >= start_dt,
            AuditEvent.at < end_dt,
        )
    ).all()
    fixes_verified = len({e.conflict_id for e in verified_events if e.detail.get("to") == "verified"})
    by_status = dict(
        session.execute(
            select(Conflict.status, func.count()).where(Conflict.sku_id.in_(sku_ids)).group_by(Conflict.status)
        ).all()
    )

    top = session.execute(
        select(Conflict, Page)
        .join(Page, Conflict.page_id == Page.id)
        .where(Conflict.sku_id.in_(sku_ids), Conflict.status.in_(UNRESOLVED))
        .order_by((Conflict.severity * Page.weight).desc(), Conflict.id)
        .limit(5)
    ).all()
    names = {s.id: s.name for s in skus}

    products = []
    for s in skus:
        t = tallies.get(s.id) or Tally()
        before = weekly_trends(session, [s], 2, today)["weeks"][0]["score"]
        products.append(
            {"id": s.id, "name": s.name, "score": t.score, "change": _change(t.score, before), "unresolved": t.unresolved,
             "drift_score": drift(t.score), "drift_change": _change(drift(t.score), drift(before))}
        )

    return {
        "brand": {"id": brand.id, "name": brand.name},
        "period": {"start": start.isoformat(), "end": (start + timedelta(days=6)).isoformat()},
        "demo": trend["demo"],  # last week's score may come from demo history
        "score": {"now": total.score, "last_week": last_week["score"], "change": _change(total.score, last_week["score"])},
        # Drift score (0 = no drift): what the report shows. "score" is the older consistency value.
        "drift": {"now": drift(total.score), "last_week": drift(last_week["score"]), "change": _change(drift(total.score), drift(last_week["score"]))},
        "unresolved": total.unresolved,
        "by_verdict": total.by_verdict,
        "new_issues": new_issues,
        "fixes_verified": fixes_verified,
        "in_progress": by_status.get(ConflictStatus.accepted, 0) + by_status.get(ConflictStatus.fixed, 0),
        "top_issues": [
            {
                "id": c.id,
                "sku_name": names[c.sku_id],
                "page": p.retailer or p.url,
                "field": c.field,
                "verdict": c.verdict.value,
                "severity": c.severity,
                "status": c.status.value,
                "value": _value(c.page_value),
            }
            for c, p in top
        ],
        "products": products,
    }


CSV_COLUMNS = [
    "Brand", "Product", "Page", "Page URL", "Claim type", "Issue", "What the page shows",
    "Approved", "Risk (1-10)", "Status", "Owner", "Due date", "Found",
]


def issues_csv(session: Session, brand_id: int | None) -> str:
    """Every issue not yet verified as fixed, one row each."""
    stmt = (
        select(Conflict, Page, Sku, Brand)
        .join(Page, Conflict.page_id == Page.id)
        .join(Sku, Conflict.sku_id == Sku.id)
        .join(Brand, Sku.brand_id == Brand.id)
        .where(Conflict.status != ConflictStatus.verified)
        .order_by(Brand.name, Sku.name, Conflict.severity.desc(), Conflict.id)
    )
    if brand_id is not None:
        stmt = stmt.where(Sku.brand_id == brand_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for c, p, s, b in session.execute(stmt):
        w.writerow(
            [
                b.name, s.name, p.retailer or p.url, p.url, FIELD_TEXT.get(c.field, c.field),
                VERDICT_TEXT[c.verdict.value], _value(c.page_value), _value(c.truth_value), c.severity,
                c.status.value, c.owner or "", c.due_date.isoformat() if c.due_date else "",
                c.detected_at.date().isoformat(),
            ]
        )
    return buf.getvalue()
