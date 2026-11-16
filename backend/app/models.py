import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Verdict(str, enum.Enum):
    contradiction = "contradiction"
    risky = "risky"
    outdated = "outdated"
    weaker = "weaker"
    missing = "missing"
    drift = "drift"


SEVERITY: dict[Verdict, int] = {
    Verdict.contradiction: 10,
    Verdict.risky: 9,
    Verdict.outdated: 6,
    Verdict.weaker: 4,
    Verdict.missing: 3,
    Verdict.drift: 1,
}


class ConflictStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    fixed = "fixed"
    verified = "verified"
    dismissed = "dismissed"


def _pg_enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, index: bool = True) -> Any:
    return mapped_column(ForeignKey(target, ondelete="CASCADE"), index=index)


class Organisation(Base):
    __tablename__ = "organisation"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Brand(Base):
    __tablename__ = "brand"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    name: Mapped[str] = mapped_column(String(200))


class Sku(Base):
    __tablename__ = "sku"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id")
    gtin: Mapped[str | None] = mapped_column(String(14))
    name: Mapped[str] = mapped_column(String(300))
    line: Mapped[str | None] = mapped_column(String(200))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    brand: Mapped["Brand"] = relationship()


class Variant(Base):
    __tablename__ = "variant"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    sku_id: Mapped[int] = _fk("sku.id")
    market: Mapped[str] = mapped_column(String(8))
    size: Mapped[str | None] = mapped_column(String(50))
    formula_version: Mapped[str | None] = mapped_column(String(50))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class ApprovedClaim(Base):
    """One approved 'source of truth' value for one field of a SKU."""

    __tablename__ = "approved_claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    sku_id: Mapped[int] = _fk("sku.id")
    field: Mapped[str] = mapped_column(String(50))
    value: Mapped[Any] = mapped_column(JSONB)
    evidence_url: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Page(Base):
    __tablename__ = "page"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    url: Mapped[str] = mapped_column(Text, unique=True)
    source_type: Mapped[str] = mapped_column(String(30))  # e.g. brand, retailer
    retailer: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(2))
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")


class Snapshot(Base):
    __tablename__ = "snapshot"
    __table_args__ = (Index("ix_snapshot_page_fetched", "page_id", "fetched_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    page_id: Mapped[int] = _fk("page.id", index=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    content_hash: Mapped[str] = mapped_column(String(64))
    html: Mapped[str] = mapped_column(Text)

    page: Mapped[Page] = relationship()


class Extraction(Base):
    """Fields read off one snapshot for one SKU: {field: {"value": ..., "quote": "..."}}."""

    __tablename__ = "extraction"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    snapshot_id: Mapped[int] = _fk("snapshot.id")
    sku_id: Mapped[int] = _fk("sku.id")
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    snapshot: Mapped[Snapshot] = relationship()


class Conflict(Base):
    __tablename__ = "conflict"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    sku_id: Mapped[int] = _fk("sku.id")
    page_id: Mapped[int] = _fk("page.id")
    field: Mapped[str] = mapped_column(String(50))
    page_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    truth_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    verdict: Mapped[Verdict] = mapped_column(_pg_enum(Verdict, "verdict"))
    severity: Mapped[int] = mapped_column(Integer)
    status: Mapped[ConflictStatus] = mapped_column(
        _pg_enum(ConflictStatus, "conflict_status"),
        default=ConflictStatus.open,
        server_default=ConflictStatus.open.value,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    dismiss_reason: Mapped[str | None] = mapped_column(Text)

    sku: Mapped[Sku] = relationship()
    page: Mapped[Page] = relationship()


class ScoreSnapshot(Base):
    """Consistency of one SKU at the end of a check run. Feeds the trend charts.

    is_demo marks generated history (seed --demo-history); the UI must label it.
    """

    __tablename__ = "score_snapshot"
    __table_args__ = (Index("ix_score_snapshot_sku_taken", "sku_id", "taken_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id")
    sku_id: Mapped[int] = _fk("sku.id", index=False)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    score: Mapped[int | None] = mapped_column(Integer)
    weighted_severity: Mapped[float] = mapped_column(Float)
    page_weight: Mapped[float] = mapped_column(Float)
    unresolved: Mapped[int] = mapped_column(Integer)
    by_verdict: Mapped[dict[str, int]] = mapped_column(JSONB)
    by_status: Mapped[dict[str, int]] = mapped_column(JSONB)
    mean_days_to_fix: Mapped[float | None] = mapped_column(Float)
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")


class AiPrompt(Base):
    """A question to ask AI assistants about a product or category."""

    __tablename__ = "ai_prompt"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brand.id", ondelete="CASCADE"), index=True)
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiAnswer(Base):
    """What one assistant answered to a prompt, with the product facts it stated.

    stated_facts uses the compare fields plus "contains" (ingredients the answer says are in it).
    """

    __tablename__ = "ai_answer"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    prompt_id: Mapped[int] = _fk("ai_prompt.id")
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), index=True)
    assistant: Mapped[str] = mapped_column(String(100))
    answer: Mapped[str] = mapped_column(Text)
    stated_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    mentioned_brands: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")

    prompt: Mapped[AiPrompt] = relationship()


class Alert(Base):
    """In-app alert: a new high-risk conflict or a score drop. read_at is null while unread."""

    __tablename__ = "alert"
    __table_args__ = (Index("ix_alert_org_created", "organisation_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id", index=False)
    sku_id: Mapped[int] = _fk("sku.id")
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflict.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(30))  # high_risk | score_drop
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sku: Mapped[Sku] = relationship()


class TeamMember(Base):
    """A person who can own issues. No sign-in yet (TODO(auth)); roles are labels only."""

    __tablename__ = "team_member"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(30))  # see app.services.team.ROLES
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brand.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateStatus(str, enum.Enum):
    new = "new"
    relevant = "relevant"
    needs_review = "needs_review"
    rejected = "rejected"


class CollectorRun(Base):
    """One run of the collector agent for a brand (and some of its products)."""

    __tablename__ = "collector_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id")
    sku_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")  # running|done|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget: Mapped[int] = mapped_column(Integer)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    planner: Mapped[str] = mapped_column(String(20), default="templates", server_default="templates")  # templates|claude
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")  # per connector
    found: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    cost: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")


class SourceCandidate(Base):
    """A page, mention or fact the collector found for a brand or product."""

    __tablename__ = "candidate"
    __table_args__ = (Index("ix_candidate_brand_sku", "brand_id", "sku_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id", index=False)
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("collector_run.id", ondelete="SET NULL"), index=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("page.id", ondelete="SET NULL"), index=True)
    connector: Mapped[str] = mapped_column(String(40))
    source_type: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(20))  # page | mention | entity
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    why: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CandidateStatus] = mapped_column(
        _pg_enum(CandidateStatus, "candidate_status"),
        default=CandidateStatus.new,
        server_default=CandidateStatus.new.value,
    )
    relevance_score: Mapped[float | None] = mapped_column(Float)
    relevance_reason: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extracted_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    extraction_method: Mapped[str | None] = mapped_column(String(60))
    fetch_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConnectorSetting(Base):
    """On/off switch per collector connector. Keys stay in the environment, never here."""

    __tablename__ = "connector_setting"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")


class AuditEvent(Base):
    """Who did what, when. Notes are events with action='note'."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_org_at", "organisation_id", "at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id", index=False)
    sku_id: Mapped[int] = _fk("sku.id")
    conflict_id: Mapped[int | None] = mapped_column(
        ForeignKey("conflict.id", ondelete="CASCADE"), index=True, nullable=True
    )
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
