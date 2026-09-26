"""
Metadata & Configuration Pydantic Schemas.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LegalMetaResponse(BaseModel):
    privacy_policy_url: str = Field(..., description="Stable URL for the Privacy Policy")
    terms_of_service_url: str = Field(..., description="Stable URL for Terms of Service")
    contact_email: str = Field(..., description="Support / Contact email")
    data_deletion_policy_url: str = Field(..., description="Data deletion compliance instructions URL")


class AppConfigResponse(BaseModel):
    min_app_version: str = Field("1.0.0", description="Minimum supported client version")
    latest_app_version: str = Field("1.1.0", description="Latest available app version")
    maintenance_mode: bool = Field(False, description="Whether the system is undergoing scheduled maintenance")
    maintenance_message: Optional[str] = Field(None, description="Banner message when maintenance_mode is True")
    curated_category_order: List[str] = Field(default_factory=list, description="Curated order of spend categories")
    feature_flags: Dict[str, Any] = Field(default_factory=dict, description="Active feature flags")
