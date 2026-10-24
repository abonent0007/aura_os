"""Logging utilities for Auto Money Printer."""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_dir: str = "./logs"):
    """Configure logging to both console and file."""
    # Create logs directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers
    root.handlers.clear()

    # Format
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handler (daily rotation simulated by date in filename)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        Path(log_dir) / f"autoprinter_{today}.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Silence noisy libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("schedule").setLevel(logging.WARNING)
    logging.getLogger("feedparser").setLevel(logging.WARNING)

    root.info("📝 Logging initialized")
