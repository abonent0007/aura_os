"""config_manager.py — кэшируемый доступ к config.json с автообновлением.

Перечитывает файл только при изменении mtime (кэш на процесс), ошибки
парсинга не ломают работу — остаётся последняя валидная копия. Веб-API
PUT /api/config пишет config.json, поэтому кэш подхватывает изменения
при следующем чтении без перезапуска приложения.

Использование:
    from config_manager import get as cfg_get
    value = cfg_get("autonomy.max_shots", 5)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

_PATH = Path(__file__).resolve().parent / "config.json"
_lock = threading.RLock()
_cache: dict = {}
_stamp: Optional[float] = None


def _load(force: bool = False) -> dict:
    global _cache, _stamp
    with _lock:
        try:
            mt = _PATH.stat().st_mtime
        except OSError:
            return _cache
        if not force and mt == _stamp and _cache:
            return _cache
        try:
            data = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _cache  # держим последнюю валидную версию
        if isinstance(data, dict):
            _cache = data
            _stamp = mt
        return _cache


def get(path: str, default: Any = None) -> Any:
    """Значение по точечному пути ('autonomy.max_shots') или default."""
    node: Any = _load()
    for part in (path or "").split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def get_all() -> dict:
    """Копия всего конфига (для диагностики/секций)."""
    return dict(_load())


def reload() -> dict:
    """Принудительное перечитывание (после внешней правки файла)."""
    return dict(_load(force=True))
