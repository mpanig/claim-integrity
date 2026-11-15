"""alert: in-app alerts for new high-risk conflicts and score drops

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Integer,
            sa.ForeignKey("organisation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("sku.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_id", sa.Integer, sa.ForeignKey("conflict.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alert_org_created", "alert", ["organisation_id", "created_at"])
    op.create_index("ix_alert_sku_id", "alert", ["sku_id"])
    op.create_index("ix_alert_conflict_id", "alert", ["conflict_id"])


def downgrade() -> None:
    op.drop_table("alert")
