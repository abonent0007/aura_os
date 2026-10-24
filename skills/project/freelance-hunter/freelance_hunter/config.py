import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

ENV_REF = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

DEFAULTS = {
    "accept_keywords": [
        "скрипт",
        "парсер",
        "бот",
        "автоматизация",
        "донастроить",
        "исправить",
        "excel",
        "google sheets",
    ],
    "reject_keywords": ["интеграция", "crm", "мобильное приложение", "срочно", "дизайн", "1с"],
    "min_score": 1,
    "min_length": 30,
    "max_length": 1200,
    "db_path": "orders.db",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_api_key": "",
    "llm_model": "gpt-4o-mini",
    "telegram_token": "",
    "telegram_chat_id": "",
    "fallback_price": 3000,
    "fallback_days": 3,
    "llm_timeout": 15,
    "telegram_timeout": 10,
    "fetch_timeout": 20,
    "max_workers": 6,
}


@dataclass(frozen=True)
class SourceConfig:
    name: str
    url: str
    min_score: Union[int, None] = None  # свой порог скоринга для источника


@dataclass(frozen=True)
class AppConfig:
    sources: tuple[SourceConfig, ...]
    accept_keywords: tuple[str, ...]
    reject_keywords: tuple[str, ...]
    min_score: int
    min_length: int
    max_length: int
    db_path: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    telegram_token: str
    telegram_chat_id: str
    fallback_price: float
    fallback_days: int
    llm_timeout: float
    telegram_timeout: float
    fetch_timeout: float
    max_workers: int


def _load_env_file(path: Path) -> None:
    """Загрузить переменные из .env, не перезаписывая уже установленные."""
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception:
        pass


def _load_global_env() -> None:
    """Глобальные ключи Ауры: .env проекта → .env ядра AURA OS.

    Программа может использовать те же ключи, что и сама Аура
    (DEEPSEEK_API_KEY, TELEGRAM_BOT_TOKEN и др.) — они подхватываются
    из .env ядра, если не заданы локально.
    """
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[1] / ".env",   # skills/project/freelance-hunter/.env
        here.parents[4] / ".env",   # C:\aura_os\.env — ключи ядра Ауры
    ):
        if candidate.exists():
            _load_env_file(candidate)


def _expand_deep(value):
    """Развернуть ${VAR} в строках (рекурсивно по dict/list)."""
    if isinstance(value, str):
        return ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_deep(v) for v in value]
    return value


def load_config(path: Union[str, Path]) -> AppConfig:
    _load_global_env()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config root must be a mapping")
    data = _expand_deep({**DEFAULTS, **raw})
    if not data.get("sources"):
        raise ValueError("config must define at least one source")
    sources = tuple(
        SourceConfig(
            name=str(item["name"]),
            url=str(item["url"]),
            min_score=int(item["min_score"]) if item.get("min_score") is not None else None,
        )
        for item in data["sources"]
    )
    return AppConfig(
        sources=sources,
        accept_keywords=tuple(str(keyword) for keyword in data["accept_keywords"]),
        reject_keywords=tuple(str(keyword) for keyword in data["reject_keywords"]),
        min_score=int(data["min_score"]),
        min_length=int(data["min_length"]),
        max_length=int(data["max_length"]),
        db_path=str(data["db_path"]),
        llm_base_url=str(data["llm_base_url"]),
        llm_api_key=str(data["llm_api_key"]),
        llm_model=str(data["llm_model"]),
        telegram_token=str(data["telegram_token"]),
        telegram_chat_id=str(data["telegram_chat_id"]),
        fallback_price=float(data["fallback_price"]),
        fallback_days=int(data["fallback_days"]),
        llm_timeout=float(data["llm_timeout"]),
        telegram_timeout=float(data["telegram_timeout"]),
        fetch_timeout=float(data["fetch_timeout"]),
        max_workers=int(data["max_workers"]),
    )
