"""Add content scheduling publish_at column."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_users_scheduling"
down_revision = "0002_modular_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_content_items_publish_at", "content_items", ["publish_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_items_publish_at", table_name="content_items")
    op.drop_column("content_items", "publish_at")
