"""add sms expense tracking tables and user_cards anniversary_month

Revision ID: f1e2d3c4b5a6
Revises: a7c3e91b4d20
Create Date: 2026-10-18 20:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, None] = "a7c3e91b4d20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Merchants dictionary
    op.create_table(
        "merchants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("mcc", sa.String(length=4), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_merchants_canonical_name", "merchants", ["canonical_name"])
    op.create_index("ix_merchants_category", "merchants", ["category"])

    # 2. Card Transactions
    op.create_table(
        "card_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_hash", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("amount_inr", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="debit"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bank_code", sa.String(length=30), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("user_card_id", sa.Integer(), nullable=True),
        sa.Column("merchant_raw", sa.Text(), nullable=True),
        sa.Column("merchant_id", sa.BigInteger(), nullable=True),
        sa.Column("merchant_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("category_source", sa.String(length=20), nullable=False, server_default="device"),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("available_limit", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="sms"),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False, server_default="1.0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_card_id"], ["user_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "dedupe_hash", name="uq_card_transactions_user_hash"),
    )
    op.create_index("ix_card_transactions_user_occurred", "card_transactions", ["user_id", "occurred_at"])
    op.create_index("ix_card_transactions_user_card", "card_transactions", ["user_id", "user_card_id"])
    op.create_index("ix_card_transactions_bank_code", "card_transactions", ["bank_code"])
    op.create_index("ix_card_transactions_category", "card_transactions", ["category"])

    # 3. Card Bills
    op.create_table(
        "card_bills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_hash", sa.String(length=32), nullable=False),
        sa.Column("bank_code", sa.String(length=30), nullable=False),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("user_card_id", sa.Integer(), nullable=True),
        sa.Column("total_due", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("minimum_due", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("noticed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_card_id"], ["user_cards.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "dedupe_hash", name="uq_card_bills_user_hash"),
    )
    op.create_index("ix_card_bills_user_due", "card_bills", ["user_id", "due_date"])

    # 4. Card Milestone Rules
    op.create_table(
        "card_milestone_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reward_description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("period", sa.String(length=30), nullable=False),
        sa.Column("target_spend", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("excluded_categories", sa.JSON(), nullable=False, server_default='["rent", "wallet", "fees"]'),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["card_id"], ["credit_cards.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_card_milestone_rules_card_id", "card_milestone_rules", ["card_id"])

    # 5. Expense Consents
    op.create_table(
        "expense_consents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False, server_default="sms_card_expense_tracking"),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notice_version", sa.String(length=50), nullable=False, server_default="sms-v1"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("platform", sa.String(length=30), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_expense_consents_user_id", "expense_consents", ["user_id"])

    # 6. Expense Idempotency
    op.create_table(
        "expense_idempotency",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idem_key", sa.String(length=64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "idem_key"),
    )

    # 7. Add anniversary_month to user_cards
    op.add_column(
        "user_cards",
        sa.Column("anniversary_month", sa.Integer(), nullable=True, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("user_cards", "anniversary_month")
    op.drop_table("expense_idempotency")
    op.drop_table("expense_consents")
    op.drop_table("card_milestone_rules")
    op.drop_table("card_bills")
    op.drop_table("card_transactions")
    op.drop_table("merchants")
