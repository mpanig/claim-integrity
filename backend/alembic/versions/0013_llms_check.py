"""llms_check: /llms.txt checks per brand site (AEO content)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llms_check",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organisation_id", sa.Integer, sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brand.id", ondelete="SET NULL")),
        sa.Column("host", sa.String(300), nullable=False, index=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("score", sa.Integer),
        sa.Column("result", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("llms_check")
