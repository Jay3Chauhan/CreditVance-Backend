"""
FastAPI Main Application Entrypoint.
Initializes lifespan, middleware, CORS, routers, and centralized exception handling.
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.database import engine
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging
from app.core.redis_client import redis_service
import app.models  # noqa: F401  — register every table on Base.metadata
from app.models.base import Base
from app.tasks.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")

    # Connect to Redis / in-memory fallback
    await redis_service.connect()

    # Create tables if SQLite (or initial bootstrapping)
    if settings.is_sqlite:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables verified/created.")

    # Start background cron scheduler
    start_scheduler()

    yield

    # --- Shutdown ---
    logger.info("Initiating graceful shutdown...")
    shutdown_scheduler()
    await redis_service.disconnect()
    await engine.dispose()
    logger.info("Application shutdown complete.")


# Initialize FastAPI instance
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise Credit Card Smart Advisor, Reward Calculator, and Ingestion Service",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Attach settings to state for handlers
app.state.settings = settings

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing & tracing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    logger.debug(
        f"{request.method} {request.url.path} completed in {process_time:.2f}ms (status {response.status_code})"
    )
    return response


# Register Centralized Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


# Mount Master v1 Router
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root():
    """Service landing probe."""
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
