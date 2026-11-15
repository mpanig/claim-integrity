"""Alerts raised by a check run.

- every new contradiction or unapproved (risky) claim
- a score drop of SCORE_DROP points or more since the previous real snapshot

TODO(notify): deliver alerts by email / Slack per user settings; in-app only for now.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, Conflict, Page, ScoreSnapshot, Sku, Verdict

SCORE_DROP = 5
HIGH_RISK = (Verdict.contradiction, Verdict.risky)
_WHAT = {Verdict.contradiction: "A claim contradicted by its own ingredients", Verdict.risky: "An unapproved claim"}


def _value(v) -> str:
    if isinstance(v, dict):
        return str(v.get("claim") or "")
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


def alerts_for_run(session: Session, sku: Sku, new: list[Conflict], snapshot: ScoreSnapshot) -> list[Alert]:
    out = []
    for c in new:
        if c.verdict not in HIGH_RISK:
            continue
        page = session.get(Page, c.page_id)
        where = page.retailer or page.url if page else "a page"
        out.append(
            Alert(
                organisation_id=sku.organisation_id,
                sku_id=sku.id,
                conflict_id=c.id,
                kind="high_risk",
                title=f"{_WHAT[c.verdict]} on {where}",
                body=f"{where} shows “{_value(c.page_value)}” for {sku.name}.",
            )
        )

    previous = session.scalar(
        select(ScoreSnapshot.score)
        .where(
            ScoreSnapshot.sku_id == sku.id,
            ScoreSnapshot.is_demo.is_(False),
            ScoreSnapshot.id != snapshot.id,
            ScoreSnapshot.score.is_not(None),
        )
        .order_by(ScoreSnapshot.taken_at.desc(), ScoreSnapshot.id.desc())
        .limit(1)
    )
    if previous is not None and snapshot.score is not None and previous - snapshot.score >= SCORE_DROP:
        out.append(
            Alert(
                organisation_id=sku.organisation_id,
                sku_id=sku.id,
                kind="score_drop",
                title=f"{sku.name} score fell {previous - snapshot.score} points",
                body=f"Consistency score went from {previous} to {snapshot.score} after the latest check.",
            )
        )
    session.add_all(out)
    return out
