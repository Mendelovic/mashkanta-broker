import logging
import sys
from typing import Optional

from ..config import settings


def setup_logging(log_level: Optional[str] = None) -> None:
    """Setup application logging configuration."""

    # Determine log level
    if log_level is None:
        log_level = "DEBUG" if settings.debug else "INFO"

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Setup application logger
    app_logger = logging.getLogger("app")
    app_logger.setLevel(getattr(logging, log_level.upper()))

    # Suppress noisy third-party loggers
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logging.info(f"Logging setup complete - Level: {log_level}")
