"""core tables

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

VERDICTS = ("contradiction", "risky", "outdated", "weaker", "missing", "drift")
STATUSES = ("open", "accepted", "fixed", "verified", "dismissed")


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer, primary_key=True)


def _fk(name: str, target: str) -> sa.Column:
    return sa.Column(name, sa.Integer, sa.ForeignKey(target, ondelete="CASCADE"), nullable=False)


def _org() -> sa.Column:
    return _fk("organisation_id", "organisation.id")


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    verdict = ENUM(*VERDICTS, name="verdict", create_type=False)
    status = ENUM(*STATUSES, name="conflict_status", create_type=False)
    verdict.create(op.get_bind())
    status.create(op.get_bind())

    op.create_table(
        "organisation",
        _id(),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        _now("created_at"),
    )
    op.create_table(
        "brand",
        _id(),
        _org(),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "sku",
        _id(),
        _org(),
        _fk("brand_id", "brand.id"),
        sa.Column("gtin", sa.String(14)),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("line", sa.String(200)),
    )
    op.create_table(
        "variant",
        _id(),
        _org(),
        _fk("sku_id", "sku.id"),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("size", sa.String(50)),
        sa.Column("formula_version", sa.String(50)),
        sa.Column("valid_from", sa.Date),
        sa.Column("valid_to", sa.Date),
    )
    op.create_table(
        "approved_claim",
        _id(),
        _org(),
        _fk("sku_id", "sku.id"),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("evidence_url", sa.Text),
        sa.Column("approved_by", sa.String(200)),
        _now("created_at"),
    )
    op.create_table(
        "page",
        _id(),
        _org(),
        sa.Column("url", sa.Text, nullable=False, unique=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("retailer", sa.String(100)),
        sa.Column("country", sa.String(2)),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
    )
    op.create_table(
        "snapshot",
        _id(),
        _org(),
        _fk("page_id", "page.id"),
        _now("fetched_at"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("html", sa.Text, nullable=False),
    )
    op.create_index("ix_snapshot_page_fetched", "snapshot", ["page_id", "fetched_at"])
    op.create_table(
        "extraction",
        _id(),
        _org(),
        _fk("snapshot_id", "snapshot.id"),
        _fk("sku_id", "sku.id"),
        sa.Column("fields", JSONB, nullable=False),
        _now("created_at"),
    )
    op.create_table(
        "conflict",
        _id(),
        _org(),
        _fk("sku_id", "sku.id"),
        _fk("page_id", "page.id"),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("page_value", JSONB),
        sa.Column("truth_value", JSONB),
        sa.Column("verdict", verdict, nullable=False),
        sa.Column("severity", sa.Integer, nullable=False),
        sa.Column("status", status, nullable=False, server_default="open"),
        _now("detected_at"),
    )

    # Index every foreign key (snapshot.page_id is covered by ix_snapshot_page_fetched).
    fks = {
        "brand": ["organisation_id"],
        "sku": ["organisation_id", "brand_id"],
        "variant": ["organisation_id", "sku_id"],
        "approved_claim": ["organisation_id", "sku_id"],
        "page": ["organisation_id"],
        "snapshot": ["organisation_id"],
        "extraction": ["organisation_id", "snapshot_id", "sku_id"],
        "conflict": ["organisation_id", "sku_id", "page_id"],
    }
    for table, cols in fks.items():
        for col in cols:
            op.create_index(f"ix_{table}_{col}", table, [col])


def downgrade() -> None:
    for table in (
        "conflict",
        "extraction",
        "snapshot",
        "page",
        "approved_claim",
        "variant",
        "sku",
        "brand",
        "organisation",
    ):
        op.drop_table(table)
    sa.Enum(name="conflict_status").drop(op.get_bind())
    sa.Enum(name="verdict").drop(op.get_bind())
