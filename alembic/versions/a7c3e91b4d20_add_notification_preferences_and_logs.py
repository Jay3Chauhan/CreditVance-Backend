"""add notification preferences and logs

Revision ID: a7c3e91b4d20
Revises: c4a91e2b7f10
Create Date: 2026-09-27 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e91b4d20"
down_revision: Union[str, None] = "c4a91e2b7f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("push_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("due_reminder_days", sa.JSON(), nullable=False),
        sa.Column("statement_reminder_days", sa.JSON(), nullable=False),
        sa.Column("product_updates", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=180), nullable=False),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),
    )
    op.create_index(op.f("ix_notification_logs_user_id"), "notification_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_notification_logs_dedupe_key"), "notification_logs", ["dedupe_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_logs_dedupe_key"), table_name="notification_logs")
    op.drop_index(op.f("ix_notification_logs_user_id"), table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_table("notification_preferences")
