"""Drift score (shown to users) and the consistency value it is derived from.

score = 100 * (1 - weighted_severity / max_weighted_severity)    stored and computed (100 = no drift)
drift = 100 - score                                                shown everywhere (0 = no drift)

weighted_severity      sum of severity x page weight over unresolved conflicts
                       (open, accepted, fixed; dismissed and verified do not count)
max_weighted_severity  10 x number of compared fields x sum of weights of the pages
                       checked for the SKU

A SKU with no checked pages has no score (None).
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conflict, ConflictStatus, Extraction, Page, Snapshot, Verdict
from app.pipeline.compare import COMPARED_FIELDS

UNRESOLVED = (ConflictStatus.open, ConflictStatus.accepted, ConflictStatus.fixed)
MAX_SEVERITY = 10


@dataclass
class Tally:
    weighted_severity: float = 0.0
    page_weight: float = 0.0
    pages: int = 0
    unresolved: int = 0
    by_verdict: dict[str, int] = field(default_factory=lambda: {v.value: 0 for v in Verdict})

    def add(self, other: "Tally") -> None:
        self.weighted_severity += other.weighted_severity
        self.page_weight += other.page_weight
        self.pages += other.pages
        self.unresolved += other.unresolved
        for k, v in other.by_verdict.items():
            self.by_verdict[k] += v

    @property
    def score(self) -> int | None:
        return score(self.weighted_severity, self.page_weight)


def drift(consistency: int | None) -> int | None:
    """Drift score shown to users: 0 = every page matches the truth, 100 = worst possible."""
    return None if consistency is None else 100 - consistency


def score(weighted_severity: float, page_weight: float) -> int | None:
    if page_weight <= 0:
        return None
    worst = MAX_SEVERITY * len(COMPARED_FIELDS) * page_weight
    return max(0, round(100 * (1 - weighted_severity / worst)))


def sku_tallies(session: Session, sku_ids: list[int] | None = None) -> dict[int, Tally]:
    tallies: dict[int, Tally] = defaultdict(Tally)

    pages = (
        select(Extraction.sku_id, Page.id, Page.weight)
        .join(Snapshot, Extraction.snapshot_id == Snapshot.id)
        .join(Page, Snapshot.page_id == Page.id)
        .distinct()
    )
    conflicts = (
        select(Conflict.sku_id, Conflict.verdict, func.count(), func.sum(Conflict.severity * Page.weight))
        .join(Page, Conflict.page_id == Page.id)
        .where(Conflict.status.in_(UNRESOLVED))
        .group_by(Conflict.sku_id, Conflict.verdict)
    )
    if sku_ids is not None:
        pages = pages.where(Extraction.sku_id.in_(sku_ids))
        conflicts = conflicts.where(Conflict.sku_id.in_(sku_ids))

    for sku_id, _page_id, weight in session.execute(pages):
        tallies[sku_id].page_weight += weight
        tallies[sku_id].pages += 1
    for sku_id, verdict, count, weighted in session.execute(conflicts):
        t = tallies[sku_id]
        t.unresolved += count
        t.by_verdict[verdict.value] += count
        t.weighted_severity += float(weighted or 0)
    return tallies
