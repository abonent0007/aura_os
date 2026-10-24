"""News collector — gathers content from RSS feeds and NewsAPI (free tier)."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import feedparser
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    summary: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""
    topic: str = ""


class NewsCollector:
    """Collects news from multiple free sources."""

    def __init__(self, rss_feeds: list[str] = None, news_api_key: str = "", topics: list[str] = None):
        self.rss_feeds = rss_feeds or []
        self.news_api_key = news_api_key
        self.topics = topics or ["технологии"]
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def collect_all(self, max_items: int = 10) -> list[NewsItem]:
        """Collect news from all available sources."""
        items: list[NewsItem] = []

        # 1. RSS feeds (always free, no API key needed)
        for feed_url in self.rss_feeds:
            rss_items = await self._fetch_rss(feed_url, max_items)
            items.extend(rss_items)

        # 2. NewsAPI (free tier: 100 req/day)
        if self.news_api_key:
            api_items = await self._fetch_newsapi(max_items)
            items.extend(api_items)

        # Deduplicate by URL
        seen = set()
        unique = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        return unique[:max_items * 2]

    async def _fetch_rss(self, feed_url: str, limit: int) -> list[NewsItem]:
        """Fetch and parse an RSS feed."""
        items = []
        try:
            # feedparser is synchronous, but fine for RSS
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit]:
                items.append(NewsItem(
                    title=entry.get("title", "Без названия"),
                    summary=self._clean_html(entry.get("summary", "")[:300]),
                    url=entry.get("link", ""),
                    source=feed.feed.get("title", feed_url),
                    published_at=entry.get("published", ""),
                ))
            logger.debug(f"RSS {feed_url}: {len(items)} items")
        except Exception as e:
            logger.error(f"RSS fetch error ({feed_url}): {e}")
        return items

    async def _fetch_newsapi(self, limit: int) -> list[NewsItem]:
        """Fetch from NewsAPI (requires API key)."""
        items = []
        try:
            session = await self._get_session()
            for topic in self.topics[:3]:  # limit topics to save free tier quota
                async with session.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": topic,
                        "language": "ru",
                        "pageSize": min(limit, 10),
                        "apiKey": self.news_api_key,
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for article in data.get("articles", []):
                            items.append(NewsItem(
                                title=article.get("title", "Без названия"),
                                summary=(article.get("description") or "")[:300],
                                url=article.get("url", ""),
                                source=article.get("source", {}).get("name", "NewsAPI"),
                                published_at=article.get("publishedAt", ""),
                                topic=topic,
                            ))
                    else:
                        logger.warning(f"NewsAPI returned {resp.status}")
        except Exception as e:
            logger.error(f"NewsAPI fetch error: {e}")
        return items

    def _clean_html(self, text: str) -> str:
        """Strip basic HTML tags."""
        import re
        return re.sub(r'<[^>]+>', '', text)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
