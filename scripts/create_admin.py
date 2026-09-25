"""
Admin User Creation & Promotion CLI Script.
Usage:
    python scripts/create_admin.py --email admin@example.com --password SecretPassword123! [--name "Admin Name"]
"""

import argparse
import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from loguru import logger
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def create_or_promote_admin(email: str, password: str, name: str):
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.email == email.lower())
        user = (await session.execute(stmt)).scalar_one_or_none()

        if user:
            logger.info(f"User '{email}' already exists. Promoting to admin and updating password...")
            user.is_admin = True
            user.is_active = True
            user.hashed_password = hash_password(password)
            if name:
                user.full_name = name
            await session.commit()
            logger.info(f"Successfully promoted user '{email}' to ADMIN.")
        else:
            logger.info(f"Creating new admin user '{email}'...")
            admin_user = User(
                email=email.lower(),
                hashed_password=hash_password(password),
                full_name=name or "Administrator",
                is_admin=True,
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            logger.info(f"Successfully created admin user: {email}")


def main():
    parser = argparse.ArgumentParser(description="Create or promote an admin user")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    parser.add_argument("--name", default="Admin", help="Admin display name")

    args = parser.parse_args()

    if len(args.password) < 8:
        logger.error("Password must be at least 8 characters long.")
        sys.exit(1)

    asyncio.run(create_or_promote_admin(args.email, args.password, args.name))


if __name__ == "__main__":
    main()
