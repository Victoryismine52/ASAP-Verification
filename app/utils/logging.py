"""
Structured logging configuration for the eligibility service.
Call configure_logging() once at application startup.
"""
import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """
    Set up a simple structured (JSON-style) log format.

    Args:
        level: Logging level string, e.g. "DEBUG", "INFO", "WARNING".
    """
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
    )
    # Silence overly verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
