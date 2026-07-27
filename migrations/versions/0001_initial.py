"""Initial PYpress schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_content_items_slug", "content_items", ["slug"], unique=True)
    op.create_index("ix_content_items_title", "content_items", ["title"], unique=False)
    op.create_index("ix_content_items_content_type", "content_items", ["content_type"], unique=False)
    op.create_index("ix_content_items_status", "content_items", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_items_status", table_name="content_items")
    op.drop_index("ix_content_items_content_type", table_name="content_items")
    op.drop_index("ix_content_items_title", table_name="content_items")
    op.drop_index("ix_content_items_slug", table_name="content_items")
    op.drop_table("content_items")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
