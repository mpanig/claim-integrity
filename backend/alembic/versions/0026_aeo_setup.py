"""aeo_setup: AI prompts, prompt variants, personas, competitors and saved test plans in one flat table; the old tables stay as views

  row_type 'prompt'        old table ai_prompt
  row_type 'variant'       old table prompt_variant
  row_type 'persona'       old table persona
  row_type 'competitor'    old table competitor
  row_type 'plan'          old table run_config

Rows keep their ids; row_type says which old table a row belongs to. See app/db_flatten.py.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-18

No downgrade: restore the pg_dump taken before this step (docs/agents/tables.md, "Migrate").
"""
from alembic import op

from app.db_flatten import flatten

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

PARTS = {'prompt': 'ai_prompt', 'variant': 'prompt_variant', 'persona': 'persona', 'competitor': 'competitor', 'plan': 'run_config'}


def upgrade() -> None:
    flatten(op.get_bind(), "aeo_setup", PARTS)


def downgrade() -> None:
    raise RuntimeError("0026 has no downgrade: restore the pg_dump taken before upgrading")
