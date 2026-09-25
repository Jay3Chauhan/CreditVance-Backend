"""
Ingestion & Sync Admin Pydantic Schemas.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class SyncTriggerRequest(BaseModel):
    sync_tabs: bool = Field(
        False,
        description="Set True to also deep-crawl all 5 perk tabs for each card (~15 min for all cards). Default False syncs all cards in ~10 seconds.",
    )
    limit_cards: Optional[int] = Field(
        None,
        description="Limit number of cards to crawl (e.g. 10). Leave null/empty for all 734 cards.",
    )


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
