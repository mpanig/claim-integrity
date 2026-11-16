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
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Attribute keys (app.ai.perception.ATTRIBUTES) the brand wants AI answers to associate with it.
    positioning: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class Sku(Base):
    __tablename__ = "sku"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id")
    gtin: Mapped[str | None] = mapped_column(String(14))
    name: Mapped[str] = mapped_column(String(300))
    line: Mapped[str | None] = mapped_column(String(200))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")

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


class Competitor(Base):
    """A brand we don't track but want to recognise in AI answers (e.g. Cetaphil)."""

    __tablename__ = "competitor"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class AiPrompt(Base):
    """A question to ask AI assistants. `text` is the default wording; variants add more.

    Placeholders filled at run time: {brand} {product} {category} {competitor} {retailer}.
    """

    __tablename__ = "ai_prompt"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brand.id", ondelete="CASCADE"), index=True)
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(30), default="category", server_default="category")
    funnel_stage: Mapped[str] = mapped_column(String(20), default="consideration", server_default="consideration")
    category: Mapped[str | None] = mapped_column(String(200))
    competitor: Mapped[str | None] = mapped_column(String(200))
    retailer: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    variants: Mapped[list["PromptVariant"]] = relationship(cascade="all, delete-orphan", order_by="PromptVariant.id")


class PromptVariant(Base):
    __tablename__ = "prompt_variant"

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = _fk("ai_prompt.id")
    language: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    text: Mapped[str] = mapped_column(Text)


class Persona(Base):
    """Who is asking. Context is added to the prompt; APIs keep no memory of real users."""

    __tablename__ = "persona"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    name: Mapped[str] = mapped_column(String(100))
    context: Mapped[str] = mapped_column(Text)  # e.g. "I'm a new parent with sensitive, dry skin."


class RunConfig(Base):
    """A saved test plan. `config` lists engines/models, search modes, regions, languages,
    persona and prompt ids, and samples per cell. See app.ai.plan.PlanConfig."""

    __tablename__ = "run_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    budget_usd: Mapped[float] = mapped_column(Float, default=5.0, server_default="5.0")
    schedule: Mapped[str] = mapped_column(String(10), default="none", server_default="none")  # none|daily|weekly
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiRun(Base):
    __tablename__ = "ai_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    run_config_id: Mapped[int | None] = mapped_column(ForeignKey("run_config.id", ondelete="SET NULL"), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")  # running|done|failed|stopped
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    budget_usd: Mapped[float] = mapped_column(Float, default=5.0, server_default="5.0")
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    analyser: Mapped[str | None] = mapped_column(String(20))
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")


class AiAnswer(Base):
    """One answer from one engine/model for one cell of a test plan, with everything that shaped it.

    `answer` keeps the raw text. stated_facts / mentioned_brands are kept for older screens.
    """

    __tablename__ = "ai_answer"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    prompt_id: Mapped[int] = _fk("ai_prompt.id")
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), index=True)
    assistant: Mapped[str] = mapped_column(String(100))  # display label, e.g. "OpenAI gpt-4.1"
    answer: Mapped[str] = mapped_column(Text)
    stated_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    mentioned_brands: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")

    run_id: Mapped[int | None] = mapped_column(ForeignKey("ai_run.id", ondelete="SET NULL"), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_variant.id", ondelete="SET NULL"))
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("persona.id", ondelete="SET NULL"))
    prompt_text: Mapped[str | None] = mapped_column(Text)  # exactly what was sent
    engine: Mapped[str | None] = mapped_column(String(20))  # openai | gemini | perplexity | anthropic
    model_requested: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))  # as returned by the API
    search_enabled: Mapped[bool | None] = mapped_column()
    region: Mapped[str | None] = mapped_column(String(10))  # ISO country code
    city: Mapped[str | None] = mapped_column(String(100))
    language: Mapped[str | None] = mapped_column(String(10))
    location_mode: Mapped[str | None] = mapped_column(String(20))  # api | prompt-only | none
    sample_index: Mapped[int | None] = mapped_column(Integer)
    temperature: Mapped[float | None] = mapped_column(Float)  # None = provider default
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    analyser: Mapped[str | None] = mapped_column(String(20))  # anthropic | ollama | rules
    error: Mapped[str | None] = mapped_column(Text)

    prompt: Mapped[AiPrompt] = relationship()
    mentions: Mapped[list["AnswerMention"]] = relationship(cascade="all, delete-orphan")
    claims: Mapped[list["AnswerClaim"]] = relationship(cascade="all, delete-orphan")
    citations: Mapped[list["AnswerCitation"]] = relationship(cascade="all, delete-orphan")


class AnswerMention(Base):
    __tablename__ = "answer_mention"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = _fk("ai_answer.id")
    name: Mapped[str] = mapped_column(String(200))  # canonical brand / competitor name
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brand.id", ondelete="CASCADE"), index=True)
    competitor_id: Mapped[int | None] = mapped_column(ForeignKey("competitor.id", ondelete="CASCADE"), index=True)
    is_own: Mapped[bool] = mapped_column(default=False)  # one of our tracked brands
    position: Mapped[int | None] = mapped_column(Integer)  # rank in a list, 1 = first
    recommended: Mapped[bool] = mapped_column(default=False)
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1 .. 1
    quote: Mapped[str | None] = mapped_column(Text)


class AnswerClaim(Base):
    """A product fact stated in an answer, checked against the truth sheet."""

    __tablename__ = "answer_claim"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = _fk("ai_answer.id")
    sku_id: Mapped[int] = _fk("sku.id")
    field: Mapped[str] = mapped_column(String(30))
    value: Mapped[Any] = mapped_column(JSONB)
    quote: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str | None] = mapped_column(String(20))  # None = matches the truth
    severity: Mapped[int | None] = mapped_column(Integer)
    echo_conflict_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, server_default="[]")


class AnswerCitation(Base):
    __tablename__ = "answer_citation"

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = _fk("ai_answer.id")
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    page_type: Mapped[str] = mapped_column(String(20))  # brand | retailer | review | forum | video | news | reference | other


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


class AuditUrl(Base):
    """A page a user asked us to audit (only these URLs are ever fetched)."""

    __tablename__ = "audit_url"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = _fk("organisation.id")
    brand_id: Mapped[int] = _fk("brand.id")
    sku_id: Mapped[int | None] = mapped_column(ForeignKey("sku.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditResult(Base):
    """One audit of one URL: structured data, AI crawlability, freshness."""

    __tablename__ = "audit_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_url_id: Mapped[int] = _fk("audit_url.id")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20))  # ok | blocked | error
    http_status: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    structured: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    crawlability: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    freshness: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class EntityCheck(Base):
    """How completely a brand is described on Wikidata / Wikipedia (AI models lean on both)."""

    __tablename__ = "entity_check"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = _fk("brand.id")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    qid: Mapped[str | None] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    wikipedia_url: Mapped[str | None] = mapped_column(Text)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    missing: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    score: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text)


class ReportBranding(Base):
    """White-label settings for reports (one row per organisation)."""

    __tablename__ = "report_branding"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(ForeignKey("organisation.id", ondelete="CASCADE"), unique=True)
    agency_name: Mapped[str | None] = mapped_column(String(200))
    report_title: Mapped[str] = mapped_column(String(200), default="Weekly claim consistency report", server_default="Weekly claim consistency report")
    primary_color: Mapped[str] = mapped_column(String(7), default="#1f2937", server_default="#1f2937")
    accent_color: Mapped[str] = mapped_column(String(7), default="#2a78d6", server_default="#2a78d6")
    logo_data_url: Mapped[str | None] = mapped_column(Text)  # data:image/png;base64,...
    footer_text: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JobRun(Base):
    """One pass of a background job (the worker), so the app can show when jobs last ran."""

    __tablename__ = "job_run"
    __table_args__ = (Index("ix_job_run_name_started", "name", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40))  # product_checks | ai_plans
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running", server_default="running")  # running|done|failed
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


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
