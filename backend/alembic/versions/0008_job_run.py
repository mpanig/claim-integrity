"""job_run: last runs of background jobs

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_run",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_job_run_name_started", "job_run", ["name", "started_at"])


def downgrade() -> None:
    op.drop_table("job_run")
