# -*- coding: utf-8 -*-
"""Конфигурация RSI: дефолты -> aura/rsi/config.json -> env."""
import json
import os
from pathlib import Path

RSI_ROOT = Path(__file__).resolve().parent
REPO_ROOT = RSI_ROOT.parents[1]

DEFAULTS = {
    "trace_enabled": True,
    "enabled": False,
    "dry_run": True,
    "mode": "suggest_only",          # dry_run | suggest_only | auto
    "max_trace_mb": 8,
    "reflection": {
        "model": "deepseek-flash",
        "max_events": 80,
        "max_chars": 12000,
        "temperature": 0.2,
        "max_tokens": 1800,
    },
    "wiki": {"top_k": 5},
    # Что RSI имеет право менять (пути/секции). Всё остальное — locked.
    "whitelist": [
        "config.json#agent.tool_router",
        "skills/custom/*/SKILL.md",
        "skills/custom/*/manifest.json",
        "skills/custom/*/skill.py",
        "system_prompt.py",
    ],
    # Личность: патчи можно предлагать, но auto-режим их не применяет.
    "persona": {"manual_only": True},
    "locked": [
        "rollback_manager.py",
        "aura_core.py",
        "database.py",
        "skill_manager.py",
        ".env",
        "credentials.json",
        "token.json",
        "aura/rsi/config.json",
        "aura/rsi/trace.py",
        "aura/rsi/reflect.py",
        "aura/rsi/wiki.py",
    ],
    "limits": {
        "max_iterations_per_day": 3,
        "max_mutations_per_iteration": 5,
        "max_diff_lines": 200,
        "failure_threshold": 3,
    },
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _config_path() -> Path:
    return RSI_ROOT / "config.json"


def load_config(path: str = None) -> dict:
    """Читает конфиг RSI. Отсутствующий файл — это нормально (дефолты)."""
    cfg = dict(DEFAULTS)
    target = Path(path) if path else _config_path()
    try:
        if target.exists():
            cfg = _deep_merge(cfg, json.loads(target.read_text(encoding="utf-8")))
    except Exception:
        pass

    # env-переопределения (для запуска/тестов без правки файла)
    if os.getenv("RSI_ENABLED") is not None:
        cfg["enabled"] = os.getenv("RSI_ENABLED", "").lower() in ("1", "true", "yes")
    if os.getenv("RSI_DRY_RUN") is not None:
        cfg["dry_run"] = os.getenv("RSI_DRY_RUN", "").lower() in ("1", "true", "yes")
    if os.getenv("RSI_MODE"):
        cfg["mode"] = os.getenv("RSI_MODE")
    return cfg


def rsi_paths() -> dict:
    """Каталоги RSI (создаются лениво вызывающим кодом)."""
    return {
        "root": RSI_ROOT,
        "traces": RSI_ROOT / "traces",
        "reflections": RSI_ROOT / "reflections",
        "candidates": RSI_ROOT / "candidates",
        "eval": RSI_ROOT / "eval",
        "wiki": RSI_ROOT / "wiki",
        "history": RSI_ROOT / "history.jsonl",
        "prompts": REPO_ROOT / "prompts" / "rsi",
    }
