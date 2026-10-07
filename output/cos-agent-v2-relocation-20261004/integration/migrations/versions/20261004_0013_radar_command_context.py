"""Persist the immutable Command Layer receipt alongside each CoS proposal."""

import sqlalchemy as sa
from alembic import op

revision = "20261004_0013"
down_revision = "20260927_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pending_radar_operations", sa.Column("execution_context", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("pending_radar_operations", "execution_context")
