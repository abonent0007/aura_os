# -*- coding: utf-8 -*-
"""M1: Trace Logger — JSONL-трейсы сессий.

Формат записи: {"ts","event_id","kind","payload"}.
Пишем только локально; каталог исключён из git (личные данные).
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from .config import load_config, rsi_paths

KINDS = {
    "task", "plan", "tool_call", "tool_result", "error",
    "user_feedback", "final_outcome", "reflection",
}


class TraceLogger:
    def __init__(self, root: str = None, max_mb: float = None):
        cfg = load_config()
        self.root = Path(root) if root else rsi_paths()["traces"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = int((max_mb if max_mb is not None else cfg.get("max_trace_mb", 8)) * 1024 * 1024)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_")[:64]
        return self.root / f"{safe or 'default'}.jsonl"

    def _rotate(self, path: Path) -> None:
        try:
            if path.exists() and path.stat().st_size >= self.max_bytes:
                old = path.with_suffix(".1.jsonl")
                if old.exists():
                    old.unlink()
                path.replace(old)
        except Exception:
            pass

    def log(self, session_id: str, kind: str, payload: dict = None,
            event_id: str = None) -> str:
        """Добавляет событие, возвращает event_id."""
        kind = kind if kind in KINDS else "task"
        eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event_id": eid,
            "kind": kind,
            "payload": payload or {},
        }
        path = self._path(session_id)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._rotate(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return eid

    # удобные обёртки
    def task(self, session_id, text, **extra):
        return self.log(session_id, "task", {"text": (text or "")[:2000], **extra})

    def tool_call(self, session_id, name, args=None, **extra):
        return self.log(session_id, "tool_call",
                        {"name": name, "args": str(args)[:1000] if args else "", **extra})

    def tool_result(self, session_id, name, result, success=True, latency_ms=None):
        return self.log(session_id, "tool_result",
                        {"name": name, "result": str(result)[:2000],
                         "success": bool(success), "latency_ms": latency_ms})

    def error(self, session_id, message, where=""):
        return self.log(session_id, "error",
                        {"message": str(message)[:1000], "where": where})

    def final_outcome(self, session_id, text, **extra):
        return self.log(session_id, "final_outcome",
                        {"text": str(text)[:2000], **extra})

    def user_feedback(self, session_id, value, note=""):
        return self.log(session_id, "user_feedback",
                        {"value": value, "note": str(note)[:500]})

    def read(self, session_id: str, limit: int = None) -> list:
        """Читает трейс, пропуская битые строки."""
        path = self._path(session_id)
        if not path.exists():
            return []
        out = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out[-limit:] if limit else out

    def digest(self, session_id: str, max_events: int = 80,
               max_chars: int = 12000) -> list:
        """Компактные записи для рефлексии: event_id + kind + короткий payload."""
        rows = self.read(session_id)[-max_events:]
        out, total = [], 0
        for row in rows:
            payload = json.dumps(row.get("payload", {}), ensure_ascii=False)
            item = {
                "event_id": row.get("event_id"),
                "ts": row.get("ts"),
                "kind": row.get("kind"),
                "payload": payload[:400],
            }
            size = len(json.dumps(item, ensure_ascii=False))
            if total + size > max_chars:
                break
            out.append(item)
            total += size
        return out

    def sessions(self) -> list:
        return sorted(p.stem for p in self.root.glob("*.jsonl"))
