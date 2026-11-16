"""collector: collector_run, candidate, connector_setting

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

STATUSES = ("new", "relevant", "needs_review", "rejected")


def _fk(name: str, target: str, nullable: bool = False, ondelete: str = "CASCADE") -> sa.Column:
    return sa.Column(name, sa.Integer, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def _json(name: str, default: str) -> sa.Column:
    return sa.Column(name, JSONB, nullable=False, server_default=default)


def upgrade() -> None:
    status = ENUM(*STATUSES, name="candidate_status", create_type=False)
    status.create(op.get_bind())

    op.create_table(
        "collector_run",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("organisation_id", "organisation.id"),
        _fk("brand_id", "brand.id"),
        _json("sku_ids", "[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("budget", sa.Integer, nullable=False),
        sa.Column("requests_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("planner", sa.String(20), nullable=False, server_default="templates"),
        _json("stats", "{}"),
        sa.Column("found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fetched", sa.Integer, nullable=False, server_default="0"),
        _json("skipped", "[]"),
        _json("errors", "[]"),
        _json("cost", "{}"),
        _json("log", "[]"),
    )
    op.create_index("ix_collector_run_organisation_id", "collector_run", ["organisation_id"])
    op.create_index("ix_collector_run_brand_id", "collector_run", ["brand_id"])

    op.create_table(
        "candidate",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("organisation_id", "organisation.id"),
        _fk("brand_id", "brand.id"),
        _fk("sku_id", "sku.id", nullable=True),
        _fk("run_id", "collector_run.id", nullable=True, ondelete="SET NULL"),
        _fk("page_id", "page.id", nullable=True, ondelete="SET NULL"),
        sa.Column("connector", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("canonical_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("why", sa.Text),
        sa.Column("snippet", sa.Text),
        sa.Column("status", status, nullable=False, server_default="new"),
        sa.Column("relevance_score", sa.Float),
        sa.Column("relevance_reason", sa.Text),
        sa.Column("data", JSONB),
        _json("extracted_fields", "[]"),
        sa.Column("extraction_method", sa.String(60)),
        sa.Column("fetch_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_candidate_brand_sku", "candidate", ["brand_id", "sku_id"])
    op.create_index("ix_candidate_organisation_id", "candidate", ["organisation_id"])
    op.create_index("ix_candidate_run_id", "candidate", ["run_id"])
    op.create_index("ix_candidate_page_id", "candidate", ["page_id"])
    op.create_index("ix_candidate_canonical_url", "candidate", ["canonical_url"])

    op.create_table(
        "connector_setting",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_table("connector_setting")
    op.drop_table("candidate")
    op.drop_table("collector_run")
    sa.Enum(name="candidate_status").drop(op.get_bind())
