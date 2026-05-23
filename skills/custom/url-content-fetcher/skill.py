# url-content-fetcher/skill.py
# Захватывает содержимое веб-страниц по URL

import re, json
from urllib.parse import urlparse
from autogen.beta import tools

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# URL-регулярка
URL_RE = re.compile(r'https?://[^\s<>\[\]()\"\'，。！？、；：""''）（》《\u200b]+', re.IGNORECASE)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
MAX_CONTENT = 5000


def _is_image(url: str) -> bool:
    try:
        path = urlparse(url).path.lower().split("?")[0]
        return any(path.endswith(ext) for ext in IMAGE_EXTS)
    except Exception:
        return False


async def _fetch_text(url: str) -> str:
    """Захватывает текст страницы."""
    if not HAS_HTTPX:
        return f"[Ошибка: httpx не установлен. pip install httpx]"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={"User-Agent": "AURA-OS/1.0"})
        resp.raise_for_status()
        html = resp.text

    # Простой HTML-to-text
    text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                          ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(entity, char)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CONTENT]


def _extract_urls(text: str) -> list:
    """Извлекает все URL из текста (кроме картинок)."""
    seen = set()
    urls = []
    for m in URL_RE.finditer(text):
        url = m.group().rstrip(".,;:!?。，；：！？")
        if url not in seen and not _is_image(url):
            seen.add(url)
            urls.append(url)
    return urls


@tools.tool
def fetch_url_content(text: str) -> str:
    """
    Находит URL в тексте, захватывает содержимое страниц и заменяет ссылки текстом.
    Поддерживает обычные сайты. Для Twitter/Reddit использует прямые запросы.
    """
    import asyncio

    if not HAS_HTTPX:
        return "Модуль httpx не установлен. Выполни: pip install httpx"

    urls = _extract_urls(text)
    if not urls:
        return "URL не найдены в тексте."

    lines = [f"Найдено URL: {len(urls)}\n"]

    async def _fetch_all():
        for url in urls[:3]:  # максимум 3 ссылки
            try:
                content = await _fetch_text(url)
                lines.append(f"[Содержимое {url}]:\n{content[:1000]}\n")
            except Exception as e:
                lines.append(f"[Ошибка захвата {url}]: {e}\n")

    asyncio.run(_fetch_all())
    return "\n".join(lines)


@tools.tool
def detect_urls(text: str) -> str:
    """
    Находит все URL в тексте и сообщает какие ссылки обнаружены (без захвата содержимого).
    """
    urls = _extract_urls(text)
    if not urls:
        return "Ссылки не найдены."

    lines = [f"Найдено ссылок: {len(urls)}"]
    for i, url in enumerate(urls, 1):
        host = urlparse(url).netloc or "неизвестный хост"
        lines.append(f"  {i}. {host} — {url[:80]}")

    return "\n".join(lines)
