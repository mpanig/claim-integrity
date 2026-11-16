"""outreach: citation outreach tracker (AEO citations)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organisation_id", sa.Integer, sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("domain", sa.String(300), nullable=False, index=True),
        sa.Column("page_url", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="to_contact"),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("team_member.id", ondelete="SET NULL")),
        sa.Column("note", sa.Text),
        sa.Column("due_date", sa.Date),
        sa.Column("published_url", sa.Text),
        sa.Column("gap_citations", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("outreach")
