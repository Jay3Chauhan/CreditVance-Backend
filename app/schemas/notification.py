"""
Push notification request and response models.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_offsets(values: list[int]) -> list[int]:
    if len(values) > 6:
        raise ValueError("At most 6 reminder days are allowed.")
    cleaned: list[int] = []
    for value in values:
        if value < 0 or value > 31:
            raise ValueError("Reminder days must be between 0 and 31.")
        if value not in cleaned:
            cleaned.append(value)
    cleaned.sort()
    return cleaned


class NotificationPreferencesResponse(BaseModel):
    push_enabled: bool = Field(..., description="Master switch for every push on this account")
    due_reminder_days: List[int] = Field(
        ...,
        description="Days before the due date to push. 0 means the due date itself.",
    )
    statement_reminder_days: List[int] = Field(
        ...,
        description="Days before the statement date to push. 0 means statement day.",
    )
    product_updates: bool = Field(
        ...,
        description="Opt in to product news. Payment reminders do not use this flag.",
    )


class NotificationPreferencesUpdate(BaseModel):
    push_enabled: Optional[bool] = None
    due_reminder_days: Optional[List[int]] = None
    statement_reminder_days: Optional[List[int]] = None
    product_updates: Optional[bool] = None

    @field_validator("due_reminder_days", "statement_reminder_days")
    @classmethod
    def validate_offsets(cls, value: Optional[List[int]]) -> Optional[List[int]]:
        if value is None:
            return None
        return _clean_offsets(value)


class PushDispatchResponse(BaseModel):
    targeted_devices: int
    success_count: int
    failure_count: int
    invalid_tokens_removed: int = 0
    status: str = Field(..., description="sent, partial, failed, or skipped")


class NotificationHistoryItem(BaseModel):
    id: int
    notification_type: str
    title: str
    body: str
    route: Optional[str] = None
    status: str
    created_at: datetime


class PushStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    initialized: bool
    project_id: Optional[str] = None
    android_channel_id: str


class AdminPushRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=180)
    body: str = Field(..., min_length=2, max_length=500)
    route: str = Field("/home", max_length=200, description="In-app route opened when the notification is tapped")
    user_id: Optional[int] = Field(
        None,
        description="Send to one account. Omit to send only to accounts that opted into product updates.",
    )
