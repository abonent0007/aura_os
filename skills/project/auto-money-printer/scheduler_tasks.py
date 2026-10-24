"""Scheduler — coordinates all periodic tasks."""

import asyncio
import logging
from datetime import datetime
from typing import Optional
import schedule
import time

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages all periodic tasks for the auto-money-printer."""

    def __init__(self, config):
        self.config = config
        self._running = False
        self._tasks_initialized = False

        # Components (lazy init)
        self._bot = None
        self._epn = None
        self._admitad = None
        self._news_collector = None
        self._content_gen = None
        self._tracker = None

        # State
        self._last_post_time: Optional[datetime] = None
        self._post_count_today: int = 0
        self._day_tracker: int = datetime.now().day

    def _init_components(self):
        """Initialize all components lazily."""
        if self._tasks_initialized:
            return

        from telegram_bot import TelegramBot
        from news_collector import NewsCollector
        from content_generator import ContentGenerator
        from analytics_tracker import AnalyticsTracker

        self._bot = TelegramBot(
            token=self.config.tg_bot_token,
            channel_id=self.config.tg_channel_id,
            admin_ids=set(self.config.tg_admin_ids),
        )

        if self.config.epn_api_key:
            from cpa_epn import EPNAPIClient
            self._epn = EPNAPIClient(
                api_key=self.config.epn_api_key,
                user_id=self.config.epn_user_id,
            )

        if self.config.admitad_client_id:
            from cpa_admitad import AdmitadAPIClient
            self._admitad = AdmitadAPIClient(
                client_id=self.config.admitad_client_id,
                client_secret=self.config.admitad_client_secret,
            )

        self._news_collector = NewsCollector(
            rss_feeds=self.config.rss_feeds,
            news_api_key=self.config.news_api_key,
            topics=self.config.news_topics,
        )

        self._content_gen = ContentGenerator(
            gemini_api_key=self.config.gemini_api_key,
        )

        self._tracker = AnalyticsTracker()

        self._tasks_initialized = True
        logger.info("✅ All components initialized")

    def setup_schedule(self):
        """Configure and start periodic tasks."""
        self._init_components()
        cfg = self.config

        # Autopost every N hours
        schedule.every(cfg.tg_posting_interval_hours).hours.do(
            lambda: asyncio.get_event_loop().run_until_complete(self._do_autopost())
        )

        # Daily ad at configured hour
        schedule.every().day.at(f"{cfg.tg_ad_message_hour:02d}:00").do(
            lambda: asyncio.get_event_loop().run_until_complete(self._do_daily_ad())
        )

        # Check new offers
        schedule.every(cfg.check_new_offers_interval_hours).hours.do(
            lambda: asyncio.get_event_loop().run_until_complete(self._do_check_offers())
        )

        # Process bot updates every 30 seconds
        schedule.every(30).seconds.do(
            lambda: asyncio.get_event_loop().run_until_complete(self._bot.process_updates())
        )

        # Reset daily counter at midnight
        schedule.every().day.at("00:00").do(self._reset_daily_counters)

        logger.info("📅 Schedule configured")

    def tick(self):
        """Main loop tick — called every second by main()."""
        schedule.run_pending()

    def run_all_once(self):
        """Execute all tasks once (dry-run / test mode)."""
        self._init_components()
        logger.info("🔍 Running all tasks once...")

        loop = asyncio.get_event_loop()

        loop.run_until_complete(self._bot.process_updates())
        logger.info("  ✓ Bot updates processed")

        loop.run_until_complete(self._do_autopost())
        logger.info("  ✓ Autopost completed")

        loop.run_until_complete(self._do_check_offers())
        logger.info("  ✓ Offers checked")

        loop.run_until_complete(self._do_daily_ad())
        logger.info("  ✓ Daily ad check completed")

        # Show stats
        logger.info(self._tracker.get_today_summary())

    def shutdown(self):
        """Clean shutdown — close all connections."""
        self._running = False

        async def _close_all():
            if self._bot:
                await self._bot.close()
            if self._epn:
                await self._epn.close()
            if self._admitad:
                await self._admitad.close()
            if self._news_collector:
                await self._news_collector.close()
            if self._content_gen:
                await self._content_gen.close()

        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_close_all())
        except Exception:
            pass

        logger.info("Scheduler shutdown complete")

    def _reset_daily_counters(self):
        """Reset daily counters at midnight."""
        self._post_count_today = 0
        self._day_tracker = datetime.now().day
        logger.info("📅 Daily counters reset")

    # ─── Task implementations ─────────────────────────────────

    async def _do_autopost(self):
        """Collect news → generate post → publish to channel."""
        try:
            news_items = await self._news_collector.collect_all(max_items=5)
            if not news_items:
                logger.info("No news items collected, skipping post")
                return

            item = news_items[0]

            # Get CPA link
            cpa_link = ""
            if self._epn:
                offers = await self._epn.get_offers(limit=1)
                if offers:
                    cpa_link = await self._epn.get_deep_link(offers[0].offer_id, "autopost")

            # Generate and post
            post = await self._content_gen.generate_news_post(
                title=item.title,
                summary=item.summary,
                source_url=item.url,
                cpa_link=cpa_link,
            )

            if self._bot:
                success = await self._bot.broadcast_to_channel(post)
                if success:
                    self._last_post_time = datetime.now()
                    self._post_count_today += 1
                    self._tracker.record_post()
                    logger.info(f"📢 Posted: {item.title[:60]}...")

        except Exception as e:
            logger.error(f"Autopost error: {e}")

    async def _do_daily_ad(self):
        """Send daily ad to all subscribers (with anti-spam)."""
        if not self._bot or self._bot.subscriber_count == 0:
            logger.debug("No subscribers, skipping daily ad")
            return

        cfg = self.config
        if cfg.max_subscribers_for_ads > 0 and self._bot.subscriber_count < cfg.max_subscribers_for_ads:
            logger.debug(f"Subscribers ({self._bot.subscriber_count}) below threshold ({cfg.max_subscribers_for_ads})")
            return

        # Get an offer
        offer = None
        if self._epn:
            offers = await self._epn.get_offers(limit=1)
            if offers:
                offer = offers[0]
                offer.deep_link = await self._epn.get_deep_link(offer.offer_id, "daily_ad")
        if not offer and self._admitad:
            offers = await self._admitad.get_offers(limit=1)
            if offers:
                offer = offers[0]
                offer.deep_link = await self._admitad.get_deep_link(offer.offer_id, "daily_ad")

        if not offer:
            logger.info("No offers available for daily ad")
            return

        ad_text = await self._content_gen.generate_post(
            title=offer.title,
            summary=offer.description,
            cpa_link=offer.deep_link or offer.url,
            use_ai=True,
        )

        sent_count = 0
        for chat_id in list(self._bot._subscribers):
            success = await self._bot.send_ad_to_subscriber(chat_id, ad_text)
            if success:
                sent_count += 1

        if sent_count > 0:
            logger.info(f"💸 Daily ad sent to {sent_count} subscribers")
        else:
            logger.debug("Daily ad: no new recipients (anti-spam)")

    async def _do_check_offers(self):
        """Periodically refresh CPA offers."""
        if self._epn:
            offers = await self._epn.get_offers(limit=5)
            logger.debug(f"ePN: {len(offers)} active offers")
        if self._admitad:
            offers = await self._admitad.get_offers(limit=5)
            logger.debug(f"Admitad: {len(offers)} active offers")
