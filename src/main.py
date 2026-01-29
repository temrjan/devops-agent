"""Main entry point for DevOps Agent.

Run with: python -m src.main
"""

import asyncio
import logging
import sys

import structlog

from src.bot import create_bot
from src.config import settings


def setup_logging() -> None:
    """Configure structured logging."""
    log_level = logging.DEBUG if settings.debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer()
            if settings.debug
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    """Main entry point."""
    setup_logging()
    logger = structlog.get_logger()

    logger.info("Starting DevOps Agent", debug=settings.debug)

    try:
        bot = await create_bot()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.exception("Fatal error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
