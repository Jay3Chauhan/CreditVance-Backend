"""
Application Configuration Module.
Loads environment variables using Pydantic Settings with type validation.
"""

from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application Basics
    ENVIRONMENT: str = "development"
    APP_NAME: str = "Credit Card Smart Advisor API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # Database Settings (Neon PostgreSQL / asyncpg / aiosqlite for tests)
    DATABASE_URL: str = "sqlite+aiosqlite:///./credit_cards.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30

    # Redis Settings (Upstash Redis)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    REDIS_CACHE_TTL_SECONDS: int = 3600  # 1 hour
    REDIS_SYNC_LOCK_TTL_SECONDS: int = 7200  # 2 hours

    # Authentication & Security
    JWT_SECRET_KEY: str = "development-secret-key-change-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    ADMIN_API_KEY: str = "admin-secret-sync-key"

    # Upstream SaveSage Ingestion Configuration
    SAVESAGE_API_BASE_URL: str = "https://api.savesage.club"
    SAVESAGE_WEB_BASE_URL: str = "https://savesage.club"
    CRAWLER_CONCURRENCY: int = 5
    CRAWLER_REQUEST_DELAY_SECONDS: float = 0.25
    CRAWLER_MAX_RETRIES: int = 3
    CRAWLER_TIMEOUT_SECONDS: int = 15

    # Cron Job Scheduling
    CRON_SYNC_ENABLED: bool = True
    CRON_SYNC_SCHEDULE: str = "0 2 * * 0"  # Every Sunday 02:00 AM UTC

    # Firebase Cloud Messaging
    FIREBASE_ENABLED: bool = True
    FIREBASE_CREDENTIALS_PATH: str = "secrets/firebase-adminsdk.json"
    CRON_PUSH_ENABLED: bool = True
    # 03:30 UTC is 09:00 in India, so "due today" matches the user's calendar date.
    CRON_PUSH_SCHEDULE: str = "30 3 * * *"

    @property
    def resolved_firebase_credentials_path(self) -> Path:
        """Absolute path to the service-account JSON. Relative paths start at the repo root."""
        path = Path(self.FIREBASE_CREDENTIALS_PATH)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        return path

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def async_database_url(self) -> str:
        """
        Normalizes database URLs to async drivers.
        Converts postgresql:// and postgres:// to postgresql+asyncpg://
        and normalizes Neon SSL query parameters.
        """
        url = self.DATABASE_URL.strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        # Handle Neon/cloud parameters for asyncpg compatibility
        if "sslmode=require" in url:
            url = url.replace("sslmode=require", "ssl=require")
        if "channel_binding=require" in url:
            url = (
                url.replace("&channel_binding=require", "")
                .replace("channel_binding=require&", "")
                .replace("channel_binding=require", "")
            )
        return url

    @property
    def clean_redis_url(self) -> str:
        """Strips quotes and accidental REDIS_URL= prefix from REDIS_URL."""
        url = self.REDIS_URL.strip()
        if url.startswith("REDIS_URL="):
            url = url.replace("REDIS_URL=", "", 1).strip()
        url = url.strip("\"'")
        return url


# Global Singleton Settings Instance
settings = Settings()
