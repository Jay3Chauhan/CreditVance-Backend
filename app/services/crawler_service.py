"""
Upstream SaveSage Club Crawler Service.
High-resilience asynchronous HTTP client handling pagination, exponential backoff, and polite delays.
"""

import asyncio
import random
from typing import Any, Dict, List, Optional
import httpx
from loguru import logger
from app.core.config import settings
from app.core.exceptions import ExternalServiceError

VALID_TABS = [
    "earn-categories",
    "benefits-and-offers",
    "lounge-access",
    "milestones",
    "redemption-options",
]


class CrawlerService:
    """Async crawler communicating with SaveSage API and Web hosts."""

    def __init__(self):
        self.api_base = settings.SAVESAGE_API_BASE_URL.rstrip("/")
        self.web_base = settings.SAVESAGE_WEB_BASE_URL.rstrip("/")
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        self.timeout = httpx.Timeout(settings.CRAWLER_TIMEOUT_SECONDS, connect=5.0)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Executes HTTP request with exponential backoff and jitter."""
        retries = settings.CRAWLER_MAX_RETRIES
        delay = settings.CRAWLER_REQUEST_DELAY_SECONDS

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            for attempt in range(1, retries + 1):
                try:
                    # Polite jitter delay between requests
                    await asyncio.sleep(delay + random.uniform(0.05, 0.15))

                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_data,
                    )

                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 429:
                        # Rate limited, backoff heavily
                        backoff = (2 ** attempt) + random.uniform(1.0, 3.0)
                        logger.warning(
                            f"HTTP 429 Rate limited at {url}. Backing off for {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    elif response.status_code >= 500:
                        backoff = 1.0 * attempt
                        logger.warning(
                            f"HTTP {response.status_code} at {url} (attempt {attempt}/{retries}). Retrying in {backoff}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.error(
                            f"HTTP {response.status_code} at {url}: {response.text[:200]}"
                        )
                        response.raise_for_status()

                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    if attempt == retries:
                        logger.error(f"Failed request to {url} after {retries} attempts: {e}")
                        raise ExternalServiceError(
                            f"Failed to communicate with upstream service: {str(e)}"
                        )
                    await asyncio.sleep(0.5 * attempt)

    async def fetch_cards_page(
        self, limit: int = 100, cursor: Optional[int] = None
    ) -> Dict[str, Any]:
        """Fetches a single page of cards from /credit-card-filters."""
        url = f"{self.api_base}/credit-card-filters"
        params: Dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor

        data = await self._request_with_retry("GET", url, params=params)
        return data

    async def fetch_all_cards_master(
        self, limit_per_page: int = 100, max_cards: Optional[int] = None
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Iterates cursor pagination until all ~734 cards are retrieved.
        Returns: (all_cards, filter_metadata)
        """
        all_cards: List[Dict[str, Any]] = []
        cursor: Optional[int] = None
        filter_metadata: Dict[str, Any] = {}
        page_num = 1

        logger.info("Starting master cards catalog crawl...")

        while True:
            logger.info(f"Crawling page {page_num} (cursor={cursor}, cards so far={len(all_cards)})...")
            result = await self.fetch_cards_page(limit=limit_per_page, cursor=cursor)

            cards = result.get("cards", [])
            if not cards:
                break

            all_cards.extend(cards)

            # Store filter metadata from the first response
            if not filter_metadata and "filters" in result:
                filter_metadata = result["filters"]

            next_cursor = result.get("nextCursor")

            if max_cards and len(all_cards) >= max_cards:
                all_cards = all_cards[:max_cards]
                logger.info(f"Reached specified max_cards limit of {max_cards}.")
                break

            if next_cursor is None or next_cursor == cursor:
                logger.info("No next cursor returned. Catalog pagination complete.")
                break

            cursor = next_cursor
            page_num += 1

        logger.info(f"Master crawl completed. Total cards retrieved: {len(all_cards)}")
        return all_cards, filter_metadata

    async def fetch_card_tab(self, slug: str, tab: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a specific tab details for a card.
        Tab must be one of VALID_TABS.
        """
        if tab not in VALID_TABS:
            raise ValueError(f"Invalid tab '{tab}'. Must be one of: {VALID_TABS}")

        url = f"{self.api_base}/credit-card/{slug}"
        params = {"tab": tab}

        try:
            data = await self._request_with_retry("GET", url, params=params)
            # Response is typically a list with a single dict
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            elif isinstance(data, dict):
                return data
            return None
        except Exception as e:
            logger.warning(f"Error fetching tab '{tab}' for slug '{slug}': {e}")
            return None

    async def fetch_all_tabs_for_card(self, slug: str) -> Dict[str, Any]:
        """Fetches all 5 tabs for a given card slug sequentially or concurrently with polite delays."""
        results: Dict[str, Any] = {}
        for tab in VALID_TABS:
            tab_data = await self.fetch_card_tab(slug, tab)
            if tab_data:
                results[tab] = tab_data
        return results

    async def fetch_calculator_banks(self) -> List[Dict[str, Any]]:
        """Fetches all 40 indexed banks for the reward calculator."""
        url = f"{self.web_base}/api/reward-calculator/banks"
        data = await self._request_with_retry("GET", url)
        return data if isinstance(data, list) else []

    async def fetch_calculator_categories(self) -> List[Dict[str, Any]]:
        """Fetches all 16 supported spend categories."""
        url = f"{self.web_base}/api/reward-calculator/categories"
        data = await self._request_with_retry("GET", url)
        return data if isinstance(data, list) else []

    async def fetch_calculator_cards_for_bank(self, bank_id: int) -> List[Dict[str, Any]]:
        """Fetches cards mapped to a specific bank under the reward calculator."""
        url = f"{self.web_base}/api/reward-calculator/banks/{bank_id}/cards"
        data = await self._request_with_retry("GET", url)
        return data if isinstance(data, list) else []

    async def query_upstream_calculator(
        self, bank_id: int, card_id: int, category_slug: str, spend_amount: float
    ) -> Dict[str, Any]:
        """Calls upstream calculation endpoint for benchmark comparisons."""
        url = f"{self.web_base}/api/reward-calculator/calculate"
        payload = {
            "bankId": bank_id,
            "cardId": card_id,
            "categorySlug": category_slug,
            "spendAmount": spend_amount,
        }
        return await self._request_with_retry("POST", url, json_data=payload)


# Global Singleton Crawler Instance
crawler_service = CrawlerService()
