"""add banners, promotions, and saved cards

Revision ID: c4a91e2b7f10
Revises: 8db00fd75200
Create Date: 2026-09-26 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4a91e2b7f10"
down_revision: Union[str, None] = "8db00fd75200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "banners",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("placement", sa.String(length=40), nullable=False),
        sa.Column("cta_label", sa.String(length=80), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("action_target", sa.String(length=500), nullable=True),
        sa.Column("badge_text", sa.String(length=40), nullable=True),
        sa.Column("background_color", sa.String(length=20), nullable=True),
        sa.Column("accent_color", sa.String(length=20), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("audience", sa.String(length=20), nullable=False, server_default="all"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impression_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_banners_slug"), "banners", ["slug"], unique=True)
    op.create_index(op.f("ix_banners_placement"), "banners", ["placement"], unique=False)
    op.create_index(op.f("ix_banners_priority"), "banners", ["priority"], unique=False)
    op.create_index(op.f("ix_banners_is_active"), "banners", ["is_active"], unique=False)

    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("badge", sa.String(length=40), nullable=True),
        sa.Column("promo_type", sa.String(length=40), nullable=False),
        sa.Column("highlight_value", sa.String(length=80), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("category_slug", sa.String(length=80), nullable=True),
        sa.Column("cta_label", sa.String(length=80), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("action_target", sa.String(length=500), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impression_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promotions_slug"), "promotions", ["slug"], unique=True)
    op.create_index(op.f("ix_promotions_promo_type"), "promotions", ["promo_type"], unique=False)
    op.create_index(op.f("ix_promotions_card_id"), "promotions", ["card_id"], unique=False)
    op.create_index(op.f("ix_promotions_category_slug"), "promotions", ["category_slug"], unique=False)
    op.create_index(op.f("ix_promotions_priority"), "promotions", ["priority"], unique=False)
    op.create_index(op.f("ix_promotions_is_featured"), "promotions", ["is_featured"], unique=False)
    op.create_index(op.f("ix_promotions_is_active"), "promotions", ["is_active"], unique=False)

    op.create_table(
        "saved_cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "card_id", name="uq_saved_card"),
    )
    op.create_index(op.f("ix_saved_cards_user_id"), "saved_cards", ["user_id"], unique=False)
    op.create_index(op.f("ix_saved_cards_card_id"), "saved_cards", ["card_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_saved_cards_card_id"), table_name="saved_cards")
    op.drop_index(op.f("ix_saved_cards_user_id"), table_name="saved_cards")
    op.drop_table("saved_cards")
    op.drop_index(op.f("ix_promotions_is_active"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_is_featured"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_priority"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_category_slug"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_card_id"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_promo_type"), table_name="promotions")
    op.drop_index(op.f("ix_promotions_slug"), table_name="promotions")
    op.drop_table("promotions")
    op.drop_index(op.f("ix_banners_is_active"), table_name="banners")
    op.drop_index(op.f("ix_banners_priority"), table_name="banners")
    op.drop_index(op.f("ix_banners_placement"), table_name="banners")
    op.drop_index(op.f("ix_banners_slug"), table_name="banners")
    op.drop_table("banners")
