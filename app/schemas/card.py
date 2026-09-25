"""
Credit Card Catalog Pydantic Schemas.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.bank import BankResponse


class CardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    display_name: str
    bank_name: Optional[str] = None
    bank_slug: Optional[str] = None
    bank_logo_url: Optional[str] = None
    web_logo_url: Optional[str] = None
    card_image_url: Optional[str] = None
    joining_fee: float
    renewal_fee: float
    forex_markup_percent: Optional[float] = None
    return_percentage_raw: Optional[str] = None
    return_min_percent: float
    return_max_percent: float
    network_type: Optional[str] = None
    lounge_types: List[str] = Field(default_factory=list)
    benefit_types: List[str] = Field(default_factory=list)
    category_slugs: List[str] = Field(default_factory=list)
    is_popular: bool
    is_currently_issuing: bool


class CardDetailResponse(CardSummaryResponse):
    bank: Optional[BankResponse] = None
    apr_percent: Optional[float] = None
    add_on_card_fee: Optional[float] = None
    is_fd_card: bool
    is_business_card: bool
    apply_link: Optional[str] = None
    overview_text: Optional[str] = None
    best_suited: Optional[str] = None
    available_tabs: List[str] = Field(default_factory=list)


class CardTabResponse(BaseModel):
    card_id: int
    card_slug: str
    tab_name: str
    content: Dict[str, Any]


class CardFilterQuery(BaseModel):
    search: Optional[str] = Field(None, description="Search term for card name, bank, or benefits")
    bank_slug: Optional[str] = Field(None, description="Filter by bank slug (e.g. hdfc, icici, axis)")
    network: Optional[str] = Field(None, description="Filter by network (VISA, MASTERCARD, RUPAY, AMEX)")
    fee_type: Optional[str] = Field(None, description="Filter: 'free', 'lt1k', '1k5k', 'gt5k'")
    lounge: Optional[bool] = Field(None, description="Filter cards with lounge access")
    is_popular: Optional[bool] = Field(None, description="Filter only popular cards")
    sort_by: Optional[str] = Field("popular", description="Sort by: 'popular', 'return', 'fee_asc', 'fee_desc', 'name'")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    limit: int = Field(20, ge=1, le=100, description="Items per page")
