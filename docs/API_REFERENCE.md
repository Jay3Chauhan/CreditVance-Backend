# API reference

Base path: `/api/v1`

Success:

```json
{ "success": true, "message": "...", "data": {}, "meta": null, "error": null }
```

Failure (`detail` is always a string):

```json
{
  "success": false,
  "message": "Human readable reason",
  "detail": "Human readable reason",
  "data": null,
  "error": { "code": "NOT_FOUND", "details": null }
}
```

Auth header when required: `Authorization: Bearer <access_token>`.

## Auth

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| POST | `/auth/register` | No | Create account. Body: `email`, `password`, `full_name`. |
| POST | `/auth/login` | No | Returns `access_token` and `refresh_token`. |
| POST | `/auth/refresh` | No | Body: `refresh_token`. Returns a new pair. |
| GET | `/auth/me` | Yes | Profile. |
| PATCH | `/auth/me` | Yes | Body: `full_name`. |
| DELETE | `/auth/me` | Yes | Deletes the account, wallet, and shortlist. |
| POST | `/auth/password/forgot` | No | Body: `email`. `reset_token` is returned only outside production. |
| POST | `/auth/password/reset` | No | Body: `token`, `new_password`. |

## Catalog

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | `/cards` | No | Paginated catalog. |
| POST | `/cards/compare` | No | Body: `slugs` (2–4). Side-by-side rows and category rates. |
| GET | `/cards/{slug}` | No | Detail, including `fee_waiver_spend`, `point_value_inr`, `per_category_earn_rates`. |
| GET | `/cards/{slug}/tabs/{tab}` | No | `earn-categories`, `benefits-and-offers`, `lounge-access`, `milestones`, `redemption-options`. Does not 404 when content was missing. |
| GET | `/banks` | No | Banks. |
| GET | `/categories` | No | Categories with `icon_key` and `display_order`. |
| GET | `/search/suggest` | No | Query: `q`, `limit`. Typeahead. |

Catalog query params: `search`, `bank_slug`, `network`, `fee_type` (`free`, `lt1k`, `1k5k`, `gt5k`), `has_lounge`, `lounge_type`, `is_popular`, `sort_by` (`popular`, `return`, `return_desc`, `return_asc`, `fee_asc`, `annual_fee_asc`, `fee_desc`, `annual_fee_desc`, `name`), `page`, `limit`.

`meta.applied_filters` echoes the filters that were applied. `search` and `bank_slug` can be sent together.

## Home, banners, promotions

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | `/home` | Optional | Hero, strip, featured promotions, popular cards, categories, collections, quick actions. |
| GET | `/banners` | No | Query: `placement`, `audience`. Live rows only. |
| POST | `/banners/{id}/track` | No | Body: `{"event": "impression"}` or `click`. |
| GET | `/promotions` | No | Query: `featured`, `promo_type`, `category_slug`, `card_slug`. |
| GET | `/promotions/{slug}` | No | One promotion, with description and terms. |
| POST | `/promotions/{id}/track` | No | Same event body. `{id}` is numeric. |

Placements: `home_hero`, `home_strip`, `catalog_top`, `wallet`, `card_detail`, `advisor`.

Audiences: `all`, `guest`, `member`. A row marked `all` matches every request.

Action `type`: `none`, `card`, `category`, `url`, `screen`, `promotion`. See `FRONTEND_GUIDE.md` for the route each target opens.

## Wallet and shortlist

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | `/wallet` and `/user-cards` | Yes | Cards the user holds, ordered by `sort_order`. |
| POST | `/wallet` and `/user-cards` | Yes | Add. Fields: `card_id`, `nickname`, `last_4_digits`, `billing_cycle_day`, `statement_day`, `due_day`. |
| PATCH | `/wallet/{id}` and `/user-cards/{id}` | Yes | Update nickname, last 4, statement day, due day. |
| DELETE | `/wallet/{id}` and `/user-cards/{id}` | Yes | Remove from the wallet. |
| PUT | `/wallet/order` and `/user-cards/order` | Yes | Body: `{"ids": [3, 8, 15]}`. |
| GET | `/wallet/insights` | Yes | Fees, lounge count, next due date, best held card per category. |
| GET | `/saved-cards` | Yes | Shortlist. Not the wallet. |
| POST | `/saved-cards` | Yes | Body: `{"card_id": 12}`. |
| DELETE | `/saved-cards/{card_id}` | Yes | `{card_id}` is the catalog id. |

## Advisor, calculator, reminders

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| POST | `/advisor/recommend` | Optional | Body: `category_slug`, `spend_amount`, `is_international`, optional `card_ids`. Response includes `forex_markup_applied`. |
| POST | `/calculator/annual` | No | Body: `card_id` or `cardId`, and `monthly_spend` or `monthlySpend`. |
| POST | `/notifications/device-token` | Optional | Body: `device_token`, `platform` (`android`, `ios`, `web`). |
| GET | `/notifications/reminders` | Yes | Statement and due reminders. `bank_name` is the real bank. |

## Meta

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| GET | `/meta/legal` | No | Privacy, terms, contact, data deletion. |
| GET | `/meta/config` | No | Min version, maintenance, category order, feature flags. |
| GET | `/meta/faq` | No | Help articles. Group by `topic`. |
| GET | `/health` | No | Process health. |

## Not for the mobile client

Admin sync and admin content require `X-Admin-API-Key`.

| Method | Path |
| :--- | :--- |
| POST | `/admin/sync/trigger` |
| GET | `/admin/sync/status` |
| GET, POST | `/admin/content/banners` |
| PATCH, DELETE | `/admin/content/banners/{id}` |
| GET, POST | `/admin/content/promotions` |
| PATCH, DELETE | `/admin/content/promotions/{id}` |
