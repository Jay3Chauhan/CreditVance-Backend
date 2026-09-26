"""
Schemas for banners, promotions, home feed, compare, search, shortlist, and insights.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.card import CardSummaryResponse
from app.schemas.category import CategoryResponse
from app.schemas.device_token import CardReminderItem

ActionType = Literal["none", "card", "category", "url", "screen", "promotion"]
BannerPlacement = Literal[
    "home_hero", "home_strip", "catalog_top", "wallet", "card_detail", "advisor"
]
Audience = Literal["all", "guest", "member"]
PromoType = Literal[
    "editorial",
    "feature",
    "welcome_bonus",
    "cashback",
    "fee_waiver",
    "lounge",
    "partner",
    "seasonal",
]
TrackEvent = Literal["impression", "click"]


class ContentAction(BaseModel):
    type: str = Field(..., description="none | card | category | url | screen | promotion")
    target: Optional[str] = Field(
        None,
        description="Card slug, category slug, https URL, in-app route, or promotion slug",
    )
    label: Optional[str] = Field(None, description="Button label")


class BannerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    subtitle: Optional[str] = None
    image_url: Optional[str] = None
    placement: str
    badge_text: Optional[str] = None
    background_color: Optional[str] = None
    accent_color: Optional[str] = None
    priority: int
    audience: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    action: ContentAction
    impression_count: int = 0
    click_count: int = 0


class BannerWriteRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(..., min_length=2, max_length=160)
    subtitle: Optional[str] = Field(None, max_length=300)
    image_url: Optional[str] = Field(None, max_length=1000)
    placement: BannerPlacement
    cta_label: Optional[str] = Field(None, max_length=80)
    action_type: ActionType = "screen"
    action_target: Optional[str] = Field(None, max_length=500)
    badge_text: Optional[str] = Field(None, max_length=40)
    background_color: Optional[str] = Field(None, max_length=20)
    accent_color: Optional[str] = Field(None, max_length=20)
    priority: int = 0
    is_active: bool = True
    audience: Audience = "all"
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class BannerUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=160)
    subtitle: Optional[str] = Field(None, max_length=300)
    image_url: Optional[str] = Field(None, max_length=1000)
    placement: Optional[BannerPlacement] = None
    cta_label: Optional[str] = Field(None, max_length=80)
    action_type: Optional[ActionType] = None
    action_target: Optional[str] = Field(None, max_length=500)
    badge_text: Optional[str] = Field(None, max_length=40)
    background_color: Optional[str] = Field(None, max_length=20)
    accent_color: Optional[str] = Field(None, max_length=20)
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    audience: Optional[Audience] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class PromotionResponse(BaseModel):
    id: int
    slug: str
    title: str
    summary: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    badge: Optional[str] = None
    promo_type: str
    highlight_value: Optional[str] = None
    terms: Optional[str] = None
    card_id: Optional[int] = None
    card_slug: Optional[str] = None
    card_title: Optional[str] = None
    category_slug: Optional[str] = None
    priority: int
    is_featured: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    action: ContentAction
    impression_count: int = 0
    click_count: int = 0


class PromotionWriteRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(..., min_length=2, max_length=180)
    summary: str = Field(..., min_length=2, max_length=400)
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1000)
    badge: Optional[str] = Field(None, max_length=40)
    promo_type: PromoType
    highlight_value: Optional[str] = Field(None, max_length=80)
    terms: Optional[str] = None
    card_id: Optional[int] = None
    category_slug: Optional[str] = Field(None, max_length=80)
    cta_label: Optional[str] = Field(None, max_length=80)
    action_type: ActionType = "screen"
    action_target: Optional[str] = Field(None, max_length=500)
    priority: int = 0
    is_featured: bool = False
    is_active: bool = True
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class PromotionUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=180)
    summary: Optional[str] = Field(None, min_length=2, max_length=400)
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1000)
    badge: Optional[str] = Field(None, max_length=40)
    promo_type: Optional[PromoType] = None
    highlight_value: Optional[str] = Field(None, max_length=80)
    terms: Optional[str] = None
    card_id: Optional[int] = None
    category_slug: Optional[str] = Field(None, max_length=80)
    cta_label: Optional[str] = Field(None, max_length=80)
    action_type: Optional[ActionType] = None
    action_target: Optional[str] = Field(None, max_length=500)
    priority: Optional[int] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class TrackEventRequest(BaseModel):
    event: TrackEvent


class HomeCollection(BaseModel):
    key: str
    title: str
    subtitle: str
    action: ContentAction
    cards: List[CardSummaryResponse] = Field(default_factory=list)


class QuickAction(BaseModel):
    key: str
    title: str
    subtitle: str
    icon_key: str
    action: ContentAction


class HomeFeedResponse(BaseModel):
    hero_banners: List[BannerResponse] = Field(default_factory=list)
    strip_banners: List[BannerResponse] = Field(default_factory=list)
    featured_promotions: List[PromotionResponse] = Field(default_factory=list)
    popular_cards: List[CardSummaryResponse] = Field(default_factory=list)
    categories: List[CategoryResponse] = Field(default_factory=list)
    collections: List[HomeCollection] = Field(default_factory=list)
    quick_actions: List[QuickAction] = Field(default_factory=list)


class CompareCardsRequest(BaseModel):
    slugs: List[str] = Field(..., min_length=2, max_length=4)


class CompareRow(BaseModel):
    key: str
    label: str
    better: Literal["lower", "higher"]
    values: Dict[str, Optional[float]]
    winner_slug: Optional[str] = None


class CompareCategoryRate(BaseModel):
    category_slug: str
    rates: Dict[str, float]
    winner_slug: Optional[str] = None


class CompareCard(CardSummaryResponse):
    best_suited: Optional[str] = None
    fee_waiver_spend: Optional[float] = None
    point_value_inr: Optional[float] = None


class CompareResponse(BaseModel):
    cards: List[CompareCard]
    rows: List[CompareRow]
    category_rates: List[CompareCategoryRate]


class SearchSuggestion(BaseModel):
    id: int
    slug: str
    title: str
    display_name: str
    bank_name: Optional[str] = None
    card_image_url: Optional[str] = None


class SaveCardRequest(BaseModel):
    card_id: int = Field(..., ge=1)


class SavedCardResponse(BaseModel):
    id: int
    card_id: int
    saved_at: datetime
    card: CardSummaryResponse


class CategoryPick(BaseModel):
    category_slug: str
    icon_key: str
    rate_percent: float
    user_card_id: int
    nickname: Optional[str] = None
    card: CardSummaryResponse


class WalletInsightsResponse(BaseModel):
    card_count: int
    total_renewal_fee_inr: float
    lifetime_free_count: int
    lounge_card_count: int
    next_due: Optional[CardReminderItem] = None
    category_picks: List[CategoryPick] = Field(default_factory=list)
    empty_state_message: Optional[str] = None


class FaqItem(BaseModel):
    id: str
    topic: str
    question: str
    answer: str


class FaqResponse(BaseModel):
    items: List[FaqItem]
