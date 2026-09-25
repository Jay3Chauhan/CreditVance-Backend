"""
Common Pydantic Schemas and API Envelope.
"""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    details: Optional[Any] = Field(None, description="Detailed error diagnostics or validation errors")


class PaginationMeta(BaseModel):
    total: int = Field(..., description="Total items matching filter")
    page: int = Field(..., description="Current page index (1-based)")
    limit: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total available pages")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_prev: bool = Field(..., description="Whether a previous page exists")


class ApiResponse(BaseModel, Generic[DataT]):
    """Standard unified API response wrapper."""
    success: bool = Field(default=True, description="Indicates operation success")
    message: str = Field(default="Operation completed successfully", description="User-facing summary message")
    data: Optional[DataT] = Field(None, description="Payload data")
    meta: Optional[PaginationMeta] = Field(None, description="Optional pagination metadata")
    error: Optional[ErrorDetail] = Field(None, description="Error detail if failed")


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str
    database: str
    redis: str
    timestamp: str
