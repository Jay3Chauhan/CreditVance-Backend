"""
Ingestion & Sync Admin Pydantic Schemas.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class SyncTriggerRequest(BaseModel):
    sync_tabs: bool = Field(True, description="Whether to also crawl 5 tabs for each card")
    limit_cards: Optional[int] = Field(None, description="Optional limit for dry-run testing (e.g. 10 cards)")


class SyncStatusResponse(BaseModel):
    is_syncing: bool
    last_sync_status: Optional[str] = None
    last_sync_time: Optional[datetime] = None
    total_cards_in_db: int
    total_banks_in_db: int


class SyncAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sync_type: str
    status: str
    cards_fetched: int
    tabs_fetched: int
    errors_count: int
    details: Dict[str, Any]
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
