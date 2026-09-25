"""
Health Check and Uptime Probes.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.core.config import settings
from app.core.redis_client import redis_service
from app.schemas.common import ApiResponse, HealthStatus

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Deep health check probing Neon PostgreSQL and Upstash Redis."""
    # Check DB
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    # Check Redis
    redis_status = "healthy"
    try:
        is_redis_alive = await redis_service.ping()
        if not is_redis_alive:
            redis_status = "degraded (fallback active)"
    except Exception as e:
        redis_status = f"degraded: {str(e)}"

    status_str = "healthy" if db_status == "healthy" else "unhealthy"

    health = HealthStatus(
        status=status_str,
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    return ApiResponse(
        success=(status_str == "healthy"),
        message=f"Service status: {status_str}",
        data=health,
    )
