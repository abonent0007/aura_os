import re
from html.parser import HTMLParser
from typing import Callable, Optional
from xml.etree import ElementTree as ET

from .models import Order

Fetcher = Callable[[str], str]
ATOM_NS = "http://www.w3.org/2005/Atom"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    extractor = _TextExtractor()
    extractor.feed(raw)
    extractor.close()
    return re.sub(r"\s+", " ", extractor.text()).strip()


def _text(element: ET.Element, tag: str, namespace: str = "") -> str:
    prefix = f"{{{namespace}}}" if namespace else ""
    child = element.find(f"{prefix}{tag}")
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _rss_order(item: ET.Element, source: str) -> Optional[Order]:
    title = strip_html(_text(item, "title"))
    if not title:
        return None
    link = _text(item, "link")
    external_id = _text(item, "guid") or link
    if not external_id:
        return None
    return Order(
        source=source,
        external_id=external_id,
        title=title,
        description=strip_html(_text(item, "description")),
        url=link,
        published_at=_text(item, "pubDate") or None,
    )


def _atom_order(entry: ET.Element, source: str) -> Optional[Order]:
    title = strip_html(_text(entry, "title", ATOM_NS))
    if not title:
        return None
    link_element = entry.find(f"{{{ATOM_NS}}}link")
    url = link_element.get("href", "") if link_element is not None else ""
    external_id = _text(entry, "id", ATOM_NS) or url
    if not external_id:
        return None
    description = _text(entry, "summary", ATOM_NS) or _text(entry, "content", ATOM_NS)
    return Order(
        source=source,
        external_id=external_id,
        title=title,
        description=strip_html(description),
        url=url,
        published_at=_text(entry, "updated", ATOM_NS) or None,
    )


def parse_feed(xml_text: str, source: str) -> list[Order]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = root.findall(".//item")
    if items:
        return [order for order in (_rss_order(item, source) for item in items) if order is not None]
    entries = root.findall(f".//{{{ATOM_NS}}}entry")
    return [order for order in (_atom_order(entry, source) for entry in entries) if order is not None]


class FeedCollector:
    def __init__(self, name: str, url: str, fetcher: Fetcher, filter_config=None) -> None:
        self.name = name
        self.url = url
        self.fetcher = fetcher
        self.filter_config = filter_config  # свой FilterConfig для источника (опционально)

    def collect(self) -> list[Order]:
        return parse_feed(self.fetcher(self.url), self.name)
