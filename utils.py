# utils.py — общие утилиты AURA OS

import threading, asyncio
from typing import Any, Callable


def run_async(coro, timeout: float = 15) -> Any:
    """
    Потокобезопасный запуск async-функции из синхронного контекста.
    Используется когда инструмент (sync) вызывает async-код (httpx, API).
    """
    result = []

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result.append(loop.run_until_complete(coro))
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0] if result else None
