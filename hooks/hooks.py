"""
AURA OS — Lifecycle Hooks
Загружает и выполняет хуки жизненного цикла: on_session_start, on_before_tool, on_after_tool, on_session_end.
Хуки — Python-скрипты из hooks/hooks.json, запускаются в изолированном контексте.
"""

import importlib.util, json, os, sys
from pathlib import Path
from typing import Any, Callable

HOOKS_DIR = Path(__file__).parent
CONFIG_PATH = HOOKS_DIR / "hooks.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"hooks": {"session_start": [], "before_tool": [], "after_tool": [], "session_end": []}}


def _load_hook_script(name: str) -> Callable | None:
    """Загружает Python-скрипт хука и возвращает функцию run()."""
    path = HOOKS_DIR / name
    if not path.exists():
        print(f"[hooks] Файл не найден: {path}")
        return None

    try:
        spec = importlib.util.spec_from_file_location(f"hook_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "run"):
            return mod.run
        print(f"[hooks] В {name} нет функции run()")
        return None
    except Exception as e:
        print(f"[hooks] Ошибка загрузки {name}: {e}")
        return None


def run_hooks(event: str, **kwargs) -> list[str]:
    """Запускает все хуки для указанного события."""
    config = _load_config()
    scripts = config.get("hooks", {}).get(event, [])
    results = []

    for script_name in scripts:
        fn = _load_hook_script(script_name)
        if fn:
            try:
                result = fn(**kwargs)
                results.append(f"[{script_name}] {result}")
            except Exception as e:
                results.append(f"[{script_name}] Ошибка: {e}")

    return results


def run_session_start() -> list[str]:
    return run_hooks("session_start")


def run_before_tool(tool_name: str, args: Any = None) -> list[str]:
    return run_hooks("before_tool", tool_name=tool_name, args=args)


def run_after_tool(tool_name: str, result: Any = None) -> list[str]:
    return run_hooks("after_tool", tool_name=tool_name, result=result)


def run_session_end() -> list[str]:
    return run_hooks("session_end")
