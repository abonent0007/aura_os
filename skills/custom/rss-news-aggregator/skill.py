# rss-news-aggregator/skill.py
# RSS News Aggregator: Moscow, MOEX, Gosuslugi, Yandex

import sys, re, threading, asyncio
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from autogen.beta import tools

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import run_async

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

RSS_FEEDS = {
    "Москва": [
        ("Mos.ru", "https://www.mos.ru/rss"),
        ("Lenta.ru Москва", "https://lenta.ru/rss"),
    ],
    "Россия": [
        ("Lenta.ru", "https://lenta.ru/rss"),
        ("RIA Новости", "https://ria.ru/export/rss2/archive.xml"),
    ],
    "Мир": [
        ("Lenta.ru", "https://lenta.ru/rss"),
    ],
    "Бизнес": [
        ("Lenta.ru Экономика", "https://lenta.ru/rss"),
        ("Rambler", "https://news.rambler.ru/rss/"),
    ],
    "Спорт": [
        ("Lenta.ru Спорт", "https://lenta.ru/rss"),
    ],
}


def _fetch_feed(url: str, timeout: int = 10) -> str:
    """Получить RSS-ленту."""
    if not HAS_HTTPX:
        return ""
    async def _get():
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, headers={"User-Agent": "AURA-OS/1.0"}, follow_redirects=True)
            return r.text if r.status_code == 200 else ""
    return run_async(_get(), timeout + 5) or ""


def _parse_rss(xml_text: str, limit: int = 5) -> list:
    """Разобрать RSS XML в список новостей."""
    items = []
    try:
        root = ET.fromstring(xml_text)

        # RSS 2.0 format
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            # Clean HTML from description
            desc = re.sub(r"<[^>]+>", "", desc)[:200]
            title = re.sub(r"<[^>]+>", "", title)[:150]

            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "date": pub_date[:25] if pub_date else "",
                })

        # Atom format
        if not items:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns) or root.findall(".//entry"):
                title = entry.findtext("atom:title", "", ns) or entry.findtext("title", "").strip()
                link_el = entry.find("atom:link", ns) or entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                desc = entry.findtext("atom:summary", "", ns) or entry.findtext("summary", "").strip()
                updated = entry.findtext("atom:updated", "", ns) or entry.findtext("updated", "").strip()
                title = re.sub(r"<[^>]+>", "", title)[:150]
                desc = re.sub(r"<[^>]+>", "", desc)[:200]
                if title:
                    items.append({
                        "title": title,
                        "link": link,
                        "description": desc,
                        "date": updated[:19] if updated else "",
                    })
    except ET.ParseError:
        pass
    except Exception:
        pass

    return items[:limit]


@tools.tool
def get_news(category: str = "all") -> str:
    """
    Получить свежие новости по категории.
    category: Москва, Россия, Мир, Бизнес, Спорт, или all (все).
    """
    if not HAS_HTTPX:
        return "News aggregator requires httpx."

    # Всегда тянем lenta.ru (основной источник), потом фильтруем
    xml = _fetch_feed("https://lenta.ru/rss")
    if not xml:
        return "News unavailable — network issue. Try again later."

    items = _parse_rss(xml, limit=20)
    if not items:
        return "No news parsed."

    # Фильтр по категории (по RSS-тегам внутри item)
    if category.lower() != "all":
        cat_lower = category.lower()
        filtered = []
        for item in items:
            title = item.get("title", "").lower()
            desc = item.get("description", "").lower()
            # Rough keyword matching
            if cat_lower in title or cat_lower in desc:
                filtered.append(item)
        if filtered:
            items = filtered[:8]

    lines = [f"News digest — {datetime.now().strftime('%d.%m.%Y %H:%M')}"]
    if category.lower() != "all":
        lines[0] += f" | {category.upper()}"

    for i, item in enumerate(items[:8], 1):
        lines.append(f"{i}. {item['title']}")

    lines.append(f"\nSource: lenta.ru | {len(items[:8])} headlines")
    return "\n".join(lines)


@tools.tool
def search_news_by_topic(topic: str) -> str:
    """
    Поиск новостей по конкретной теме через Google News RSS.
    topic: ключевые слова (например: 'Москва', 'криптовалюта', 'спорт')
    """
    import urllib.parse
    encoded = urllib.parse.quote(topic)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ru&gl=RU&ceid=RU:ru"

    xml = _fetch_feed(url, timeout=15)
    if not xml:
        # Fallback: use lenta.ru with keyword filter
        xml = _fetch_feed("https://lenta.ru/rss")
        if not xml:
            return "News unavailable — network issue."
        items = _parse_rss(xml, limit=30)
        topic_lower = topic.lower()
        filtered = [i for i in items if topic_lower in i.get("title", "").lower() or topic_lower in i.get("description", "").lower()]
        if not filtered:
            return f"No news found for topic '{topic}'."
        items = filtered[:10]
    else:
        items = _parse_rss(xml, limit=10)

    lines = [f"News for: {topic}", f"Source: {'Google News' if xml else 'Lenta.ru'}"]
    lines.append("")
    for i, item in enumerate(items[:6], 1):
        lines.append(f"{i}. {item['title']}")

    return "\n".join(lines)


@tools.tool
def list_news_sources() -> str:
    """Показать все источники новостей по категориям."""
    lines = ["RSS News Sources:"]
    for cat, feeds in RSS_FEEDS.items():
        lines.append(f"\n{cat}:")
        for name, url in feeds:
            lines.append(f"  {name}: {url}")
    return "\n".join(lines)
