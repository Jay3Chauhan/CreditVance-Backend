"""
CLI Script to manually run the SaveSage ingestion pipeline.
Usage:
    python scripts/run_sync.py [--limit 10] [--no-tabs]
"""

import argparse
import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from loguru import logger
from app.core.database import AsyncSessionLocal
from app.services.sync_service import sync_service


async def main():
    parser = argparse.ArgumentParser(description="Synchronize SaveSage Club Credit Card Data")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of cards to crawl (useful for testing, e.g. 5)",
    )
    parser.add_argument(
        "--no-tabs",
        action="store_true",
        help="Skip fetching the 5 sub-tabs (faster initial crawl)",
    )
    args = parser.parse_args()

    logger.info(
        f"Starting manual sync CLI... (limit={args.limit}, sync_tabs={not args.no_tabs})"
    )

    async with AsyncSessionLocal() as session:
        result = await sync_service.execute_sync(
            db=session,
            sync_type="cli_manual",
            sync_tabs=not args.no_tabs,
            limit_cards=args.limit,
        )
        logger.info(f"Sync Result: {result}")
        if result.get("status") == "failed":
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
