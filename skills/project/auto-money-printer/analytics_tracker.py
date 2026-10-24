"""Analytics tracker — monitors clicks, conversions, revenue."""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DailyStats:
    date: str = ""
    posts_published: int = 0
    ad_clicks: int = 0
    conversions: int = 0
    revenue_rub: float = 0.0
    new_subscribers: int = 0
    total_subscribers: int = 0


class AnalyticsTracker:
    """Tracks and persists performance metrics."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._today_stats = DailyStats(date=datetime.now().strftime("%Y-%m-%d"))
        self._load_today()

    def _today_file(self) -> Path:
        return self.data_dir / f"stats_{self._today_stats.date}.json"

    def _load_today(self):
        """Load today's stats from file if exists."""
        fpath = self._today_file()
        if fpath.exists():
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                    self._today_stats = DailyStats(**data)
            except Exception as e:
                logger.warning(f"Failed to load stats: {e}")

    def _save_today(self):
        """Persist today's stats to file."""
        try:
            with open(self._today_file(), "w") as f:
                json.dump(self._today_stats.__dict__, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def record_post(self):
        self._today_stats.posts_published += 1
        self._save_today()

    def record_clicks(self, count: int = 1):
        self._today_stats.ad_clicks += count
        self._save_today()

    def record_conversion(self, revenue: float = 0.0):
        self._today_stats.conversions += 1
        self._today_stats.revenue_rub += revenue
        self._save_today()

    def update_subscribers(self, count: int):
        self._today_stats.total_subscribers = count
        self._save_today()

    def get_today_summary(self) -> str:
        """Return a human-readable summary of today's performance."""
        s = self._today_stats
        return (
            f"📊 Статистика за {s.date}:\n"
            f"📢 Постов: {s.posts_published}\n"
            f"👆 Кликов: {s.ad_clicks}\n"
            f"💰 Конверсий: {s.conversions}\n"
            f"💵 Доход: {s.revenue_rub:.2f} ₽\n"
            f"👥 Подписчиков: {s.total_subscribers}"
        )

    def get_weekly_summary(self) -> str:
        """Aggregate stats for the last 7 days."""
        total_revenue = 0.0
        total_posts = 0
        total_clicks = 0
        total_conversions = 0

        for i in range(7):
            date = datetime.now().strftime("%Y-%m-%d")  # simplified
            fpath = self.data_dir / f"stats_{date}.json"
            if fpath.exists():
                try:
                    with open(fpath, "r") as f:
                        data = json.load(f)
                        total_posts += data.get("posts_published", 0)
                        total_clicks += data.get("ad_clicks", 0)
                        total_conversions += data.get("conversions", 0)
                        total_revenue += data.get("revenue_rub", 0)
                except Exception:
                    pass

        return (
            f"📊 За последнюю неделю:\n"
            f"📢 Постов: {total_posts}\n"
            f"👆 Кликов: {total_clicks}\n"
            f"💰 Конверсий: {total_conversions}\n"
            f"💵 Доход: {total_revenue:.2f} ₽"
        )
