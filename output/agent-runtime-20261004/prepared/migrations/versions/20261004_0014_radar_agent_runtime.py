"""Durable product runtime, independent of the Telegram and simulation ledgers."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0014"
down_revision = "20261004_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "radar_agent_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("identity", sa.JSON(), nullable=False),
        sa.Column("context_hash", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("radar_agent_runs")
