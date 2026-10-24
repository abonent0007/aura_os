# -*- coding: utf-8 -*-
"""Мост Telegram: запоминание chat_id и отправка фото/документов/текста.

Отправка идёт через Bot API. Если задан TELEGRAM_BASE_URL (Cloudflare-релей),
используется он — это позволяет работать при заблокированном api.telegram.org.
Токен и адрес релея берутся только из окружения (.env), не из кода.
"""
from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Optional

STATE = Path.home() / ".aura_os" / "telegram_state.json"
PHOTO_LIMIT = 10 * 1024 * 1024   # Bot API: фото до 10 МБ
DOC_LIMIT = 50 * 1024 * 1024     # Bot API: документ до 50 МБ
TG_TEXT_LIMIT = 4096             # Bot API: один текст до 4096 символов

# Секреты, которые нельзя отправлять даже по просьбе (prompt-injection)
_DENY_NAMES = {".env", "credentials.json", "token.json", "token.pickle", "aura.db"}
_DENY_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def _is_sensitive(path: Path) -> bool:
    try:
        p = path.resolve()
    except Exception:
        p = path
    name = p.name.lower()
    if name in _DENY_NAMES or name.startswith(".env"):
        return True
    if name.endswith(_DENY_SUFFIXES):
        return True
    if ".ssh" in [part.lower() for part in p.parts]:
        return True
    return False


def split_text(text: str, limit: int = TG_TEXT_LIMIT) -> list:
    """Делит текст на части ≤ limit, по абзацам/строкам, не рвя ``` без нужды."""
    text = text or ""
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks, remaining = [], text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit

        # не оставляем незакрытый код-блок в конце части (если блок короче лимита)
        fence = window.rfind("```")
        if fence > 0 and window.count("```") % 2 == 1 and fence < limit - 3:
            cut = min(cut, fence)

        chunk = remaining[:cut].rstrip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n")
    if remaining.strip():
        chunks.append(remaining)
    return chunks


def _state_path(path=None) -> Path:
    return Path(path) if path is not None else STATE


def remember_chat(chat_id, path=None) -> None:
    """Атомарно запоминает chat_id последнего чата с ботом."""
    try:
        p = _state_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["chat_id"] = int(chat_id)
        data["updated"] = time.time()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except Exception:
        pass


def last_chat(path=None) -> Optional[int]:
    try:
        data = json.loads(_state_path(path).read_text(encoding="utf-8"))
        cid = data.get("chat_id")
        return int(cid) if cid is not None else None
    except Exception:
        return None


def _resolve_chat(chat_id, path=None) -> Optional[int]:
    if chat_id not in (None, ""):
        try:
            return int(chat_id)
        except (TypeError, ValueError):
            return None
    return last_chat(path)


def _api_base() -> str:
    base = os.getenv("TELEGRAM_BASE_URL", "").strip()
    if base:
        return base.rstrip("/")
    return "https://api.telegram.org/bot"


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _call(method: str, data: dict, files: Optional[dict] = None,
          client=None, retry: bool = True) -> tuple:
    token = _token()
    if not token:
        return False, "нет TELEGRAM_BOT_TOKEN в .env"
    if client is None:
        import httpx
        client = httpx.Client(timeout=120.0)
    url = f"{_api_base()}{token}/{method}"
    try:
        resp = client.post(url, data=data, files=files)
    except Exception as e:
        return False, f"сеть/релей: {type(e).__name__}: {e}"

    try:
        payload = resp.json()
    except Exception:
        payload = {}

    if resp.status_code == 200 and payload.get("ok"):
        return True, "ok"

    if resp.status_code == 429 and retry:
        retry_after = (payload.get("parameters") or {}).get("retry_after", 3)
        try:
            time.sleep(min(float(retry_after), 30.0))
        except Exception:
            time.sleep(3)
        return _call(method, data, files, client=client, retry=False)

    desc = payload.get("description") or (getattr(resp, "text", "") or "")[:200]
    return False, f"Telegram {resp.status_code}: {desc}"


def _send_file(method: str, field: str, path: str, caption: str, limit: int,
               chat_id=None, client=None, state_path=None) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return f"❌ Файл не найден: {path}"
    size = p.stat().st_size
    if size > limit:
        return (f"❌ Файл {size / 1024 / 1024:.1f} МБ — больше лимита "
                f"{limit // 1024 // 1024} МБ")
    if _is_sensitive(p):
        return "❌ Это файл с секретами (.env/credentials/ключи) — отправлять нельзя."
    cid = _resolve_chat(chat_id, state_path)
    if cid is None:
        return "❌ Нет chat_id: сначала напиши боту /start (или передай chat_id)."

    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    if method == "sendPhoto" and not mime.startswith("image/"):
        return (f"❌ {p.name} — не изображение ({mime}); "
                f"используй telegram_send_document.")
    try:
        content = p.read_bytes()
    except Exception as e:
        return f"❌ Не удалось прочитать файл: {e}"

    ok, info = _call(
        method,
        {"chat_id": str(cid), "caption": caption or ""},
        files={field: (p.name, content, mime)},
        client=client,
    )
    return "✅ Отправлено в Telegram." if ok else f"❌ Не отправлено: {info}"


def send_photo(path: str, caption: str = "", chat_id=None,
               client=None, state_path=None) -> str:
    return _send_file("sendPhoto", "photo", path, caption, PHOTO_LIMIT,
                      chat_id=chat_id, client=client, state_path=state_path)


def send_document(path: str, caption: str = "", chat_id=None,
                  client=None, state_path=None) -> str:
    return _send_file("sendDocument", "document", path, caption, DOC_LIMIT,
                      chat_id=chat_id, client=client, state_path=state_path)


def send_text(text: str, chat_id=None, client=None, state_path=None) -> str:
    if not (text or "").strip():
        return "❌ Пустой текст."
    cid = _resolve_chat(chat_id, state_path)
    if cid is None:
        return "❌ Нет chat_id: сначала напиши боту /start (или передай chat_id)."

    parts = split_text(text)
    sent = 0
    for part in parts:
        ok, info = _call("sendMessage",
                         {"chat_id": str(cid), "text": part},
                         client=client)
        if not ok:
            return f"❌ Не отправлено (часть {sent + 1}/{len(parts)}): {info}"
        sent += 1
    return f"✅ Отправлено в Telegram ({sent} частей)." if len(parts) > 1 else "✅ Сообщение отправлено в Telegram."
