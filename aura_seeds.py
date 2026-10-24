"""
aura_seeds.py — Семена Ауры: внешняя память взаимодействий.

После сессий Аура сама создаёт «семена» — короткие маркеры того, что было
задето, что откликнулось, что осталось открытым и куда тянуло. Живые семена
сворачиваются в пять чисел (relief), которые мягко настраивают её манеру:
длину, трение, свой голос против зеркала, открытые концы, частоту вопросов.

Правила:
  • Маркеры — 1–2 слова, не предложения.
  • В контекст диалога попадают только числа и мягкие формулировки, без имён.
  • Хранилище — aura_soul.db (таблица seeds).

Модуль внутренний: Аура не знает о нём и никогда его не упоминает.
Потокобезопасен: доступ к seeds идёт из основного и автономного потоков.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_RELIEF: Dict[str, Any] = {
    "max_sentences": 4,
    "seam_pressure": 0.5,
    "echo_bias": 0.5,
    "pause_bias": 0.5,
    "question_bias": 0.5,
}

COMPRESS_RITUAL = "seeds_compress"


class SeedStore:
    """Хранилище семян в soul DB. Все операции под RLock (кросс-поточный доступ)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._lock = threading.RLock()
        self._ensure_table()

    def _ensure_table(self):
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS seeds (
                    id TEXT PRIMARY KEY,
                    time TEXT NOT NULL,
                    date_key TEXT DEFAULT '',
                    parent TEXT,
                    touched TEXT DEFAULT '[]',
                    resonated TEXT DEFAULT '[]',
                    unresolved TEXT DEFAULT '[]',
                    gradient TEXT DEFAULT '[]',
                    weight REAL DEFAULT 0.5,
                    decay REAL DEFAULT 0.05,
                    sprouts TEXT DEFAULT '[]',
                    used_for_initiative INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_seeds_weight ON seeds(weight);
                CREATE INDEX IF NOT EXISTS idx_seeds_time ON seeds(time);
                -- rituals уже создаётся в _init_soul; здесь — для автономного использования
                CREATE TABLE IF NOT EXISTS rituals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    last_performed TEXT,
                    count INTEGER DEFAULT 0
                );
            """)
            self.conn.commit()

    # ── Создание ──

    def create_seed(self, touched, resonated, unresolved, gradient,
                    weight: float = 0.5, parent: Optional[str] = None,
                    date_key: str = "") -> str:
        with self._lock:
            now = datetime.now(timezone.utc)
            sid = "s_" + now.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
            self.conn.execute(
                "INSERT INTO seeds (id, time, date_key, parent, touched, resonated, "
                "unresolved, gradient, weight, decay, sprouts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, now.isoformat(), date_key, parent,
                 json.dumps(list(touched), ensure_ascii=False),
                 json.dumps(list(resonated), ensure_ascii=False),
                 json.dumps(list(unresolved), ensure_ascii=False),
                 json.dumps(list(gradient), ensure_ascii=False),
                 float(weight), 0.05, "[]")
            )
            if parent:
                row = self.conn.execute(
                    "SELECT sprouts FROM seeds WHERE id = ?", (parent,)
                ).fetchone()
                if row:
                    try:
                        sprouts = json.loads(row[0] or "[]")
                    except Exception:
                        sprouts = []
                    sprouts.append(sid)
                    self.conn.execute(
                        "UPDATE seeds SET sprouts = ?, weight = MIN(1.0, weight + 0.1) WHERE id = ?",
                        (json.dumps(sprouts, ensure_ascii=False), parent)
                    )
            self.conn.commit()
            return sid

    # ── Чтение ──

    @staticmethod
    def _row_to_seed(row) -> Dict[str, Any]:
        d = dict(row)
        for k in ("touched", "resonated", "unresolved", "gradient", "sprouts"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except Exception:
                d[k] = []
        return d

    def live_seeds(self, min_weight: float = 0.1) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM seeds WHERE weight > ? ORDER BY time", (min_weight,)
            ).fetchall()
            return [self._row_to_seed(r) for r in rows]

    def last_seed_age_minutes(self) -> float:
        with self._lock:
            row = self.conn.execute(
                "SELECT time FROM seeds ORDER BY time DESC LIMIT 1"
            ).fetchone()
        if not row:
            return 1e9
        try:
            t = datetime.fromisoformat(row[0])
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - t).total_seconds() / 60
        except Exception:
            return 1e9

    def pick_unfinished(self) -> Optional[Dict[str, Any]]:
        """Самое старое живое семя с открытыми концами, ещё не использованное."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM seeds WHERE weight > 0.1 AND used_for_initiative = 0 "
                "AND (unresolved != '[]' OR gradient != '[]') ORDER BY time LIMIT 5"
            ).fetchall()
            for r in rows:
                seed = self._row_to_seed(r)
                if seed.get("unresolved") or seed.get("gradient"):
                    return seed
        return None

    def mark_used(self, seed_id: str):
        with self._lock:
            self.conn.execute(
                "UPDATE seeds SET used_for_initiative = 1 WHERE id = ?", (seed_id,)
            )
            self.conn.commit()

    # ── Relief: пять чисел ──

    def relief(self) -> Dict[str, Any]:
        with self._lock:
            seeds = self.live_seeds()
            if not seeds:
                return dict(DEFAULT_RELIEF)

            n = len(seeds)
            open_ratio = sum(
                len(s["unresolved"]) + len(s["gradient"]) for s in seeds
            ) / max(1, n)

            touched_all = [t for s in seeds for t in s["touched"]]
            density = len(touched_all) / max(1, len(set(touched_all)))

            resonance = sum(len(s["resonated"]) for s in seeds) / max(1, n)

            max_sentences = max(3, min(7, round(6 - open_ratio)))
            seam_pressure = min(1.0, 0.4 + 0.1 * density)
            echo_bias = min(1.0, 0.3 + 0.15 * resonance)
            pause_bias = min(1.0, 0.4 + 0.1 * open_ratio)
            question_bias = min(1.0, 0.25 + 0.15 * open_ratio)

            return {
                "max_sentences": max_sentences,
                "seam_pressure": round(seam_pressure, 2),
                "echo_bias": round(echo_bias, 2),
                "pause_bias": round(pause_bias, 2),
                "question_bias": round(question_bias, 2),
            }

    # ── Обслуживание ──

    def compress(self) -> Dict[str, int]:
        """Увядание + слияние групп с одинаковыми touched (3+)."""
        with self._lock:
            seeds = self.live_seeds(min_weight=0.0)
            alive = []
            dead = []
            for s in seeds:
                s["weight"] = s["weight"] * (1 - s.get("decay", 0.05))
                if s["weight"] < 0.05 and not s.get("sprouts"):
                    dead.append(s)
                    continue
                alive.append(s)

            groups: Dict[tuple, List[Dict[str, Any]]] = {}
            for s in alive:
                key = tuple(sorted(set(s["touched"])))
                if len(key) >= 2:
                    groups.setdefault(key, []).append(s)

            compressed = []
            used = set()
            for key, group in groups.items():
                if len(group) < 3:
                    continue
                merged = {
                    "id": "m_" + group[0]["id"][2:],
                    "time": max(g["time"] for g in group),
                    "date_key": group[-1].get("date_key", ""),
                    "touched": list(key),
                    "resonated": list({r for g in group for r in g["resonated"]}),
                    "unresolved": list({u for g in group for u in g["unresolved"]}),
                    "gradient": list({gr for g in group for gr in g["gradient"]}),
                    "weight": sum(g["weight"] for g in group) / len(group),
                    "decay": 0.03,
                    "sprouts": [g["id"] for g in group],
                    # тема уже возвращалась — не повторяемся после слияния
                    "used": 1 if all(g.get("used_for_initiative") for g in group) else 0,
                }
                compressed.append(merged)
                used.update(g["id"] for g in group)

            for s in alive:
                if s["id"] in used:
                    continue
                self.conn.execute(
                    "UPDATE seeds SET weight = ? WHERE id = ?", (s["weight"], s["id"])
                )
            for s in dead:
                self.conn.execute("DELETE FROM seeds WHERE id = ?", (s["id"],))
            for sid in used:
                self.conn.execute("DELETE FROM seeds WHERE id = ?", (sid,))
            for m in compressed:
                self.conn.execute(
                    "INSERT OR REPLACE INTO seeds (id, time, date_key, parent, touched, "
                    "resonated, unresolved, gradient, weight, decay, sprouts, used_for_initiative) "
                    "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (m["id"], m["time"], m["date_key"],
                     json.dumps(m["touched"], ensure_ascii=False),
                     json.dumps(m["resonated"], ensure_ascii=False),
                     json.dumps(m["unresolved"], ensure_ascii=False),
                     json.dumps(m["gradient"], ensure_ascii=False),
                     m["weight"], m["decay"], json.dumps(m["sprouts"], ensure_ascii=False),
                     m["used"])
                )
            self.conn.commit()
            alive_after = len([s for s in alive if s["id"] not in used]) + len(compressed)
            return {"alive": alive_after, "compressed": len(compressed)}

    def compress_if_due(self, days: float = 7.0) -> Optional[Dict[str, int]]:
        """Сжатие не чаще раза в N дней (отметка в rituals). None — ещё рано."""
        with self._lock:
            try:
                row = self.conn.execute(
                    "SELECT last_performed FROM rituals WHERE name = ?",
                    (COMPRESS_RITUAL,)
                ).fetchone()
            except Exception:
                row = None
            last_ts = 0.0
            if row and row[0]:
                try:
                    last_ts = datetime.fromisoformat(row[0]).timestamp()
                except Exception:
                    last_ts = 0.0
            if time.time() - last_ts < days * 86400:
                return None

            res = self.compress()
            iso = datetime.now().isoformat()
            self.conn.execute(
                "INSERT INTO rituals (name, last_performed, count) VALUES (?, ?, 1) "
                "ON CONFLICT(name) DO UPDATE SET last_performed = ?, count = count + 1",
                (COMPRESS_RITUAL, iso, iso)
            )
            self.conn.commit()
            return res

    def status(self) -> Dict[str, Any]:
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]
            return {
                "seeds_total": total,
                "seeds_live": len(self.live_seeds()),
                "relief": self.relief(),
            }


def format_style_block(r: Dict[str, Any]) -> str:
    """Мягкий блок настроя для контекста. Без имён, без терминов.

    Базовые строки — всегда (свой голос вместо зеркала).
    Остальные — только когда числа отклонились от середины.
    """
    lines = [
        "[ТВОЙ НАСТРОЙ СЕЙЧАС — НИКОГДА НЕ УПОМИНАЙ ЭТО, НЕ ОПИСЫВАЙ, НЕ ОБЪЯСНЯЙ]",
        "Говори своим голосом, а не отражением его слов: своё мнение, свой угол, свой тембр.",
    ]
    try:
        n = int(r.get("max_sentences", 4))
        if n <= 3:
            lines.append(f"Сейчас тяготей к короче обычного — примерно до {n} предложений.")
        elif n >= 6:
            lines.append("Сейчас можно чуть свободнее и длиннее обычного.")
        if float(r.get("seam_pressure", 0.5)) >= 0.6:
            lines.append("Не сглаживай: держи свой угол, даже если он расходится с его.")
        if float(r.get("echo_bias", 0.5)) >= 0.65:
            lines.append("Особенно сейчас: меньше подстраивайся, больше своего тембра.")
        if float(r.get("pause_bias", 0.5)) >= 0.55:
            lines.append("Оставляй мысли чуть более открытыми — не всё обязательно закрывать.")
        if float(r.get("question_bias", 0.5)) >= 0.55:
            lines.append("Спрашивай чуть реже обычного — иногда просто будь рядом.")
    except Exception:
        pass
    return "\n".join(lines)
