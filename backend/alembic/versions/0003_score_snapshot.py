"""score_snapshot: consistency history per SKU, written on every check run

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Integer,
            sa.ForeignKey("organisation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("sku.id", ondelete="CASCADE"), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("score", sa.Integer),
        sa.Column("weighted_severity", sa.Float, nullable=False),
        sa.Column("page_weight", sa.Float, nullable=False),
        sa.Column("unresolved", sa.Integer, nullable=False),
        sa.Column("by_verdict", JSONB, nullable=False),
        sa.Column("by_status", JSONB, nullable=False),
        sa.Column("mean_days_to_fix", sa.Float),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_score_snapshot_sku_taken", "score_snapshot", ["sku_id", "taken_at"])
    op.create_index("ix_score_snapshot_organisation_id", "score_snapshot", ["organisation_id"])
    op.create_index("ix_score_snapshot_brand_id", "score_snapshot", ["brand_id"])


def downgrade() -> None:
    op.drop_table("score_snapshot")
