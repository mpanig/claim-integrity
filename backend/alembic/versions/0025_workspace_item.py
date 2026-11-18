"""workspace_item: team members, report branding and outreach in one flat table; the old tables stay as views

  row_type 'team'          old table team_member
  row_type 'branding'      old table report_branding
  row_type 'outreach'      old table outreach

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

PARTS = {'team': 'team_member', 'branding': 'report_branding', 'outreach': 'outreach'}


def upgrade() -> None:
    flatten(op.get_bind(), "workspace_item", PARTS)


def downgrade() -> None:
    raise RuntimeError("0025 has no downgrade: restore the pg_dump taken before upgrading")
