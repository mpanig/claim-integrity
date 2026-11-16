"""LLM answer engine: aliases, competitors, prompt variants, personas, run configs, runs,
and per-answer mentions, claims and citations

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _fk(name: str, target: str, nullable: bool = False, ondelete: str = "CASCADE") -> sa.Column:
    return sa.Column(name, sa.Integer, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer, primary_key=True)


def _ix(table: str, *cols: str) -> None:
    for col in cols:
        op.create_index(f"ix_{table}_{col}", table, [col])


def upgrade() -> None:
    op.add_column("brand", sa.Column("aliases", JSONB, nullable=False, server_default="[]"))
    op.add_column("sku", sa.Column("aliases", JSONB, nullable=False, server_default="[]"))

    op.create_table(
        "competitor",
        _id(),
        _fk("organisation_id", "organisation.id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", JSONB, nullable=False, server_default="[]"),
    )
    _ix("competitor", "organisation_id")

    for col in (
        sa.Column("intent", sa.String(30), nullable=False, server_default="category"),
        sa.Column("funnel_stage", sa.String(20), nullable=False, server_default="consideration"),
        sa.Column("category", sa.String(200)),
        sa.Column("competitor", sa.String(200)),
        sa.Column("retailer", sa.String(200)),
    ):
        op.add_column("ai_prompt", col)

    op.create_table(
        "prompt_variant",
        _id(),
        _fk("prompt_id", "ai_prompt.id"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("text", sa.Text, nullable=False),
    )
    _ix("prompt_variant", "prompt_id")

    op.create_table(
        "persona",
        _id(),
        _fk("organisation_id", "organisation.id"),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("context", sa.Text, nullable=False),
    )
    _ix("persona", "organisation_id")

    op.create_table(
        "run_config",
        _id(),
        _fk("organisation_id", "organisation.id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("budget_usd", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("schedule", sa.String(10), nullable=False, server_default="none"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _ix("run_config", "organisation_id")

    op.create_table(
        "ai_run",
        _id(),
        _fk("organisation_id", "organisation.id"),
        _fk("run_config_id", "run_config.id", nullable=True, ondelete="SET NULL"),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("planned_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("done_calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", JSONB, nullable=False, server_default="[]"),
        sa.Column("errors", JSONB, nullable=False, server_default="[]"),
        sa.Column("budget_usd", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("est_cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("analyser", sa.String(20)),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )
    _ix("ai_run", "organisation_id", "run_config_id")

    for col in (
        _fk("run_id", "ai_run.id", nullable=True, ondelete="SET NULL"),
        _fk("variant_id", "prompt_variant.id", nullable=True, ondelete="SET NULL"),
        _fk("persona_id", "persona.id", nullable=True, ondelete="SET NULL"),
        sa.Column("prompt_text", sa.Text),
        sa.Column("engine", sa.String(20)),
        sa.Column("model_requested", sa.String(100)),
        sa.Column("model_version", sa.String(100)),
        sa.Column("search_enabled", sa.Boolean),
        sa.Column("region", sa.String(10)),
        sa.Column("city", sa.String(100)),
        sa.Column("language", sa.String(10)),
        sa.Column("location_mode", sa.String(20)),
        sa.Column("sample_index", sa.Integer),
        sa.Column("temperature", sa.Float),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Float),
        sa.Column("analyser", sa.String(20)),
        sa.Column("error", sa.Text),
    ):
        op.add_column("ai_answer", col)
    _ix("ai_answer", "run_id")

    op.create_table(
        "answer_mention",
        _id(),
        _fk("answer_id", "ai_answer.id"),
        sa.Column("name", sa.String(200), nullable=False),
        _fk("brand_id", "brand.id", nullable=True),
        _fk("competitor_id", "competitor.id", nullable=True),
        sa.Column("is_own", sa.Boolean, nullable=False),
        sa.Column("position", sa.Integer),
        sa.Column("recommended", sa.Boolean, nullable=False),
        sa.Column("sentiment", sa.Float, nullable=False),
        sa.Column("quote", sa.Text),
    )
    _ix("answer_mention", "answer_id", "brand_id", "competitor_id")

    op.create_table(
        "answer_claim",
        _id(),
        _fk("answer_id", "ai_answer.id"),
        _fk("sku_id", "sku.id"),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("quote", sa.Text),
        sa.Column("verdict", sa.String(20)),
        sa.Column("severity", sa.Integer),
        sa.Column("echo_conflict_ids", JSONB, nullable=False, server_default="[]"),
    )
    _ix("answer_claim", "answer_id", "sku_id")

    op.create_table(
        "answer_citation",
        _id(),
        _fk("answer_id", "ai_answer.id"),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("page_type", sa.String(20), nullable=False),
    )
    _ix("answer_citation", "answer_id")


def downgrade() -> None:
    for table in ("answer_citation", "answer_claim", "answer_mention"):
        op.drop_table(table)
    for col in (
        "error", "analyser", "cost_usd", "output_tokens", "input_tokens", "latency_ms", "temperature",
        "sample_index", "location_mode", "language", "city", "region", "search_enabled", "model_version",
        "model_requested", "engine", "prompt_text", "persona_id", "variant_id", "run_id",
    ):
        op.drop_column("ai_answer", col)
    for table in ("ai_run", "run_config", "persona", "prompt_variant"):
        op.drop_table(table)
    for col in ("retailer", "competitor", "category", "funnel_stage", "intent"):
        op.drop_column("ai_prompt", col)
    op.drop_table("competitor")
    op.drop_column("sku", "aliases")
    op.drop_column("brand", "aliases")
