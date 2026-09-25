"""
Seed Demo Data Script.
Seeds sample banks, categories, and top popular cards for instant offline development and testing.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.models.bank import Bank
from app.models.card import CreditCard
from app.models.card_tab import CardTab
from app.models.category import SpendCategory


async def seed_data():
    async with AsyncSessionLocal() as db:
        logger.info("Seeding sample banks and categories...")

        # Banks
        banks_data = [
            {"slug": "hdfc", "name": "HDFC", "logo_url": "https://d3dx7t8uh9asmu.cloudfront.net/bank_square/HDFC.png", "savesage_bank_id": 1},
            {"slug": "icici", "name": "ICICI", "logo_url": "https://d3dx7t8uh9asmu.cloudfront.net/bank_square/ICICI.png", "savesage_bank_id": 3},
            {"slug": "axis", "name": "Axis", "logo_url": "https://d3dx7t8uh9asmu.cloudfront.net/bank_square/AXIS.png", "savesage_bank_id": 4},
            {"slug": "sbi", "name": "SBI", "logo_url": "https://d3dx7t8uh9asmu.cloudfront.net/bank_square/SBI.png", "savesage_bank_id": 2},
        ]

        bank_map = {}
        for b in banks_data:
            stmt = select(Bank).where(Bank.slug == b["slug"])
            bank = (await db.execute(stmt)).scalar_one_or_none()
            if not bank:
                bank = Bank(**b)
                db.add(bank)
                await db.flush()
            bank_map[b["slug"]] = bank

        # Categories
        categories_data = [
            {"slug": "Dining", "name": "Dining", "savesage_category_id": 8},
            {"slug": "Flights", "name": "Flights", "savesage_category_id": 1},
            {"slug": "Fuel", "name": "Fuel", "savesage_category_id": 3},
            {"slug": "Grocery", "name": "Grocery", "savesage_category_id": 6},
            {"slug": "Online Shopping", "name": "Online Shopping", "savesage_category_id": 11},
            {"slug": "Rent", "name": "Rent", "savesage_category_id": 12},
            {"slug": "Travel", "name": "Travel", "savesage_category_id": 13},
            {"slug": "Utilities", "name": "Utilities", "savesage_category_id": 15},
        ]

        for c in categories_data:
            stmt = select(SpendCategory).where(SpendCategory.slug == c["slug"])
            cat = (await db.execute(stmt)).scalar_one_or_none()
            if not cat:
                db.add(SpendCategory(**c))

        await db.commit()

        # Seed Cards
        cards_data = [
            {
                "slug": "hdfc-infinia-metal",
                "title": "HDFC Infinia Metal Credit Card",
                "display_name": "Infinia Metal",
                "bank_id": bank_map["hdfc"].id,
                "joining_fee": 12500.0,
                "renewal_fee": 12500.0,
                "forex_markup_percent": 2.0,
                "return_percentage_raw": "3.3% to 33.3%",
                "return_min_percent": 3.3,
                "return_max_percent": 33.3,
                "network_type": "VISA",
                "lounge_types": ["DOMESTIC_LOUNGE", "INTERNATIONAL_LOUNGE"],
                "benefit_types": ["DINING", "GOLF", "INSURANCE", "CONCIERGE"],
                "is_popular": True,
                "is_currently_issuing": True,
                "card_image_url": "https://d3dx7t8uh9asmu.cloudfront.net/creditcardimages/INFINIA%20METAL%20EDITION.png",
                "overview_text": "Super premium metal card offering industry-leading reward rates on dining and SmartBuy travel.",
                "earn_tab": {
                    "tabData": {
                        "type": "earn-categories",
                        "earnRows": [
                            {"name": "Base Rewards", "points": 5, "per": 150, "unit": "RPs"},
                            {"name": "Dining", "category": "Dining", "points": 25, "per": 150, "unit": "RPs"},
                            {"name": "Flights", "category": "Flights", "points": 25, "per": 150, "unit": "RPs"},
                        ],
                        "exclusions": [{"name": "Rent", "category": "Rent"}, {"name": "Fuel", "category": "Fuel"}]
                    }
                }
            },
            {
                "slug": "icici-rubyx-mastercard",
                "title": "ICICI Rubyx (Mastercard) Credit Card",
                "display_name": "Rubyx (Mastercard)",
                "bank_id": bank_map["icici"].id,
                "joining_fee": 3000.0,
                "renewal_fee": 2000.0,
                "forex_markup_percent": 3.5,
                "return_percentage_raw": "0.5% to 1%",
                "return_min_percent": 0.5,
                "return_max_percent": 1.0,
                "network_type": "MASTERCARD",
                "lounge_types": ["DOMESTIC_LOUNGE", "RAILWAY_LOUNGE"],
                "benefit_types": ["MOVIES_AND_EVENTS", "GOLF"],
                "is_popular": True,
                "is_currently_issuing": True,
                "card_image_url": "https://d3dx7t8uh9asmu.cloudfront.net/Mapped/ICICI.webp",
                "overview_text": "Lifestyle card offering milestone perks and dining vouchers.",
                "earn_tab": {
                    "tabData": {
                        "type": "earn-categories",
                        "earnRows": [
                            {"name": "Base Rewards", "points": 2, "per": 100, "unit": "RPs"},
                            {"name": "Grocery", "category": "Grocery", "points": 2, "per": 100, "unit": "RPs"},
                        ],
                        "exclusions": [{"name": "Rent", "category": "Rent"}, {"name": "Fuel", "category": "Fuel"}]
                    }
                }
            },
            {
                "slug": "sbi-cashback-credit-card",
                "title": "SBI Cashback Credit Card",
                "display_name": "Cashback SBI Card",
                "bank_id": bank_map["sbi"].id,
                "joining_fee": 999.0,
                "renewal_fee": 999.0,
                "forex_markup_percent": 3.5,
                "return_percentage_raw": "1% to 5%",
                "return_min_percent": 1.0,
                "return_max_percent": 5.0,
                "network_type": "VISA",
                "lounge_types": [],
                "benefit_types": ["CASHBACK"],
                "is_popular": True,
                "is_currently_issuing": True,
                "card_image_url": "https://d3dx7t8uh9asmu.cloudfront.net/creditcardimages/CASHBACK_SBI.png",
                "overview_text": "Direct 5% cashback on all online spends without merchant restrictions.",
                "earn_tab": {
                    "tabData": {
                        "type": "earn-categories",
                        "earnRows": [
                            {"name": "Online Shopping", "category": "Online Shopping", "points": 5, "per": 100, "unit": "INR"},
                            {"name": "Base Rewards", "points": 1, "per": 100, "unit": "INR"},
                        ],
                        "exclusions": [{"name": "Rent", "category": "Rent"}, {"name": "Fuel", "category": "Fuel"}, {"name": "Wallets", "category": "Wallets"}]
                    }
                }
            }
        ]

        for c_data in cards_data:
            earn_tab = c_data.pop("earn_tab", None)
            stmt = select(CreditCard).where(CreditCard.slug == c_data["slug"])
            card = (await db.execute(stmt)).scalar_one_or_none()
            if not card:
                card = CreditCard(**c_data, last_synced_at=datetime.now(timezone.utc))
                db.add(card)
                await db.flush()

            if earn_tab:
                tab_stmt = select(CardTab).where(CardTab.card_id == card.id, CardTab.tab_name == "earn-categories")
                tab = (await db.execute(tab_stmt)).scalar_one_or_none()
                if not tab:
                    db.add(CardTab(card_id=card.id, tab_name="earn-categories", raw_content=earn_tab))

        await db.commit()
        logger.info("Demo data seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_data())
