"""
Device Token & Reminders Schemas.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceTokenRegisterRequest(BaseModel):
    device_token: str = Field(..., min_length=10, max_length=500, description="FCM registration token")
    platform: str = Field("android", description="Device platform: android, ios, or web")

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"android", "ios", "web"}:
            raise ValueError("platform must be android, ios, or web")
        return normalized


class DeviceTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    platform: str
    created_at: datetime


class CardReminderItem(BaseModel):
    user_card_id: int
    nickname: str
    card_title: str
    bank_name: str
    statement_day: Optional[int] = None
    due_day: Optional[int] = None
    days_until_statement: Optional[int] = None
    days_until_due: Optional[int] = None
    reminder_type: str = "due_date"  # "due_date" or "statement_date"
    message: str


class UpcomingRemindersResponse(BaseModel):
    reminders: List[CardReminderItem] = Field(default_factory=list)
