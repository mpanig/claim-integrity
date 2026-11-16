"""audit: audit_url, audit_result, entity_check

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _fk(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Integer, sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable)


def _json(name: str, default: str) -> sa.Column:
    return sa.Column(name, JSONB, nullable=False, server_default=default)


def upgrade() -> None:
    op.create_table(
        "audit_url",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("organisation_id", "organisation.id"),
        _fk("brand_id", "brand.id"),
        _fk("sku_id", "sku.id", nullable=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
    )
    for col in ("organisation_id", "brand_id", "sku_id"):
        op.create_index(f"ix_audit_url_{col}", "audit_url", [col])

    op.create_table(
        "audit_result",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("audit_url_id", "audit_url.id"),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("note", sa.Text),
        _json("structured", "{}"),
        _json("crawlability", "{}"),
        _json("freshness", "{}"),
    )
    op.create_index("ix_audit_result_audit_url_id", "audit_result", ["audit_url_id"])

    op.create_table(
        "entity_check",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("brand_id", "brand.id"),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("qid", sa.String(20)),
        sa.Column("label", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("wikipedia_url", sa.Text),
        _json("facts", "{}"),
        _json("missing", "[]"),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("note", sa.Text),
    )
    op.create_index("ix_entity_check_brand_id", "entity_check", ["brand_id"])


def downgrade() -> None:
    op.drop_table("entity_check")
    op.drop_table("audit_result")
    op.drop_table("audit_url")
