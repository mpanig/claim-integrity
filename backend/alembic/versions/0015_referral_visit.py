"""referral_visit: AI referral sessions imported from analytics CSV

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_visit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("upload_id", sa.Integer, sa.ForeignKey("log_upload.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("day", sa.Date, nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False, index=True),
        sa.Column("landing", sa.Text, nullable=False, server_default=""),
        sa.Column("sessions", sa.Integer, nullable=False),
        sa.Column("conversions", sa.Float, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("referral_visit")
