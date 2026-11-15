"""ai_prompt and ai_answer: what AI assistants say about products

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _fk(name: str, target: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Integer, sa.ForeignKey(target, ondelete="CASCADE"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "ai_prompt",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("organisation_id", "organisation.id"),
        _fk("brand_id", "brand.id", nullable=True),
        _fk("sku_id", "sku.id", nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ai_answer",
        sa.Column("id", sa.Integer, primary_key=True),
        _fk("organisation_id", "organisation.id"),
        _fk("prompt_id", "ai_prompt.id"),
        _fk("sku_id", "sku.id", nullable=True),
        sa.Column("assistant", sa.String(100), nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("stated_facts", JSONB, nullable=False, server_default="{}"),
        sa.Column("mentioned_brands", JSONB, nullable=False, server_default="[]"),
        sa.Column("asked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )
    for table, cols in {
        "ai_prompt": ["organisation_id", "brand_id", "sku_id"],
        "ai_answer": ["organisation_id", "prompt_id", "sku_id"],
    }.items():
        for col in cols:
            op.create_index(f"ix_{table}_{col}", table, [col])


def downgrade() -> None:
    op.drop_table("ai_answer")
    op.drop_table("ai_prompt")
