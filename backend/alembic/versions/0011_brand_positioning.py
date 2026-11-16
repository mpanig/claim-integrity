"""brand_positioning: intended attributes per brand (AEO brand perception)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brand", sa.Column("positioning", JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("brand", "positioning")
