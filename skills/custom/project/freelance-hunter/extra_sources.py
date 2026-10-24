"""extra_sources.py — расширенный поиск заказов для freelance-hunter.

Ядро программы умеет только RSS. Этот модуль добавляет:
  * источники с полем kind: html (kwork, youdo) — разбор страницы по pattern
  * браузерный User-Agent (часть досок отдаёт 403 на «бота»)
  * тот же конвейер, что и у ядра: фильтры → оценка DeepSeek → orders.db

Запуск:
    python extra_sources.py --config config.yaml          # поиск
    python extra_sources.py --config config.yaml --probe  # проверка источников
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import yaml

from freelance_hunter.cli import OpenAICompatibleClient
from freelance_hunter.collector import FeedCollector, parse_feed, strip_html
from freelance_hunter.config import load_config
from freelance_hunter.estimator import Estimator
from freelance_hunter.filters import FilterConfig
from freelance_hunter.models import Order
from freelance_hunter.notifier import NullNotifier
from freelance_hunter.pipeline import Pipeline
from freelance_hunter.storage import Storage

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def http_fetch(url: str, timeout: float = 20.0) -> str:
    import httpx

    response = httpx.get(
        url,
        timeout=httpx.Timeout(timeout, connect=5.0),
        follow_redirects=True,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        },
    )
    response.raise_for_status()
    return response.text


def parse_html(text: str, source: str, pattern: str, base: str = "") -> list[Order]:
    """Карточки заказов из HTML по regex с группами url/title/desc."""
    if not text or not pattern:
        return []
    orders: list[Order] = []
    seen: set[str] = set()
    for match in re.finditer(pattern, text, re.S | re.I):
        groups = match.groupdict()
        url = (groups.get("url") or "").strip()
        title = strip_html(groups.get("title") or "")
        if not url or not title or url in seen:
            continue
        seen.add(url)
        if base and url.startswith("/"):
            url = base.rstrip("/") + url
        orders.append(
            Order(
                source=source,
                external_id=url,
                title=title,
                description=strip_html(groups.get("desc") or ""),
                url=url,
            )
        )
    return orders


class HtmlCollector:
    def __init__(self, name: str, url: str, pattern: str, fetcher, base: str = "") -> None:
        self.name = name
        self.url = url
        self.pattern = pattern
        self.base = base
        self.fetcher = fetcher

    def collect(self) -> list[Order]:
        return parse_html(self.fetcher(self.url), self.name, self.pattern, self.base)


def make_collector(item: dict, fetcher):
    if str(item.get("kind", "rss")).lower() == "html":
        return HtmlCollector(
            name=str(item["name"]),
            url=str(item["url"]),
            pattern=str(item.get("pattern", "")),
            fetcher=fetcher,
            base=str(item.get("base", "")),
        )
    return FeedCollector(name=str(item["name"]), url=str(item["url"]), fetcher=fetcher)


def raw_sources(cfg_path: str) -> list[dict]:
    """Сырые источники из config.yaml — с полями kind/pattern/base."""
    raw = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
    return [s for s in (raw.get("sources") or []) if s.get("url")]


def probe(cfg, items: list[dict]) -> int:
    fetcher = functools.partial(http_fetch, timeout=cfg.fetch_timeout)
    alive = 0
    for item in items:
        name = str(item["name"])
        try:
            text = fetcher(str(item["url"]))
        except Exception as exc:
            print(f"DEAD  {name:16} ошибка: {type(exc).__name__}: {exc}"[:300])
            continue
        if str(item.get("kind", "rss")).lower() == "html":
            orders = parse_html(text, name, str(item.get("pattern", "")), str(item.get("base", "")))
        else:
            orders = parse_feed(text, name)
        if orders:
            alive += 1
            print(
                f"ALIVE {name:16} {len(orders)} записей (получено {len(text)} симв.)\n"
                f"      пример: {orders[0].title[:80]}"
            )
        else:
            head = " ".join((text or "")[:150].split())
            print(f"EMPTY {name:16} 0 записей (получено {len(text)} симв.)\n      начало: {head}")
    print(f"\nРабочих источников: {alive} из {len(items)}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="extra_sources")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--probe", action="store_true", help="проверить источники, не писать в базу")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    items = raw_sources(args.config)
    if not items:
        print("в конфиге нет источников")
        return 1
    if args.probe:
        return probe(cfg, items)

    fetcher = functools.partial(http_fetch, timeout=cfg.fetch_timeout)
    collectors = [make_collector(item, fetcher) for item in items]
    estimator = Estimator(
        client=OpenAICompatibleClient(
            cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model, timeout=cfg.llm_timeout
        ),
        fallback_price=cfg.fallback_price,
        fallback_days=cfg.fallback_days,
    )
    db_path = Path(cfg.db_path)
    if not db_path.is_absolute():
        db_path = HERE / db_path
    storage = Storage(db_path)
    filter_config = FilterConfig(
        accept_keywords=cfg.accept_keywords,
        reject_keywords=cfg.reject_keywords,
        min_score=cfg.min_score,
        min_length=cfg.min_length,
        max_length=cfg.max_length,
    )
    pipeline = Pipeline(collectors, filter_config, estimator, storage, NullNotifier())
    try:
        stats = pipeline.run_once()
    finally:
        storage.close()
    print(json.dumps(stats.as_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
