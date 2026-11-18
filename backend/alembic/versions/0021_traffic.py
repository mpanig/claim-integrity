"""traffic: AI crawler log and AI referral uploads in one flat table; the old tables stay as views

  row_type 'upload'        old table log_upload
  row_type 'crawler'       old table crawler_hit
  row_type 'referral'      old table referral_visit

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

PARTS = {'upload': 'log_upload', 'crawler': 'crawler_hit', 'referral': 'referral_visit'}


def upgrade() -> None:
    flatten(op.get_bind(), "traffic", PARTS)


def downgrade() -> None:
    raise RuntimeError("0021 has no downgrade: restore the pg_dump taken before upgrading")
