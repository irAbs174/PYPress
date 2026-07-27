"""Modular CMS foundation schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_modular_foundation"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=True)

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
    )
    op.create_index("ix_tags_name", "tags", ["name"], unique=True)
    op.create_index("ix_tags_slug", "tags", ["slug"], unique=True)

    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.create_index("ix_site_settings_key", "site_settings", ["key"], unique=True)

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_media_assets_filename", "media_assets", ["filename"], unique=True)

    op.add_column("content_items", sa.Column("excerpt", sa.Text(), nullable=True))
    op.add_column("content_items", sa.Column("meta_title", sa.String(length=255), nullable=True))
    op.add_column("content_items", sa.Column("meta_description", sa.String(length=512), nullable=True))
    op.add_column("content_items", sa.Column("author_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_content_items_author_id_users",
        "content_items",
        "users",
        ["author_id"],
        ["id"],
    )
    op.create_index("ix_content_items_author_id", "content_items", ["author_id"], unique=False)

    op.create_table(
        "content_categories",
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "content_tags",
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("content_tags")
    op.drop_table("content_categories")
    op.drop_index("ix_content_items_author_id", table_name="content_items")
    op.drop_constraint("fk_content_items_author_id_users", "content_items", type_="foreignkey")
    op.drop_column("content_items", "author_id")
    op.drop_column("content_items", "meta_description")
    op.drop_column("content_items", "meta_title")
    op.drop_column("content_items", "excerpt")
    op.drop_index("ix_media_assets_filename", table_name="media_assets")
    op.drop_table("media_assets")
    op.drop_index("ix_site_settings_key", table_name="site_settings")
    op.drop_table("site_settings")
    op.drop_index("ix_tags_slug", table_name="tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
