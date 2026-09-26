# CreditVance Backend Updates & Frontend Migration Guide

This document is the handoff for the Flutter app. It keeps the first round of API work (advisor, card detail, calculator, wallet, auth, catalog, reminders) and adds the second round: home feed, banners, promotions, compare, search, shortlist, and wallet insights.

Organized copies also live in `docs/` (`docs/FRONTEND_GUIDE.md` is the same handoff, written for the app developer).

---

## 1. Executive Summary & Verification

- **Git Baseline:** Synced with the latest commit from `main`.
- **Database Migrations:** Created and executed Alembic migration `8db00fd75200_add_wallet_catalog_device_token_features` on Neon Serverless PostgreSQL.
- **Test Verification:** All test suites passed with 100% success rate:
  - `tests/test_advisor.py` (Passed)
  - `tests/test_auth.py` (Passed)
  - `tests/test_calculator.py` (Passed)
  - `tests/test_cards.py` (Passed)
  - `tests/test_health.py` (Passed)
  - `tests/test_new_features.py` (Passed - verifies all 10 new feature domains end-to-end)

---

## 2. Detailed Summary of Backend Changes

| Priority | Feature / Issue | Backend Component(s) | Status | Description |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | **Advisor ignores `is_international`** | `advisor_service.py`<br>`schemas/advisor.py` | **Completed** | Calculates forex markup including 18% GST `(forex_markup × 1.18)`, checks international earn rates, deducts forex fee from return, and returns `forex_markup_applied`. |
| **P0** | **Advisor for guests & explicit card list** | `advisor_service.py`<br>`schemas/advisor.py` | **Completed** | Added optional `card_ids: List[int]` to `CardRecommendationRequest`. Unauthenticated guests or custom comparisons now rank cards server-side. |
| **P0** | **Card detail content is empty (Tabs & Overview)** | `card_service.py`<br>`crawler_service.py` | **Completed** | Automatic on-demand crawler ingestion + structured fallbacks. `card_image_url`, `overview_text`, `apply_link`, and tabs now always populated. `/cards/{slug}/tabs/*` **never returns 404**. |
| **P1** | **Reward calculator data in Card Detail** | `schemas/card.py`<br>`card_service.py`<br>`models/card.py` | **Completed** | Added `fee_waiver_spend`, `point_value_inr`, and `per_category_earn_rates` across all 17 categories to `CardDetailResponse`. |
| **P1** | **Annual Spend Calculator Endpoint** | `calculator_service.py`<br>`schemas/calculator.py`<br>`api/v1/calculator.py` | **Completed** | Added `POST /api/v1/calculator/annual` taking `{card_id, monthly_spend: {category: amount}}` and returning annual savings, waiver qualification, fee, and net value. |
| **P1** | **Profile & Account Management** | `api/v1/auth.py`<br>`core/security.py`<br>`schemas/auth.py` | **Completed** | Added `PATCH /api/v1/auth/me` (full_name), `POST /api/v1/auth/refresh` (refresh token), `POST /api/v1/auth/password/forgot`, `POST /api/v1/auth/password/reset`, and `DELETE /api/v1/auth/me` (account deletion). |
| **P1** | **Wallet Reordering & Billing Days** | `models/user_card.py`<br>`schemas/user_card.py`<br>`user_card_service.py`<br>`api/v1/wallet.py` | **Completed** | Added `sort_order`, `statement_day`, `due_day`, and `updated_at`. Added `PUT /api/v1/wallet/order` and `PUT /api/v1/user-cards/order` to persist drag-to-reorder. Mounted dedicated `/wallet` router. |
| **P1** | **Catalog Lounge Filters & Sorts** | `api/v1/cards.py`<br>`card_service.py`<br>`schemas/card.py` | **Completed** | Added `has_lounge=true/false` and `lounge_type` filters. Added `annual_fee_asc` and `return_desc` sorts. `applied_filters` now returned in pagination `meta`. |
| **P2** | **Due-Date Reminders & Device Tokens** | `models/device_token.py`<br>`api/v1/notifications.py`<br>`schemas/device_token.py` | **Completed** | Added `POST /api/v1/notifications/device-token` for APNs/FCM tokens and `GET /api/v1/notifications/reminders` for calculating upcoming statement/due dates. PCI-DSS safe (no PAN/CVV). |
| **P2** | **Legal & App Config Metadata** | `api/v1/meta.py`<br>`schemas/meta.py`<br>`card_service.py` | **Completed** | Added `GET /api/v1/meta/legal` and `GET /api/v1/meta/config` for minimum app version, maintenance banners, and curated category orders. |
| **P2** | **Category Metadata (Icons & Ordering)** | `api/v1/categories.py`<br>`schemas/category.py` | **Completed** | `GET /api/v1/categories` now returns `icon_key` (Material icon identifier) and `display_order` sorted logically. |
| **P2** | **Consistent Error Shape (`{"detail": "..."}`)** | `core/exceptions.py`<br>`main.py` | **Completed** | Unified error responses: FastAPI validation errors and custom errors now return a single flattened human-readable `detail` string, preventing client list-parsing crashes. |

---

## 3. Deep Dive into Changes & API Contracts

### 3.1. Advisor: `is_international` & `forex_markup_applied` (P0)

#### Changes Made:
- When `is_international: true` is passed to `POST /api/v1/advisor/recommend`:
  - Forex markup percentage is computed as `round((card.forex_markup_percent or 0.0) * 1.18, 2)` (accounting for India's 18% GST on forex markup).
  - Cards with 0% forex markup (e.g. Scapia, RBL World Safari) receive `forex_markup_applied = 0.0` and rank higher for international transactions.
  - International earn rows from the card's `earn-categories` tab are matched with highest priority.
  - The forex fee cost is subtracted from `estimated_reward_value_inr` and `effective_return_percent`.
  - Added `forex_markup_applied` to `RecommendedCardItem`.

#### Response Contract:
```json
{
  "card_id": 2,
  "card_title": "ICICI Rubyx (Mastercard) Credit Card",
  "card_slug": "icici-rubyx-mastercard",
  "rank": 1,
  "estimated_reward_points": 200.0,
  "estimated_reward_value_inr": 29.0,
  "effective_return_percent": 0.58,
  "forex_markup_applied": 4.13,
  "benefit_highlight": "Accelerated: 4 pts per ₹100 on International (net of 4.13% forex markup)"
}
```

---

### 3.2. Advisor for Guests & Explicit Card List (P0)

#### Changes Made:
- Updated `CardRecommendationRequest` to accept an optional `card_ids: List[int]`.
- Unauthenticated users (or guests without cloud wallets) can now pass `card_ids: [1, 2, 145]`.
- The backend evaluates and ranks these specific cards, returning `top_recommendation` and `alternative_cards` populated without needing user login.

#### Request Contract:
```http
POST /api/v1/advisor/recommend
Content-Type: application/json

{
  "category_slug": "Dining",
  "spend_amount": 5000.0,
  "is_international": false,
  "card_ids": [2, 145]
}
```

---

### 3.3. Card Details & Tabs: Non-Empty & Zero 404s (P0)

#### Changes Made:
- If a card detail is requested via `GET /api/v1/cards/{slug}` and has not been crawled yet:
  - The backend dynamically queries SaveSage on-demand and caches the tabs into the database.
  - If upstream returns no data or fails, the backend synthesizes clean, accurate editorial content and standard tabs based on the card's fee, network, return rates, and lounge attributes.
  - `card_image_url` automatically falls back to `web_logo_url` so images are never `null`.
  - `apply_link` automatically generates a secure bank application portal link.
  - `available_tabs` returns all 5 standard tabs: `["earn-categories", "benefits-and-offers", "lounge-access", "milestones", "redemption-options"]`.
- `GET /api/v1/cards/{slug}/tabs/{tab_name}`:
  - Dynamically fetches or synthesizes tab data if not already indexed.
  - **Never returns 404 Not Found**.

---

### 3.4. Reward Calculator Data & Annual Spend Endpoint (P1)

#### Changes to `GET /api/v1/cards/{slug}`:
Added three new properties to `CardDetailResponse`:
1. `fee_waiver_spend` (`float | null`): Annual spend threshold for annual renewal fee waiver.
2. `point_value_inr` (`float`): Cash value of 1 point (e.g. `1.00` for cashback/Infinia, `0.50` for Atlas/Regalia, `0.25` for standard).
3. `per_category_earn_rates` (`List[CategoryEarnRateItem]`):
   ```json
   [
     {"category_slug": "Dining", "rate_percent": 3.3, "cap_monthly": null},
     {"category_slug": "Fuel", "rate_percent": 0.0, "cap_monthly": null},
     {"category_slug": "Online Shopping", "rate_percent": 5.0, "cap_monthly": 10000.0}
   ]
   ```

#### New Endpoint: `POST /api/v1/calculator/annual`
Takes monthly spend across categories and computes annual returns, fee waiver qualification, and net monetary gain.

#### Request Contract:
```http
POST /api/v1/calculator/annual
Content-Type: application/json

{
  "cardId": 145,
  "monthlySpend": {
    "Dining": 5000,
    "Grocery": 10000,
    "Online Shopping": 15000,
    "Fuel": 3000
  }
}
```

#### Response Contract:
```json
{
  "success": true,
  "data": {
    "card_id": 145,
    "card_name": "Infinia (Metal)",
    "bank_name": "HDFC",
    "annual_spend": 396000.0,
    "total_annual_reward_inr": 23400.0,
    "renewal_fee": 12500.0,
    "fee_waiver_spend": 1000000.0,
    "fee_waived": false,
    "effective_renewal_fee": 12500.0,
    "net_annual_value_inr": 10900.0,
    "category_breakdown": [
      {
        "category_slug": "Dining",
        "monthly_spend": 5000.0,
        "annual_spend": 60000.0,
        "rate_percent": 3.3,
        "annual_reward_inr": 1980.0
      }
    ]
  }
}
```

---

### 3.5. Profile & Account Management (P1)

#### 1. `POST /api/v1/auth/login` & `POST /api/v1/auth/register`
Now returns both `access_token` and `refresh_token`:
```json
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in_minutes": 10080
}
```

#### 2. `POST /api/v1/auth/refresh`
Exchange a refresh token for new access and refresh tokens without signing the user out on 401.
```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbG..."
}
```

#### 3. `PATCH /api/v1/auth/me`
Update profile details (e.g. display name):
```http
PATCH /api/v1/auth/me
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "full_name": "Jay Chauhan"
}
```

#### 4. `DELETE /api/v1/auth/me`
In-app account deletion required by Google Play & Apple App Store. Deletes the account and cascades deletion of all associated wallet cards.

#### 5. `POST /api/v1/auth/password/forgot` & `POST /api/v1/auth/password/reset`
Initiates password reset instructions and completes password change securely.

---

### 3.6. Wallet Reordering & Billing Cycle Days (P1)

#### Changes Made:
- Model `UserCard` now stores:
  - `statement_day` (`int | null`, 1-31): Date each month when card statement is generated.
  - `due_day` (`int | null`, 1-31): Date each month when bill payment is due.
  - `sort_order` (`int`, default 0): Display position in portfolio.
  - `updated_at` (`datetime`): For offline conflict reconciliation.
- Added endpoints:
  - `PUT /api/v1/wallet/order` (and `PUT /api/v1/user-cards/order`) taking `{ids: [int]}`.
  - Drag-and-drop reordering is now persisted in PostgreSQL and returned ordered by `sort_order`.

#### Reorder Contract:
```http
PUT /api/v1/wallet/order
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "ids": [15, 8, 3]
}
```

---

### 3.7. Catalog: Lounge Filters, Sorts, and Meta (P1)

#### Query Parameters Added to `GET /api/v1/cards`:
- `has_lounge`: `true` or `false` (filters cards with airport lounge access).
- `lounge_type`: e.g. `INTERNATIONAL_LOUNGE`, `DOMESTIC_LOUNGE`, `RAILWAY_LOUNGE`.
- `sort_by`:
  - `annual_fee_asc`: Sorts by lowest renewal fee, then joining fee.
  - `annual_fee_desc`: Sorts by highest fee.
  - `return_desc`: Sorts by highest reward return percentage.
  - `return_asc`: Sorts by lowest return.
  - `popular`: Default popularity rank.

#### Pagination Metadata with Applied Filters:
```json
{
  "meta": {
    "total": 65,
    "page": 1,
    "limit": 20,
    "total_pages": 4,
    "has_next": true,
    "has_prev": false,
    "applied_filters": {
      "search": null,
      "bank_slug": null,
      "network": null,
      "fee_type": null,
      "has_lounge": true,
      "lounge_type": "INTERNATIONAL_LOUNGE",
      "is_popular": null,
      "sort_by": "annual_fee_asc"
    }
  }
}
```

---

### 3.8. Nice-to-Have Features (P2)

#### 1. Push Due-Date Reminders (`/api/v1/notifications`)
- `POST /api/v1/notifications/device-token`: Register FCM (Android) or APNs (iOS) tokens.
- `GET /api/v1/notifications/reminders`: Returns days until statement and days until payment due for user cards.

#### 2. Legal Compliance & App Config (`/api/v1/meta`)
- `GET /api/v1/meta/legal`: Returns verified URLs for Privacy Policy, Terms, and Data Deletion.
- `GET /api/v1/meta/config`: Returns `min_app_version`, `latest_app_version`, `maintenance_mode`, and `curated_category_order`.

#### 3. Category Metadata (`/api/v1/categories`)
- Returns `icon_key` (Material icon identifier such as `restaurant`, `flight_takeoff`, `shopping_cart`) and `display_order` (1 to 17).

#### 4. Unified Error Shape
- Any error (validation error or application error) includes `"detail": "message"` as a string:
```json
{
  "success": false,
  "message": "spend_amount: Input should be greater than 0",
  "detail": "spend_amount: Input should be greater than 0",
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "details": [...]
  }
}
```

---

## 4. Frontend Action Items & Workarounds to Remove

The following table summarizes what frontend code can now be cleaned up or unlocked:

| Screen / Feature | Workaround Currently in App | Action for Frontend Developer |
| :--- | :--- | :--- |
| **Smart Advisor** | Client calculates `forex_markup × 1.18` on-device. | **Remove on-device calculation.** Pass `is_international: true` to `/advisor/recommend` and display the returned `forex_markup_applied`. |
| **Guest Advisor** | Unauthenticated users were ranked purely with on-device heuristics. | Pass locally stored card IDs via `card_ids: [int]` in the request body to `/advisor/recommend`. Display `top_recommendation` and `alternative_cards` directly from the server. |
| **Card Detail Screen** | Sections hide when tabs are empty or 404. | Un-hide tab sections! Call `/cards/{slug}/tabs/{tab}` and display the earn rates, lounge lists, milestones, and redemption options returned. |
| **Card Detail Overview** | Overview fallback had empty text. | Render `overview_text`, `apply_link`, and `card_image_url` directly from `CardDetailResponse`. |
| **Reward Calculator** | App hardcodes rates for 4 cards and falls back to `return_min_percent`. | Use `fee_waiver_spend`, `point_value_inr`, and `per_category_earn_rates` directly from card detail, OR call `POST /calculator/annual` with `{cardId, monthlySpend}` for complete instant breakdown. |
| **Wallet Portfolio** | Drag-to-reorder cards only persisted in local SQLite/Hive. | Call `PUT /wallet/order` with `{"ids": orderedCardIds}` on drag end to persist ordering across devices. |
| **Billing Cycle** | Statement day was inconsistently saved. | Use `statement_day` and `due_day` (1-31) in `AddUserCardRequest` and `UpdateUserCardRequest`. |
| **Account Screen** | Edit Profile & Account Deletion were non-functional. | Wire up `PATCH /auth/me` with `{"full_name": name}` and `DELETE /auth/me` on "Delete Account" confirmation. |
| **Auth Interceptor** | On 401 error, user was immediately logged out. | Catch 401 in Dio / HTTP interceptor, call `POST /auth/refresh` with `refresh_token`, update tokens, and replay request. |
| **Catalog Filter Sheet** | Lounge filters and custom sorts were missing. | Add `has_lounge=true`, `lounge_type=INTERNATIONAL_LOUNGE`, `sort_by=annual_fee_asc`, and `sort_by=return_desc` to catalog query params. |
| **About Screen / Legal** | Privacy and Terms links were hardcoded or placeholder. | Fetch `GET /meta/legal` to open stable URLs in in-app webview or external browser. |
| **Category Badges** | Client had custom hardcoded icon maps. | Read `icon_key` and `display_order` from `GET /categories` to automatically order and iconify categories. |
| **Error Handling** | Client had to check if `detail` was a List or String. | Client can now read `response.data['detail']` or `response.data['message']` directly as a String without manual flattening. |

---

## 5. Flutter Code Examples for Quick Integration

### 5.1. Guest Mode Advisor Request
```dart
Future<AdvisorRecommendation> getGuestRecommendation({
  required String categorySlug,
  required double spendAmount,
  required List<int> localCardCatalogIds,
  bool isInternational = false,
}) async {
  final response = await dio.post('/api/v1/advisor/recommend', data: {
    'category_slug': categorySlug,
    'spend_amount': spendAmount,
    'is_international': isInternational,
    'card_ids': localCardCatalogIds,
  });
  return AdvisorRecommendation.fromJson(response.data['data']);
}
```

### 5.2. Persisting Wallet Reordering
```dart
Future<void> onReorderCards(List<int> orderedUserCardIds) async {
  await dio.put('/api/v1/wallet/order', data: {
    'ids': orderedUserCardIds,
  });
}
```

### 5.3. Multi-Category Annual Calculator
```dart
Future<AnnualCalculatorResult> calculateAnnualRewards({
  required int cardId,
  required Map<String, double> monthlySpendByCategory,
}) async {
  final response = await dio.post('/api/v1/calculator/annual', data: {
    'cardId': cardId,
    'monthlySpend': monthlySpendByCategory,
  });
  return AnnualCalculatorResult.fromJson(response.data['data']);
}
```

### 5.4. Token Refresh Interceptor (Dio)
```dart
dio.interceptors.add(InterceptorsWrapper(
  onError: (DioException error, handler) async {
    if (error.response?.statusCode == 401 && storedRefreshToken != null) {
      try {
        final refreshRes = await dio.post('/api/v1/auth/refresh', data: {
          'refresh_token': storedRefreshToken,
        });
        final newAccessToken = refreshRes.data['data']['access_token'];
        final newRefreshToken = refreshRes.data['data']['refresh_token'];
        await saveTokens(newAccessToken, newRefreshToken);

        // Replay original request with new token
        error.requestOptions.headers['Authorization'] = 'Bearer $newAccessToken';
        final cloneReq = await dio.fetch(error.requestOptions);
        return handler.resolve(cloneReq);
      } catch (e) {
        await logoutUser();
      }
    }
    return handler.next(error);
  },
));
```

---

## 6. Verification and Health Checks

All changes are live in the local and server codebase, backed by PostgreSQL migrations and pytest coverage:
- Run all tests: `.venv/bin/pytest`
- First-round features: `.venv/bin/pytest tests/test_new_features.py`
- Home, banners, promotions, compare, search, shortlist, insights: `.venv/bin/pytest tests/test_content_platform.py`

Database revision for the second round: `c4a91e2b7f10` (`alembic upgrade head`). The shared database is already stamped at that revision. A fresh database should run the migration; the first public read of banners or promotions inserts the editorial seed if those tables are empty.

---

## 7. Fixes in this round

| Issue | What the app was seeing | What the backend does now |
| :--- | :--- | :--- |
| Reminder bank name | `bank_name` was always `"Bank"`. | The reminder loads the card's bank and returns the real name, for example `"HDFC"`. |
| Due-date math | Days used `(due_day - today) % 30`, so February and 31-day months were wrong, and a date could never be more than 29 days away. | Days follow the real calendar. `0` means today. A due day of `31` in a shorter month lands on that month's last day. `days_until_due` can be greater than 30. |
| Catalog search + bank filter | `search` and `bank_slug` together joined the banks table twice and could return HTTP 500. | One join. Both filters can be sent together. |
| Password reset token | `POST /auth/password/forgot` always returned `reset_token`. | Development still returns it, because email is not wired yet. When `ENVIRONMENT` is production the field is `null` and the message stays generic. Do not build the production UI around reading that token. |

---

## 8. New APIs (second round)

Base path is still `/api/v1`. Every success and error body uses the same envelope as before, including a string `detail`.

New feature flags on `GET /api/v1/meta/config` (existing flags are unchanged):

`home_feed`, `banners`, `promotions`, `card_compare`, `search_suggest`, `saved_cards`, `wallet_insights`, `faq`.

`min_app_version` stays `1.0.0`. Do not force-update existing installs because of these flags.

### 8.1 How a tap works

Banners, promotions, collections, and quick actions share one action object:

```json
{
  "type": "screen",
  "target": "/advisor?international=true",
  "label": "International mode"
}
```

| `type` | `target` | Open |
| :--- | :--- | :--- |
| `screen` | `/advisor` | Advisor. Optional query: `international=true`, `category=Dining`. |
| `screen` | `/compare` | Compare flow. |
| `screen` | `/calculator` | Annual calculator. |
| `screen` | `/catalog?has_lounge=true` | Catalog. Also `fee_type=free`, `sort_by=return_desc`. |
| `screen` | `/wallet` | Wallet. |
| `screen` | `/saved` | Shortlist. |
| `card` | card slug | Card detail. |
| `category` | category slug, e.g. `Dining` | That category, or the advisor with it pre-selected. |
| `promotion` | promotion slug | Promotion detail. |
| `url` | `https://...` | In-app webview or the system browser. |
| `none` | `null` | No navigation. |

`image_url` is often `null`. Draw the banner from `background_color`, `accent_color`, `title`, `subtitle`, and `badge_text`. Use `image_url` only when it is present.

Seeded banners and promotions are product guides. They are not bank welcome-bonus claims. A future row with `promo_type` of `welcome_bonus` or `cashback` is an offer an editor published; show `terms` and do not invent a reward the payload does not contain.

### 8.2 Home feed — `GET /api/v1/home`

One call for the home screen. Optional `Authorization` header.

- No token: audience `guest` (plus every row marked `all`).
- Valid token: audience `member` (plus `all`). The wallet banner is `member`, so it does not appear for guests.

```json
{
  "success": true,
  "data": {
    "hero_banners": [],
    "strip_banners": [],
    "featured_promotions": [],
    "popular_cards": [],
    "categories": [],
    "collections": [
      {
        "key": "lifetime_free",
        "title": "Lifetime free",
        "subtitle": "No joining fee. Useful first cards and everyday backups.",
        "action": {"type": "screen", "target": "/catalog?fee_type=free", "label": "See all"},
        "cards": []
      }
    ],
    "quick_actions": [
      {
        "key": "advisor",
        "title": "Which card?",
        "subtitle": "Best card for this spend",
        "icon_key": "auto_awesome",
        "action": {"type": "screen", "target": "/advisor", "label": "Ask"}
      }
    ]
  }
}
```

`categories` on this payload is the first eight, already ordered. The full list is still `GET /categories`.

Suggested home layout, top to bottom: `hero_banners` carousel, `quick_actions`, `strip_banners`, `featured_promotions`, `collections`, `popular_cards`.

### 8.3 Banners — `GET /api/v1/banners`

Query: `placement` (`home_hero`, `home_strip`, `catalog_top`, `wallet`, `card_detail`, `advisor`) and optional `audience` (`guest` or `member`). Rows with `audience: all` are always included. Inactive and out-of-schedule rows are omitted.

| Screen | Call |
| :--- | :--- |
| Home | Prefer `GET /home` instead of calling banners yourself. |
| Catalog | `GET /banners?placement=catalog_top` |
| Wallet | `GET /banners?placement=wallet&audience=member` |
| Advisor | `GET /banners?placement=advisor` |
| Card detail | `GET /banners?placement=card_detail` |

```json
{
  "id": 1,
  "slug": "advisor-hero",
  "title": "Which card should you use?",
  "subtitle": "Rank the cards you hold for this exact spend.",
  "image_url": null,
  "placement": "home_hero",
  "badge_text": "Smart",
  "background_color": "#0F2744",
  "accent_color": "#F4C430",
  "priority": 100,
  "audience": "all",
  "starts_at": null,
  "ends_at": null,
  "action": {"type": "screen", "target": "/advisor", "label": "Ask advisor"},
  "impression_count": 0,
  "click_count": 0
}
```

Tracking (no auth, fire-and-forget):

```http
POST /api/v1/banners/{id}/track
{"event": "impression"}
```

`event` is `impression` or `click`. Send `impression` once when the banner is actually shown, and `click` when the user taps it, then navigate using `action`.

### 8.4 Promotions — `GET /api/v1/promotions`

Query: `featured`, `promo_type`, `category_slug`, `card_slug`.

`card_slug` returns promotions linked to that card, or to one of the card's categories. Use it on card detail. An empty list means there is nothing to show; hide the section.

`GET /api/v1/promotions/{slug}` returns one guide, including `description` and `terms`.

`POST /api/v1/promotions/{id}/track` uses the same `impression` / `click` body as banners. The path id is the numeric `id`, not the slug.

```json
{
  "id": 2,
  "slug": "dining-picks",
  "title": "Best fit for dining",
  "summary": "Restaurant spends are one of the widest gaps between cards.",
  "description": "Use category Dining in the advisor.",
  "image_url": null,
  "badge": "Dining",
  "promo_type": "editorial",
  "highlight_value": "Dining",
  "terms": null,
  "card_id": null,
  "card_slug": null,
  "card_title": null,
  "category_slug": "Dining",
  "priority": 90,
  "is_featured": true,
  "action": {"type": "screen", "target": "/advisor?category=Dining", "label": "Ask for dining"}
}
```

`promo_type` values: `editorial`, `feature`, `welcome_bonus`, `cashback`, `fee_waiver`, `lounge`, `partner`, `seasonal`.

### 8.5 Compare — `POST /api/v1/cards/compare`

No auth. Send 2 to 4 slugs. Duplicates are ignored. Unknown slug returns 404 with a string `detail`.

```json
{"slugs": ["hdfc-millennia", "sbi-cashback-credit-card"]}
```

```json
{
  "cards": [
    {
      "slug": "hdfc-millennia",
      "joining_fee": 1000.0,
      "best_suited": null,
      "fee_waiver_spend": 100000.0,
      "point_value_inr": 0.25
    }
  ],
  "rows": [
    {
      "key": "joining_fee",
      "label": "Joining fee",
      "better": "lower",
      "values": {"hdfc-millennia": 1000.0},
      "winner_slug": "hdfc-millennia"
    }
  ],
  "category_rates": [
    {
      "category_slug": "Dining",
      "rates": {"hdfc-millennia": 2.5},
      "winner_slug": "hdfc-millennia"
    }
  ]
}
```

`cards` includes the normal card summary fields plus `best_suited`, `fee_waiver_spend`, and `point_value_inr`.

Rows: `joining_fee`, `renewal_fee`, `forex_markup_percent` (lower is better), `return_max_percent`, `point_value_inr`, `lounge_count` (higher is better). `winner_slug` is `null` when the values tie or a value is missing. Do not highlight a winner in that case.

Category rows are Dining, Grocery, Online Shopping, Travel, Fuel, and International.

### 8.6 Search suggestions — `GET /api/v1/search/suggest?q=inf&limit=8`

`q` is 1–40 characters. `limit` is 1–10, default 8. Debounce about 300ms.

```json
{
  "id": 12,
  "slug": "hdfc-infinia-metal",
  "title": "HDFC Infinia Metal Credit Card",
  "display_name": "Infinia Metal",
  "bank_name": "HDFC",
  "card_image_url": null
}
```

This does not replace `GET /cards?search=`. Use suggest in the search field, then the normal catalog for the results page.

### 8.7 Shortlist — `/api/v1/saved-cards`

Auth required. This is not the wallet. Wallet = cards the user holds. Shortlist = catalog cards they might apply for. Still no PAN or CVV.

| Method | Path | Body |
| :--- | :--- | :--- |
| `GET` | `/saved-cards` | — |
| `POST` | `/saved-cards` | `{"card_id": 12}` |
| `DELETE` | `/saved-cards/{card_id}` | catalog id, not the shortlist row id |

Saving the same card again returns 201 with the existing row. It does not create a duplicate.

```json
{
  "id": 4,
  "card_id": 12,
  "saved_at": "2026-09-26T08:00:00Z",
  "card": { "id": 12, "slug": "hdfc-infinia-metal", "title": "HDFC Infinia Metal Credit Card" }
}
```

`card` is a full catalog summary. Deleting the account removes the shortlist.

### 8.8 Wallet insights — `GET /api/v1/wallet/insights`

Auth required.

```json
{
  "card_count": 2,
  "total_renewal_fee_inr": 15000.0,
  "lifetime_free_count": 0,
  "lounge_card_count": 1,
  "next_due": {
    "user_card_id": 15,
    "nickname": "Primary",
    "card_title": "HDFC Millennia Credit Card",
    "bank_name": "HDFC",
    "due_day": 25,
    "days_until_due": 12,
    "reminder_type": "due_date",
    "message": "Payment for Primary is due in 12 days."
  },
  "category_picks": [
    {
      "category_slug": "Dining",
      "icon_key": "restaurant",
      "rate_percent": 5.0,
      "user_card_id": 15,
      "nickname": "Primary",
      "card": { "slug": "hdfc-millennia" }
    }
  ],
  "empty_state_message": null
}
```

`category_picks` covers Dining, Grocery, Online Shopping, Travel, Fuel, and International. Show the nickname and the rate. An empty wallet returns zeros, an empty `category_picks`, and `empty_state_message`.

### 8.9 FAQ — `GET /api/v1/meta/faq`

No auth. Render this on the help screen instead of hardcoding answers.

```json
{
  "id": "wallet-vs-shortlist",
  "topic": "wallet",
  "question": "What is the difference between my wallet and my shortlist?",
  "answer": "The wallet is cards you already hold..."
}
```

Topics: `wallet`, `advisor`, `calculator`, `reminders`, `privacy`, `promotions`.

### 8.10 Admin content (not for the mobile app)

`/api/v1/admin/content/banners` and `/api/v1/admin/content/promotions` support list, create, update, and delete with `X-Admin-API-Key`. The app should only call the public GET and track endpoints.

---

## 9. Frontend work for this round

Do the items in section 4 as well. They are still required. This table is only the new work.

| Screen | Build |
| :--- | :--- |
| **Home** | Replace the hand-built home with `GET /home`. Carousel from `hero_banners`. Quick actions from `quick_actions` using `icon_key` as a Material icon. Strip, featured promotions, collections, then popular cards. |
| **Catalog** | Banner from `placement=catalog_top`. Search field calls `/search/suggest`, then `/cards?search=`. |
| **Compare** | New screen. User picks 2–4 cards (from catalog, shortlist, or wallet). `POST /cards/compare`. Highlight `winner_slug` only when it is non-null. `better: lower` means the smaller number wins (fees, forex). |
| **Card detail** | `GET /promotions?card_slug={slug}`. Hide the block when the list is empty. Optional `card_detail` banner. |
| **Wallet** | `GET /wallet/insights` under the card stack: next due, total renewal fees, lounge count, and “best card for dining / travel / …”. Banner `placement=wallet&audience=member`. |
| **Shortlist** | New screen at `/saved`. Bookmark on catalog and card detail calls `POST /saved-cards`. Filled bookmark calls `DELETE /saved-cards/{cardId}`. |
| **Advisor** | Banner `placement=advisor`. Honor `action.target` query `international=true` and `category=Dining` when a promotion opens this screen. |
| **Help** | `GET /meta/faq`, grouped by `topic`. |
| **Reminders** | Show `bank_name` from the API. Do not cap the countdown at 30 days. |
| **Tracking** | On show: `event: impression`. On tap: `event: click`, then route with the action table in section 8.1. |

### Dart: open an action

```dart
void openContentAction(ContentAction action) {
  switch (action.type) {
    case 'screen':
      // Parse action.target. Examples:
      // /advisor?international=true&category=Dining
      // /catalog?has_lounge=true
      // /catalog?fee_type=free
      break;
    case 'card':
      // Navigator to card detail with slug = action.target
      break;
    case 'category':
      // Advisor or catalog scoped to action.target
      break;
    case 'promotion':
      // GET /api/v1/promotions/{action.target}
      break;
    case 'url':
      // Launch action.target
      break;
    case 'none':
      break;
  }
}
```

### Dart: home

```dart
Future<HomeFeed> loadHome() async {
  final response = await dio.get('/api/v1/home');
  return HomeFeed.fromJson(response.data['data'] as Map<String, dynamic>);
}
```

Send the access token on this call when the user is signed in so member banners are included. If the token is missing or expired, call it again without the header; guests still get a full home.
