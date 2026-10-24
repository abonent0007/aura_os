# -*- coding: utf-8 -*-
"""Журнал общего чата: один диалог для всех окон Ауры.

Каждое сообщение получает id (для дедупликации при reconnect и повторной
отправке), роль, текст, client_id (кто инициировал) и время.
"""
from collections import deque
from typing import Optional
import time
import uuid


class ChatJournal:
    def __init__(self, maxlen: int = 200):
        self._events = deque(maxlen=maxlen)

    def add(self, role: str, text: str, client_id: str = "") -> dict:
        event = {
            "id": uuid.uuid4().hex,
            "role": role,
            "text": text or "",
            "client_id": client_id or "",
            "ts": time.time(),
        }
        self._events.append(event)
        return event

    def history(self, limit: int = 40, after: Optional[str] = None) -> list:
        events = list(self._events)
        if after:
            idx = next((i for i, e in enumerate(events) if e["id"] == after), None)
            if idx is not None:
                events = events[idx + 1:]
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = 40
        return events[-max(1, min(n, 200)):]

    def clear(self):
        self._events.clear()
