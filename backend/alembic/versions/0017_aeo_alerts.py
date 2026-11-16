"""aeo_alerts: brand-level alerts (sku optional), link, dedupe key, demo flag

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("alert", "sku_id", existing_type=sa.Integer, nullable=True)
    op.add_column("alert", sa.Column("brand_id", sa.Integer, sa.ForeignKey("brand.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_alert_brand_id", "alert", ["brand_id"])
    op.add_column("alert", sa.Column("link", sa.Text, nullable=True))
    op.add_column("alert", sa.Column("key", sa.String(300), nullable=True))
    op.create_index("ix_alert_key", "alert", ["key"])
    op.add_column("alert", sa.Column("is_demo", sa.Boolean, nullable=False, server_default="false"))


def downgrade() -> None:
    op.execute("DELETE FROM alert WHERE sku_id IS NULL")
    op.drop_column("alert", "is_demo")
    op.drop_index("ix_alert_key", table_name="alert")
    op.drop_column("alert", "key")
    op.drop_column("alert", "link")
    op.drop_index("ix_alert_brand_id", table_name="alert")
    op.drop_column("alert", "brand_id")
    op.alter_column("alert", "sku_id", existing_type=sa.Integer, nullable=False)
