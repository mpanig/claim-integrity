"""run_log: AI test runs and background job runs in one flat table; the old tables stay as views

  row_type 'ai_run'        old table ai_run
  row_type 'job'           old table job_run

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

PARTS = {'ai_run': 'ai_run', 'job': 'job_run'}


def upgrade() -> None:
    flatten(op.get_bind(), "run_log", PARTS)


def downgrade() -> None:
    raise RuntimeError("0023 has no downgrade: restore the pg_dump taken before upgrading")
