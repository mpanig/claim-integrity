"""team_member: people and roles (no auth yet)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_member",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "organisation_id",
            sa.Integer,
            sa.ForeignKey("organisation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brand.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_team_member_organisation_id", "team_member", ["organisation_id"])
    op.create_index("ix_team_member_brand_id", "team_member", ["brand_id"])


def downgrade() -> None:
    op.drop_table("team_member")
