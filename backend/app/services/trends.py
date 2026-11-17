"""Score history: a snapshot per SKU on every check run, aggregated by week for charts."""

import random
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conflict, ConflictStatus, ScoreSnapshot, Sku, Verdict
from app.pipeline.compare import COMPARED_FIELDS
from app.services.scoring import MAX_SEVERITY, Tally, drift, score, sku_tallies


def mean_days_to_fix(session: Session, sku_ids: list[int]) -> float | None:
    """Average days from detection to verified fix."""
    rows = session.execute(
        select(Conflict.detected_at, Conflict.status_changed_at).where(
            Conflict.sku_id.in_(sku_ids),
            Conflict.status == ConflictStatus.verified,
            Conflict.status_changed_at.is_not(None),
        )
    ).all()
    if not rows:
        return None
    return round(sum((done - found).total_seconds() for found, done in rows) / len(rows) / 86400, 1)


def status_counts(session: Session, sku_ids: list[int]) -> dict[str, int]:
    counts = {s.value: 0 for s in ConflictStatus}
    for status, n in session.execute(
        select(Conflict.status, func.count()).where(Conflict.sku_id.in_(sku_ids)).group_by(Conflict.status)
    ):
        counts[status.value] = n
    return counts


def take_snapshot(session: Session, sku: Sku) -> ScoreSnapshot:
    session.flush()
    tally = sku_tallies(session, [sku.id]).get(sku.id) or Tally()
    snap = ScoreSnapshot(
        organisation_id=sku.organisation_id,
        brand_id=sku.brand_id,
        sku_id=sku.id,
        score=tally.score,
        weighted_severity=tally.weighted_severity,
        page_weight=tally.page_weight,
        unresolved=tally.unresolved,
        by_verdict=tally.by_verdict,
        by_status=status_counts(session, [sku.id]),
        mean_days_to_fix=mean_days_to_fix(session, [sku.id]),
    )
    session.add(snap)
    return snap


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_trends(session: Session, skus: list[Sku], weeks: int, today: date | None = None) -> dict[str, Any]:
    """One point per week: each SKU's last snapshot before the week ended, summed."""
    today = today or datetime.now(UTC).date()
    starts = [week_start(today) - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    sku_ids = [s.id for s in skus]
    snaps = session.scalars(
        select(ScoreSnapshot).where(ScoreSnapshot.sku_id.in_(sku_ids)).order_by(ScoreSnapshot.taken_at, ScoreSnapshot.id)
    ).all()
    by_sku: dict[int, list[ScoreSnapshot]] = defaultdict(list)
    for s in snaps:
        by_sku[s.sku_id].append(s)

    brand_names = {s.brand_id: s.brand.name for s in skus}
    points, demo = [], False
    prev_verified: int | None = None
    for start in starts:
        end = datetime.combine(start + timedelta(days=7), datetime.min.time(), tzinfo=UTC)
        ws = pw = 0.0
        unresolved = verified = 0
        fix_days: list[float] = []
        brand: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        seen = False
        for sku_id, history in by_sku.items():
            last = next((s for s in reversed(history) if s.taken_at < end), None)
            if last is None:
                continue
            seen = True
            demo = demo or last.is_demo
            ws += last.weighted_severity
            pw += last.page_weight
            unresolved += last.unresolved
            verified += last.by_status.get("verified", 0)
            if last.mean_days_to_fix is not None:
                fix_days.append(last.mean_days_to_fix)
            brand[last.brand_id][0] += last.weighted_severity
            brand[last.brand_id][1] += last.page_weight
        fixed = None
        if seen:
            # Verified fixes this week = growth of the running total (never negative).
            fixed = max(0, verified - prev_verified) if prev_verified is not None else 0
            prev_verified = verified
        points.append(
            {
                "week": start.isoformat(),
                "score": score(ws, pw) if seen else None,
                "drift_score": drift(score(ws, pw)) if seen else None,
                "unresolved": unresolved if seen else None,
                "verified": verified if seen else None,
                "fixed": fixed,
                "mean_days_to_fix": round(sum(fix_days) / len(fix_days), 1) if fix_days else None,
                "brands": {str(b): score(v[0], v[1]) for b, v in brand.items()},
                "drift_brands": {str(b): drift(score(v[0], v[1])) for b, v in brand.items()},
            }
        )
    return {
        "demo": demo,
        "weeks": points,
        "brands": [{"id": b, "name": n} for b, n in sorted(brand_names.items(), key=lambda kv: kv[0])],
    }


def generate_demo_history(session: Session, weeks: int = 12) -> int:
    """Write `weeks` weekly demo snapshots per SKU ending last week, trending toward today.

    Every row is marked is_demo=True so the UI can label it. Returns rows written.
    """
    session.execute(ScoreSnapshot.__table__.delete().where(ScoreSnapshot.is_demo.is_(True)))
    now = datetime.now(UTC)
    skus = session.scalars(select(Sku)).all()
    tallies = sku_tallies(session, [s.id for s in skus])
    written = 0
    for sku in skus:
        tally = tallies.get(sku.id) or Tally()
        if tally.page_weight <= 0:
            continue
        rng = random.Random(sku.id)
        worst = MAX_SEVERITY * len(COMPARED_FIELDS) * tally.page_weight
        current = tally.score if tally.score is not None else 100
        start_score = max(5, current - rng.randint(15, 30))
        verified = 0
        for i in range(weeks):
            t = i / max(1, weeks - 1)
            s = round(start_score + (current - start_score) * t + rng.uniform(-4, 4))
            s = min(100, max(0, s))
            unresolved = max(tally.unresolved, round(tally.unresolved * (1.8 - 0.8 * t) + rng.uniform(-1, 1)))
            verified += rng.randint(0, 3)  # running total, so it only grows
            session.add(
                ScoreSnapshot(
                    organisation_id=sku.organisation_id,
                    brand_id=sku.brand_id,
                    sku_id=sku.id,
                    taken_at=now - timedelta(weeks=weeks - i),
                    score=s,
                    weighted_severity=worst * (1 - s / 100),
                    page_weight=tally.page_weight,
                    unresolved=unresolved,
                    by_verdict={v.value: 0 for v in Verdict},
                    by_status={"open": unresolved, "verified": verified},
                    mean_days_to_fix=round(14 - 8 * t + rng.uniform(-1.5, 1.5), 1),
                    is_demo=True,
                )
            )
            written += 1
    session.commit()
    return written
