"""answer_grade: page answer-readiness grades (AEO content)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "answer_grade",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organisation_id", sa.Integer, sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brand.id", ondelete="SET NULL")),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("sku.id", ondelete="SET NULL")),
        sa.Column("url", sa.Text, nullable=False, index=True),
        sa.Column("graded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("title", sa.Text),
        sa.Column("score", sa.Integer),
        sa.Column("checks", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("answer_grade")
