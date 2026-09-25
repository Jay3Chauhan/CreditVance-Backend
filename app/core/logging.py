"""
Structured Logging Configuration with Loguru.
Formats logs as structured JSON in production and readable colored text in development.
"""

import sys
from loguru import logger
from app.core.config import settings


def setup_logging():
    logger.remove()

    if settings.is_production:
        # JSON formatting for production log collectors (Datadog, CloudWatch, Loki)
        log_format = (
            "{time:YYYY-MM-DDTHH:mm:ss.SSSZ} | {level} | "
            "{name}:{function}:{line} | {message}"
        )
        logger.add(
            sys.stdout,
            format=log_format,
            level="INFO",
            serialize=True,
            backtrace=True,
            diagnose=False,
        )
    else:
        # High readability colored format for local dev and debugging
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stderr,
            format=log_format,
            level="DEBUG" if settings.DEBUG else "INFO",
            colorize=True,
        )

    return logger
