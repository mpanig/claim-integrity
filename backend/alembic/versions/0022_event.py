"""event: alerts and issue history in one flat table; the old tables stay as views

  row_type 'alert'         old table alert
  row_type 'audit'         old table audit_event

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

PARTS = {'alert': 'alert', 'audit': 'audit_event'}


def upgrade() -> None:
    flatten(op.get_bind(), "event", PARTS)


def downgrade() -> None:
    raise RuntimeError("0022 has no downgrade: restore the pg_dump taken before upgrading")
