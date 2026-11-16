"""report_branding: white-label settings for reports

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_branding",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organisation_id", sa.Integer, sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("agency_name", sa.String(200)),
        sa.Column("report_title", sa.String(200), nullable=False, server_default="Weekly claim consistency report"),
        sa.Column("primary_color", sa.String(7), nullable=False, server_default="#1f2937"),
        sa.Column("accent_color", sa.String(7), nullable=False, server_default="#2a78d6"),
        sa.Column("logo_data_url", sa.Text),
        sa.Column("footer_text", sa.String(300)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_branding")
