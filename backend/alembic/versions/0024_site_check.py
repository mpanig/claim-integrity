"""site_check: site audits, entity checks, answer grades and llms.txt checks in one flat table; the old tables stay as views

  row_type 'audit_url'     old table audit_url
  row_type 'audit_result'  old table audit_result
  row_type 'entity'        old table entity_check
  row_type 'grade'         old table answer_grade
  row_type 'llms'          old table llms_check

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

PARTS = {'audit_url': 'audit_url', 'audit_result': 'audit_result', 'entity': 'entity_check', 'grade': 'answer_grade', 'llms': 'llms_check'}


def upgrade() -> None:
    flatten(op.get_bind(), "site_check", PARTS)


def downgrade() -> None:
    raise RuntimeError("0024 has no downgrade: restore the pg_dump taken before upgrading")
