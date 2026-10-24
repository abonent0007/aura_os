"""extra_sources.py — расширенный поиск заказов для freelance-hunter.

Дополняет ядро программы (которое умеет только RSS):
  * тянет все источники из config.yaml, включая kind: html (kwork, youdo)
  * браузерный User-Agent — часть досок отдаёт 403 «боту»
  * свой конвейер: фильтр → оценка DeepSeek → orders.db (та же схема)
  * ветки: прогон берёт только ту, что указана в ключе branch (сейчас gigs —
    разовые заказы с оплатой физлицу). Источники чужой ветки пропускаются,
    а старые записи найма размечаются веткой jobs и в gigs-выдачу не лезут.

Запуск:
    python extra_sources.py --config config.yaml
    python extra_sources.py --config config.yaml --probe
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ATOM_NS = "http://www.w3.org/2005/Atom"
ENV_REF = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
WORD_CHARS = r"[A-Za-zА-Яа-яЁё0-9]"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT 'gigs',
    score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    price REAL,
    days INTEGER,
    proposal TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
)
"""

PROMPT = (
    "Оцени фриланс-заказ и предложи короткий отклик от первого лица, физлица "
    "(без ИП, безнала и закрывающих документов), до 400 знаков. "
    'Ответь строго JSON без пояснений: {{"price": число, "days": число, "proposal": строка}}.\n'
    "Заказ: {title}\nОписание: {description}"
)

DEFAULTS = {
    "accept_keywords": ["скрипт", "парсер", "бот", "автоматизация", "python"],
    "reject_keywords": ["дизайн", "1с"],
    "min_score": 2,
    "min_length": 30,
    "max_length": 1200,
    "db_path": "orders.db",
    "branch": "gigs",
    "llm_base_url": "https://api.deepseek.com/v1",
    "llm_api_key": "",
    "llm_model": "deepseek-flash",
    "llm_timeout": 30,
    "fallback_price": 3000,
    "fallback_days": 3,
    "fetch_timeout": 20,
    "estimate_limit": 30,
    "max_workers": 6,
}

# Источники найма: в конфиге выключены (нужны заказы, а не работа), но их записи
# в базе уже есть — по этому списку размечаем старые заказы веткой jobs.
LEGACY_JOB_SOURCES = (
    "hh.ru",
    "habr-career",
    "career.habr",
    "geekjob",
    "weworkremotely",
    "remoteok",
)


# ------------------------------------------------------------------- ветки

def ensure_schema(conn) -> None:
    """Таблица orders + миграция: колонка branch появилась позже базовых полей."""
    conn.execute(SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
    if "branch" not in columns:
        conn.execute("ALTER TABLE orders ADD COLUMN branch TEXT NOT NULL DEFAULT 'gigs'")


def source_branches(path: str) -> dict:
    """source → branch из config.yaml."""
    return {
        str(item["name"]): str(item.get("branch", "gigs")).lower()
        for item in raw_sources(path)
    }


def build_branch_map(path: str) -> dict:
    """Ветки для разметки базы: сначала выключенный найм, потом явные из конфига."""
    mapping = {name: "jobs" for name in LEGACY_JOB_SOURCES}
    mapping.update(source_branches(path))
    return mapping


def backfill_branches(db_path: Path, mapping: dict) -> int:
    """Проставить ветку уже сохранённым заказам. Возвращает число правок."""
    if not Path(db_path).exists():
        return 0
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ensure_schema(conn)
        changed = 0
        for source, branch in mapping.items():
            cursor = conn.execute(
                "UPDATE orders SET branch = ? WHERE branch != ? AND source LIKE ?",
                (branch, branch, f"{source}%"),
            )
            changed += cursor.rowcount
        conn.commit()
        return changed
    finally:
        conn.close()


# ---------------------------------------------------------------- источники

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


def parse_feed(xml_text: str, source: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    orders: list[dict] = []
    items = root.findall(".//item")
    if items:
        for item in items:
            title = strip_html(_text(item, "title"))
            link = _text(item, "link")
            external_id = _text(item, "guid") or link
            if not title or not external_id:
                continue
            orders.append(
                {
                    "source": source,
                    "external_id": external_id,
                    "title": title,
                    "description": strip_html(_text(item, "description")),
                    "url": link,
                }
            )
        return orders
    for entry in root.findall(f".//{{{ATOM_NS}}}entry"):
        title = strip_html(_text(entry, "title", ATOM_NS))
        link_element = entry.find(f"{{{ATOM_NS}}}link")
        url = link_element.get("href", "") if link_element is not None else ""
        external_id = _text(entry, "id", ATOM_NS) or url
        if not title or not external_id:
            continue
        description = _text(entry, "summary", ATOM_NS) or _text(entry, "content", ATOM_NS)
        orders.append(
            {
                "source": source,
                "external_id": external_id,
                "title": title,
                "description": strip_html(description),
                "url": url,
            }
        )
    return orders


def parse_html(text: str, source: str, pattern: str, base: str = "") -> list[dict]:
    """Карточки заказов из HTML по regex с именованными группами url/title/desc."""
    if not text or not pattern:
        return []
    orders: list[dict] = []
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
            {
                "source": source,
                "external_id": url,
                "title": title,
                "description": strip_html(groups.get("desc") or ""),
                "url": url,
            }
        )
    return orders


def fetch(url: str, timeout: float = 20.0) -> str:
    import httpx

    response = httpx.get(
        url,
        timeout=httpx.Timeout(timeout, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": BROWSER_UA, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"},
    )
    response.raise_for_status()
    return response.text


def collect(item: dict, timeout: float) -> list[dict]:
    text = fetch(str(item["url"]), timeout)
    if str(item.get("kind", "rss")).lower() == "html":
        orders = parse_html(text, str(item["name"]), str(item.get("pattern", "")), str(item.get("base", "")))
    else:
        orders = parse_feed(text, str(item["name"]))
    branch = str(item.get("branch", "gigs")).lower()
    for order in orders:
        order["branch"] = branch
    return orders


# ------------------------------------------------------------------ фильтры

def _word_match(text: str, keyword: str) -> bool:
    """Совпадение с начала слова (русские словоформы: «дизайн» → «дизайнера»)."""
    pattern = rf"(?<!{WORD_CHARS}){re.escape(keyword.lower())}"
    return re.search(pattern, text) is not None


def evaluate(order: dict, cfg: dict, min_score: int | None = None) -> tuple[bool, int]:
    text = f"{order['title']} {order['description']}".lower()
    for keyword in cfg["reject_keywords"]:
        if _word_match(text, str(keyword)):
            return False, 0
    score = sum(1 for keyword in cfg["accept_keywords"] if str(keyword).lower() in text)
    if not (cfg["min_length"] <= len(text) <= cfg["max_length"]):
        return False, score
    threshold = cfg["min_score"] if min_score is None else min_score
    return score >= threshold, score


# --------------------------------------------------------------------- LLM

def estimate(order: dict, cfg: dict) -> tuple[float, int, str, bool]:
    prompt = PROMPT.format(title=order["title"], description=order["description"])
    raw = ""
    try:
        import httpx

        response = httpx.post(
            f"{str(cfg['llm_base_url']).rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['llm_api_key']}"},
            json={
                "model": cfg["llm_model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=httpx.Timeout(float(cfg["llm_timeout"]), connect=5.0),
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
    except Exception:
        raw = ""
    data = _extract_json(raw)
    price = _as_number(data.get("price")) if isinstance(data, dict) else None
    days = _as_number(data.get("days")) if isinstance(data, dict) else None
    proposal = data.get("proposal") if isinstance(data, dict) else None
    proposal = proposal.strip() if isinstance(proposal, str) else ""
    if price is None or days is None or not proposal:
        return (
            float(cfg["fallback_price"]),
            int(cfg["fallback_days"]),
            proposal
            or (
                f"Здравствуйте! Готов взяться за «{order['title']}» и сдать в срок. "
                "Уточню пару деталей и сразу приступлю."
            ),
            True,
        )
    return float(price), int(days), proposal, False


def _extract_json(raw: str):
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _as_number(value):
    try:
        if isinstance(value, str):
            value = re.sub(r"[^\d.]", "", value)
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------- конфиг

def load_config(path: str) -> dict:
    import yaml

    _load_env_files()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data = {**DEFAULTS, **raw}
    for key in ("llm_base_url", "llm_api_key", "llm_model", "db_path"):
        if isinstance(data.get(key), str):
            data[key] = ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), data[key])
    data["sources"] = [s for s in (raw.get("sources") or []) if s.get("url")]
    return data


def _load_env_files() -> None:
    for candidate in (
        HERE / ".env",
        HERE.parent / ".env",
        HERE.parents[1] / ".env",
        Path("C:/aura_os/.env"),
    ):
        try:
            for line in candidate.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        except Exception:
            continue


def raw_sources(path: str) -> list[dict]:
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [s for s in (raw.get("sources") or []) if s.get("url")]


# --------------------------------------------------------------------- база

def existing_keys(path: Path) -> set:
    """Все (source, external_id) из базы — чтобы не тратить токены на дубли."""
    try:
        conn = sqlite3.connect(str(path), timeout=10)
        try:
            ensure_schema(conn)
            return {(r[0], r[1]) for r in conn.execute("SELECT source, external_id FROM orders")}
        finally:
            conn.close()
    except Exception:
        return set()


def store(path: Path, order: dict, score: int, est: tuple[float, int, str, bool]) -> bool:
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        ensure_schema(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO orders
            (source, external_id, title, url, description, branch, score, status, price, days, proposal, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)
            """,
            (
                order["source"],
                order["external_id"],
                order["title"],
                order["url"],
                order["description"],
                order.get("branch", "gigs"),
                score,
                est[0],
                est[1],
                est[2],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# --------------------------------------------------------------------- main

def probe(items: list[dict], cfg: dict) -> int:
    def reject_reason(order: dict) -> str:
        """Какой запретный ключ срезал заказ — чтобы видеть, чем режет фильтр."""
        text = f"{order['title']} {order['description']}".lower()
        for keyword in cfg["reject_keywords"]:
            if _word_match(text, str(keyword)):
                return str(keyword)
        return ""

    alive = 0
    alive_branches: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for item in items:
        name = str(item["name"])
        branch = str(item.get("branch", "gigs")).lower()
        tag = f"{name} [{branch}]"
        try:
            text = fetch(str(item["url"]), float(cfg["fetch_timeout"]))
        except Exception as exc:
            print(f"DEAD  {tag:24} {type(exc).__name__}: {exc}"[:200])
            continue
        orders = (
            parse_html(text, name, str(item.get("pattern", "")), str(item.get("base", "")))
            if str(item.get("kind", "rss")).lower() == "html"
            else parse_feed(text, name)
        )
        for order in orders:
            order["branch"] = branch
        if orders:
            alive += 1
            alive_branches[branch] = alive_branches.get(branch, 0) + 1
            source_min = item.get("min_score")
            source_min = int(source_min) if source_min is not None else None
            keep = 0
            for order in orders:
                if evaluate(order, cfg, source_min)[0]:
                    keep += 1
                    continue
                reason = reject_reason(order)
                if reason:
                    reasons[reason] = reasons.get(reason, 0) + 1
            print(
                f"ALIVE {tag:24} {len(orders)} записей, прошло фильтр {keep} ({len(text)} симв.)\n"
                f"      пример: {orders[0]['title'][:80]}"
            )
        else:
            head = " ".join((text or "")[:120].split())
            print(f"EMPTY {tag:24} 0 записей ({len(text)} симв.)\n      начало: {head}")
    summary = ", ".join(f"{name}: {count}" for name, count in sorted(alive_branches.items()))
    tail = f" (по веткам {summary})" if summary else ""
    print(f"\nРабочих источников: {alive} из {len(items)}{tail}")
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:8]
        print("Режет чаще всего: " + ", ".join(f"{key} ({count})" for key, count in top))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="extra_sources")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    items = raw_sources(args.config)
    if not items:
        print(json.dumps({"error": "в конфиге нет источников"}, ensure_ascii=False))
        return 1
    if args.probe:
        return probe(items, cfg)

    db_path = Path(str(cfg["db_path"]))
    if not db_path.is_absolute():
        db_path = HERE / db_path

    active_branch = str(cfg.get("branch", "gigs")).lower()
    marked = backfill_branches(db_path, build_branch_map(args.config))

    stats = {
        "fetched": 0, "accepted": 0, "stored": 0,
        "duplicates": 0, "fallbacks": 0, "errors": 0,
        "branch": active_branch, "marked_branch": marked,
    }
    per_source: dict[str, int] = {}
    other_branch: list[str] = []
    print(f"Ветка: {active_branch}. Источников в конфиге: {len(items)}")

    # Фаза 1: собрать и отфильтровать (без LLM)
    candidates: list[tuple[dict, int, str]] = []
    for item in items:
        name = str(item["name"])
        item_branch = str(item.get("branch", "gigs")).lower()
        if item_branch != active_branch:
            other_branch.append(f"{name} [{item_branch}]")
            continue
        try:
            orders = collect(item, float(cfg["fetch_timeout"]))
        except Exception as exc:
            stats["errors"] += 1
            print(f"  ── {name:16} ошибка: {type(exc).__name__}: {exc}"[:160])
            continue
        per_source[name] = len(orders)
        stats["fetched"] += len(orders)
        source_min = item.get("min_score")
        source_min = int(source_min) if source_min is not None else None
        keep = 0
        for order in orders:
            accepted, score = evaluate(order, cfg, source_min)
            if not accepted:
                continue
            stats["accepted"] += 1
            candidates.append((order, score, name))
            keep += 1
        print(f"  ── {name:16} лента {len(orders):4} · подошло {keep}")

    if other_branch:
        stats["skipped_sources"] = other_branch
        print("  ── пропущено (другая ветка): " + ", ".join(other_branch))

    # Отсеять уже известное — на дубли токены не тратим
    known = existing_keys(db_path)
    fresh = []
    for order, score, name in candidates:
        if (order["source"], order["external_id"]) in known:
            stats["duplicates"] += 1
            continue
        fresh.append((order, score, name))

    # Фаза 2: оценка — параллельно (LLM-вызовы независимы)
    limit = int(cfg.get("estimate_limit", 30) or 30)
    to_estimate = fresh[:limit]
    skipped = len(fresh) - len(to_estimate)

    def _estimate(pair):
        order, score, name = pair
        try:
            return order, score, estimate(order, cfg)
        except Exception:
            return order, score, None

    workers = max(1, min(int(cfg.get("max_workers", 6) or 6), len(to_estimate) or 1))
    if to_estimate:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            estimated = list(pool.map(_estimate, to_estimate))
    else:
        estimated = []

    # Фаза 3: сохранить
    for order, score, est in estimated:
        if est is None:
            stats["errors"] += 1
            continue
        if est[3]:
            stats["fallbacks"] += 1
        try:
            if store(db_path, order, score, est):
                stats["stored"] += 1
            else:
                stats["duplicates"] += 1
        except Exception as exc:
            stats["errors"] += 1
            print(f"  ── база: {type(exc).__name__}: {exc}"[:160])

    if skipped:
        print(f"  ── лимит оценок {limit}: ещё {skipped} отложено до следующего прогона")
    stats["per_source"] = per_source
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
