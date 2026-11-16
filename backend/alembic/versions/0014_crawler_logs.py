"""crawler_logs: uploaded logs and aggregated AI crawler hits

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "log_upload",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organisation_id", sa.Integer, sa.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="crawler"),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lines", sa.Integer, nullable=False, server_default="0"),
        sa.Column("matched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_day", sa.Date),
        sa.Column("last_day", sa.Date),
        sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_table(
        "crawler_hit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("upload_id", sa.Integer, sa.ForeignKey("log_upload.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("day", sa.Date, nullable=False, index=True),
        sa.Column("bot", sa.String(50), nullable=False, index=True),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("hits", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("crawler_hit")
    op.drop_table("log_upload")
