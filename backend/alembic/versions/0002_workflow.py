"""conflict workflow: owner, due date, dismiss reason, audit log, sku last checked

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sku", sa.Column("last_checked_at", sa.DateTime(timezone=True)))
    op.add_column("conflict", sa.Column("status_changed_at", sa.DateTime(timezone=True)))
    op.add_column("conflict", sa.Column("owner", sa.String(200)))
    op.add_column("conflict", sa.Column("due_date", sa.Date))
    op.add_column("conflict", sa.Column("dismiss_reason", sa.Text))

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Integer,
            sa.ForeignKey("organisation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("sku.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_id", sa.Integer, sa.ForeignKey("conflict.id", ondelete="CASCADE")),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_event_org_at", "audit_event", ["organisation_id", "at"])
    op.create_index("ix_audit_event_sku_id", "audit_event", ["sku_id"])
    op.create_index("ix_audit_event_conflict_id", "audit_event", ["conflict_id"])


def downgrade() -> None:
    op.drop_table("audit_event")
    for col in ("dismiss_reason", "due_date", "owner", "status_changed_at"):
        op.drop_column("conflict", col)
    op.drop_column("sku", "last_checked_at")
