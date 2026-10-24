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


def vision_describe(image_b64: str, mime: str = "image/png", prompt: str = "",
                    timeout: float = 90.0, client=None):
    """Описание изображения через DeepSeek Vision (reasoning-safe бюджет).

    Бюджет из config: vision.max_tokens (дефолт 3000); если content пуст
    (reasoning съел весь лимит) — один повтор с vision.retry_max_tokens (5000).
    Возвращает (text, meta); text == "" — модель не дала ответа.
    """
    import os
    from config_manager import get as cfg_get

    base = int(cfg_get("vision.max_tokens", 3000) or 3000)
    retry = int(cfg_get("vision.retry_max_tokens", 5000) or 5000)
    q = prompt or "Опиши кратко что видно на этом изображении: объекты, текст, детали."

    if client is None:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=timeout,
            max_retries=0,
        )

    model = str(cfg_get("vision.model", cfg_get("agent.model", "deepseek-flash")))

    def _call(limit: int):
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": q},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{image_b64}", "detail": "auto"}},
            ]}],
            max_tokens=limit,
        )
        msg = resp.choices[0].message
        text = (getattr(msg, "content", "") or "").strip()
        usage = getattr(resp, "usage", None)
        meta = {
            "model": model,
            "limit": limit,
            "finish": getattr(resp.choices[0], "finish_reason", None),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        }
        return text, meta

    text, meta = _call(base)
    if not text:
        text2, meta2 = _call(max(retry, base * 2))
        meta = {"first": meta, "retry": meta2}
        text = text2
    return text, meta
