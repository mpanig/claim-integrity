"""inferred_truth: provisional truth for products without a truth sheet; conflict.truth_source

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inferred_truth",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("sku.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("fields", JSONB, nullable=False, server_default="{}"),
        sa.Column("agreement", JSONB, nullable=False, server_default="{}"),
        sa.Column("method", sa.String(20), nullable=False, server_default="majority"),
        sa.Column("sources", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("conflict", sa.Column("truth_source", sa.String(20), nullable=False, server_default="approved"))


def downgrade() -> None:
    op.drop_column("conflict", "truth_source")
    op.drop_table("inferred_truth")
