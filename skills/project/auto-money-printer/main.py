# Auto Money Printer — автономная система пассивного заработка
# Точка входа. Запуск: python main.py

import argparse
import asyncio
import logging
import sys
import signal
import time
from config import Config, validate_config
from scheduler_tasks import Scheduler
from utils_logger import setup_logging

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def handle_signal(signum, frame):
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True


def main():
    parser = argparse.ArgumentParser(description="Auto Money Printer v0.1.0")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run once without scheduling (test mode)"
    )
    args = parser.parse_args()

    # Setup logging
    setup_logging()
    logger.info("=" * 60)
    logger.info("  🖨️  Auto Money Printer v0.1.0")
    logger.info("  Легальный пассивный заработок 24/7")
    logger.info("=" * 60)

    # Load and validate config
    try:
        config = Config.from_env()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        logger.error("Copy .env.example to .env and fill in the required fields")
        sys.exit(1)

    if args.check_config:
        errors = validate_config(config)
        if errors:
            logger.error("Configuration errors found:")
            for err in errors:
                logger.error(f"  - {err}")
            sys.exit(1)
        logger.info("✅ Configuration is valid!")
        logger.info(f"  Telegram Bot: {'enabled' if config.tg_bot_token else 'disabled'}")
        logger.info(f"  ePN API: {'enabled' if config.epn_api_key else 'disabled'}")
        logger.info(f"  Admitad API: {'enabled' if config.admitad_client_id else 'disabled'}")
        logger.info(f"  News API: {'enabled' if config.news_api_key else 'disabled'}")
        logger.info(f"  Gemini AI: {'enabled' if config.gemini_api_key else 'disabled'}")
        return

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Initialize scheduler
    scheduler = Scheduler(config)

    if args.dry_run:
        logger.info("🔍 DRY RUN mode — executing all tasks once...")
        scheduler.run_all_once()
        logger.info("✅ Dry run completed! Check logs for results.")
        return

    # Setup periodic schedule
    scheduler.setup_schedule()

    # Main loop
    logger.info("🚀 Starting 24/7 autonomous operation...")
    logger.info("Press Ctrl+C to stop gracefully")

    try:
        while not shutdown_requested:
            scheduler.tick()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        scheduler.shutdown()
        logger.info("👋 Auto Money Printer stopped. До новых встреч!")


if __name__ == "__main__":
    main()
