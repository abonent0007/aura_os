# database.py
# AURA OS — Database layer (extracted from aura_core.py)
import sqlite3, re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional


class EventCategory:
    BIRTHDAY = "drr"   # День рождения
    TASK = "zad"       # Задача
    REMINDER = "nap"   # Напоминание
    EVENT = "evt"      # Событие (встреча, созвон, мероприятие)
    PLAN = "pln"       # План (поездка, дело, проект)
    HEALTH = "med"     # Здоровье (врач, спорт, процедуры)

    @classmethod
    def get_emoji(cls, category: str) -> str:
        return {"drr": "🎂", "zad": "📋", "nap": "🔔",
                "evt": "📅", "pln": "📌", "med": "🏥"}.get(category, "📌")

    @classmethod
    def get_name(cls, category: str) -> str:
        return {"drr": "День рождения", "zad": "Задача", "nap": "Напоминание",
                "evt": "Событие", "pln": "План", "med": "Здоровье"}.get(category, "Событие")


class MemoryTriggerSystem:
    def __init__(self, config: dict):
        cfg = config.get("memory", {}).get("memory_search", {})
        self.enabled = cfg.get("auto_search_enabled", True)
        self.max_results = cfg.get("max_results", 5)

        self.past_triggers = cfg.get("triggers_past", [])
        self.context_triggers = cfg.get("triggers_context", [])

        if self.past_triggers:
            self.past_pattern = re.compile(
                '|'.join(re.escape(t) for t in self.past_triggers),
                re.IGNORECASE
            )
        else:
            self.past_pattern = None

        if self.context_triggers:
            self.context_pattern = re.compile(
                '|'.join(re.escape(t) for t in self.context_triggers),
                re.IGNORECASE
            )
        else:
            self.context_pattern = None

    def analyze_query(self, text: str) -> dict:
        if not self.enabled:
            return {"should_search": False}

        result = {
            "should_search": False,
            "search_type": None,
            "matched_triggers": [],
            "search_terms": []
        }

        past_matches = []
        if self.past_pattern:
            past_matches = self.past_pattern.findall(text.lower())
        if past_matches:
            result["should_search"] = True
            result["search_type"] = "past"
            result["matched_triggers"] = list(set(past_matches))

        context_matches = []
        if self.context_pattern:
            context_matches = self.context_pattern.findall(text.lower())
        if context_matches:
            result["should_search"] = True
            if not result["search_type"]:
                result["search_type"] = "context"
            result["matched_triggers"].extend(list(set(context_matches)))

        words = re.findall(r'\b[а-яёa-z]{4,}\b', text.lower())
        stop_words = {
            'напомни', 'вспомни', 'помнишь', 'найди', 'поищи',
            'делали', 'сделали', 'вели', 'обсуждали', 'говорили',
            'расскажи', 'подробнее', 'пожалуйста', 'можешь',
            'который', 'когда', 'где', 'зачем', 'почему',
            'контекст', 'история', 'детали', 'подробности'
        }
        result["search_terms"] = [w for w in words if w not in stop_words]

        return result

    def extract_search_query(self, text: str, trigger_result: dict) -> str:
        terms = trigger_result.get("search_terms", [])
        clean_text = text
        for trigger in trigger_result.get("matched_triggers", []):
            clean_text = re.sub(re.escape(trigger), '', clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.strip().strip(',.!?;:').strip()

        if terms:
            return ' '.join(terms[:5])
        if len(clean_text) > 3:
            return clean_text[:200]
        return text


class AuraDatabase:
    CURRENT_SCHEMA = 1

    def __init__(self, config: dict, db_path: str = None):
        self.config = config
        if db_path is None:
            db_path = config["memory"]["db_path"]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._migrate_schema()
        self._init_tables()

    def _migrate_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
        row = self.conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        current = row["v"] if row and row["v"] else 0

        if current < self.CURRENT_SCHEMA:
            print(f"[db] Schema migration: v{current} → v{self.CURRENT_SCHEMA}")
            now = datetime.now().isoformat()
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                (self.CURRENT_SCHEMA, now)
            )
            self.conn.commit()
            print(f"[db] Migration complete: v{self.CURRENT_SCHEMA}")

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_key DATE NOT NULL,
                session_id TEXT,
                summary TEXT NOT NULL,
                key_topics TEXT,
                key_decisions TEXT,
                key_facts TEXT,
                full_compressed_text TEXT,
                message_count INTEGER DEFAULT 0,
                importance_score REAL DEFAULT 0.5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_memory_date ON conversation_memory(date_key);
            CREATE INDEX IF NOT EXISTS idx_memory_topics ON conversation_memory(key_topics);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_date_session 
                ON conversation_memory(date_key, session_id);

            CREATE TABLE IF NOT EXISTS calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT NOT NULL DEFAULT 'nap',
                event_date DATE NOT NULL,
                event_time TIME,
                end_date DATE,
                recurring_rule TEXT,
                remind_before_days INTEGER DEFAULT 1,
                is_completed BOOLEAN DEFAULT 0,
                completed_at TIMESTAMP,
                last_reminded_at TIMESTAMP,
                remind_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_events_date ON calendar_events(event_date);
            CREATE INDEX IF NOT EXISTS idx_events_category ON calendar_events(category);
            CREATE INDEX IF NOT EXISTS idx_events_completed ON calendar_events(is_completed);

            CREATE TABLE IF NOT EXISTS quick_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL,
                source TEXT,
                confidence REAL DEFAULT 0.5,
                last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS birthdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT NOT NULL,
                birth_date DATE NOT NULL,
                year INTEGER,
                relation TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_birthdays_person 
                ON birthdays(person_name, birth_date);

            CREATE TABLE IF NOT EXISTS trace_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_type TEXT NOT NULL,
                tool_name TEXT,
                tool_args TEXT,
                tool_result TEXT,
                thought TEXT,
                latency_ms INTEGER,
                success BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_trace_session ON trace_steps(session_id);

            CREATE TABLE IF NOT EXISTS memory_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL REFERENCES conversation_memory(id),
                tag TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_memory_tags_memory ON memory_tags(memory_id);

            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER NOT NULL UNIQUE REFERENCES conversation_memory(id),
                embedding TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                summary,
                key_topics,
                key_decisions,
                key_facts,
                full_compressed_text,
                content='conversation_memory',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON conversation_memory BEGIN
                INSERT INTO memory_fts(rowid, summary, key_topics, key_decisions, key_facts, full_compressed_text)
                VALUES (new.id, new.summary, new.key_topics, new.key_decisions, new.key_facts, new.full_compressed_text);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON conversation_memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, summary, key_topics, key_decisions, key_facts, full_compressed_text)
                VALUES ('delete', old.id, old.summary, old.key_topics, old.key_decisions, old.key_facts, old.full_compressed_text);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON conversation_memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, summary, key_topics, key_decisions, key_facts, full_compressed_text)
                VALUES ('delete', old.id, old.summary, old.key_topics, old.key_decisions, old.key_facts, old.full_compressed_text);
                INSERT INTO memory_fts(rowid, summary, key_topics, key_decisions, key_facts, full_compressed_text)
                VALUES (new.id, new.summary, new.key_topics, new.key_decisions, new.key_facts, new.full_compressed_text);
            END;
        """)
        self.conn.commit()

    def save_daily_summary(self, date_key, summary, session_id=None, key_topics=None,
                           key_decisions=None, key_facts=None, full_text=None, message_count=0):
        if session_id is None:
            session_id = "main"
        existing = self.conn.execute(
            "SELECT id FROM conversation_memory WHERE date_key = ? AND session_id = ?",
            (date_key, session_id)
        ).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE conversation_memory 
                   SET summary=?, key_topics=?, key_decisions=?, key_facts=?,
                       full_compressed_text=?, message_count=?, updated_at=?
                   WHERE id=?""",
                (summary, key_topics, key_decisions, key_facts, full_text,
                 message_count, datetime.now().isoformat(), existing["id"])
            )
            self.conn.commit()
            return existing["id"]
        else:
            cursor = self.conn.execute(
                """INSERT INTO conversation_memory 
                   (date_key, session_id, summary, key_topics, key_decisions, 
                    key_facts, full_compressed_text, message_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (date_key, session_id, summary, key_topics, key_decisions,
                 key_facts, full_text, message_count)
            )
            self.conn.commit()
            return cursor.lastrowid

    def get_today_summary(self, date_key=None):
        if date_key is None:
            date_key = date.today().isoformat()
        row = self.conn.execute(
            "SELECT * FROM conversation_memory WHERE date_key = ? ORDER BY updated_at DESC LIMIT 1",
            (date_key,)
        ).fetchone()
        return dict(row) if row else None

    def search_memory_fts(self, query, limit=5):
        try:
            cursor = self.conn.execute(
                """SELECT cm.*, snippet(memory_fts, 0, '<mark>', '</mark>', '...', 40) as snippet
                   FROM memory_fts JOIN conversation_memory cm ON memory_fts.rowid = cm.id
                   WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?""",
                (query, limit)
            )
            results = [dict(row) for row in cursor.fetchall()]
            if results:
                return results
        except Exception:
            pass
        like_query = f"%{query}%"
        cursor = self.conn.execute(
            """SELECT * FROM conversation_memory 
               WHERE summary LIKE ? OR key_topics LIKE ? OR key_facts LIKE ? 
                  OR full_compressed_text LIKE ?
               ORDER BY date_key DESC LIMIT ?""",
            (like_query, like_query, like_query, like_query, limit)
        )
        return [dict(row) for row in cursor.fetchall()]

    def search_memory_by_tags(self, tags, limit=5):
        if not tags:
            return []
        placeholders = ','.join(['?' for _ in tags])
        cursor = self.conn.execute(
            f"""SELECT DISTINCT cm.* FROM conversation_memory cm
                JOIN memory_tags mt ON cm.id = mt.memory_id
                WHERE mt.tag IN ({placeholders}) ORDER BY cm.date_key DESC LIMIT ?""",
            (*tags, limit)
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_tags(self, memory_id, tags):
        for tag in tags:
            self.conn.execute(
                "INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)",
                (memory_id, tag.strip().lower())
            )
        self.conn.commit()

    def get_recent_summaries(self, days=7):
        start_date = (date.today() - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "SELECT * FROM conversation_memory WHERE date_key >= ? ORDER BY date_key DESC, updated_at DESC",
            (start_date,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_quick_fact(self, fact, source="dialogue"):
        max_facts = self.config["memory"]["max_quick_facts"]
        count = self.conn.execute("SELECT COUNT(*) FROM quick_facts").fetchone()[0]
        if count >= max_facts:
            self.conn.execute("DELETE FROM quick_facts WHERE id = (SELECT MIN(id) FROM quick_facts)")
        self.conn.execute(
            "INSERT INTO quick_facts (fact, source) VALUES (?, ?)",
            (fact, source)
        )
        self.conn.commit()

    def get_relevant_facts(self, limit=5):
        cursor = self.conn.execute(
            "SELECT * FROM quick_facts ORDER BY last_accessed DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_event(self, title, event_date, category="nap", event_time=None,
                  description=None, recurring_rule=None, remind_before_days=1):
        if category == EventCategory.BIRTHDAY:
            recurring_rule = "yearly"
            remind_before_days = 1
        elif category in (EventCategory.TASK, EventCategory.REMINDER):
            recurring_rule = None
            remind_before_days = 0

        cursor = self.conn.execute(
            """INSERT INTO calendar_events 
               (title, description, category, event_date, event_time, 
                recurring_rule, remind_before_days)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, description, category, event_date, event_time,
             recurring_rule, remind_before_days)
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_birthday(self, person_name, birth_date, year=None, relation=None):
        existing = self.conn.execute(
            "SELECT id FROM birthdays WHERE person_name = ? AND birth_date = ?",
            (person_name, birth_date)
        ).fetchone()
        if existing:
            return existing["id"]

        cursor = self.conn.execute(
            "INSERT INTO birthdays (person_name, birth_date, year, relation) VALUES (?, ?, ?, ?)",
            (person_name, birth_date, year, relation)
        )
        birthday_id = cursor.lastrowid

        today = date.today()
        birth_date_obj = datetime.strptime(birth_date, "%m-%d").date()
        next_birthday = date(today.year, birth_date_obj.month, birth_date_obj.day)
        if next_birthday < today:
            next_birthday = date(today.year + 1, birth_date_obj.month, birth_date_obj.day)

        age_hint = f" (исполняется {today.year - year} лет)" if year else ""
        self.add_event(
            title=f"🎂 День рождения: {person_name}{age_hint}",
            event_date=next_birthday.isoformat(),
            category=EventCategory.BIRTHDAY,
            description=f"День рождения {person_name}{age_hint}",
            recurring_rule="yearly",
            remind_before_days=1
        )
        self.conn.commit()
        return birthday_id

    def get_events_for_date(self, target_date=None, include_completed=False):
        if target_date is None:
            target_date = date.today().isoformat()
        target = datetime.strptime(target_date, "%Y-%m-%d").date()

        query = """SELECT * FROM calendar_events 
                   WHERE (event_date = ? 
                       OR (recurring_rule = 'yearly' 
                           AND strftime('%m-%d', event_date) = ?))
                   AND event_date <= ?"""
        params = [target_date, target.strftime("%m-%d"), target_date]
        if not include_completed:
            query += " AND is_completed = 0"
        query += " ORDER BY event_time, category"

        cursor = self.conn.execute(query, params)
        events = [dict(row) for row in cursor.fetchall()]
        for ev in events:
            ev["emoji"] = EventCategory.get_emoji(ev["category"])
            ev["category_name"] = EventCategory.get_name(ev["category"])
        return events

    def get_upcoming_events(self, days=7, include_completed=False):
        today = date.today()
        end_date = today + timedelta(days=days)
        events = []
        current = today
        while current <= end_date:
            day_events = self.get_events_for_date(current.isoformat(), include_completed)
            events.extend(day_events)
            current += timedelta(days=1)
        return events

    def search_events(self, query, limit=10):
        cursor = self.conn.execute(
            """SELECT * FROM calendar_events 
               WHERE (title LIKE ? OR description LIKE ?) AND is_completed = 0
               ORDER BY event_date LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        )
        events = [dict(row) for row in cursor.fetchall()]
        for ev in events:
            ev["emoji"] = EventCategory.get_emoji(ev["category"])
        return events

    def complete_event(self, event_id):
        event = self.conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        if not event or event["category"] == EventCategory.BIRTHDAY:
            return False
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE calendar_events SET is_completed=1, completed_at=?, updated_at=? WHERE id=?",
            (now, now, event_id)
        )
        self.conn.commit()
        return True

    def reschedule_event(self, event_id, new_date):
        event = self.conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        if not event or event["category"] == EventCategory.BIRTHDAY:
            return False
        self.conn.execute(
            "UPDATE calendar_events SET event_date=?, updated_at=? WHERE id=?",
            (new_date, datetime.now().isoformat(), event_id)
        )
        self.conn.commit()
        return True

    def get_due_reminders(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        events = []

        for cat in [EventCategory.REMINDER, EventCategory.TASK]:
            cursor = self.conn.execute(
                "SELECT * FROM calendar_events WHERE category=? AND event_date=? AND is_completed=0",
                (cat, today.isoformat())
            )
            events.extend([dict(row) for row in cursor.fetchall()])

        cursor = self.conn.execute(
            """SELECT * FROM calendar_events 
               WHERE category=? AND is_completed=0
               AND (event_date=? OR (recurring_rule='yearly' AND strftime('%m-%d', event_date)=?))""",
            (EventCategory.BIRTHDAY, tomorrow.isoformat(), tomorrow.strftime("%m-%d"))
        )
        events.extend([dict(row) for row in cursor.fetchall()])

        cursor = self.conn.execute(
            "SELECT * FROM calendar_events WHERE category=? AND event_date<? AND is_completed=0",
            (EventCategory.TASK, today.isoformat())
        )
        overdue = [dict(row) for row in cursor.fetchall()]
        for ev in overdue:
            ev["overdue"] = True
        events.extend(overdue)

        for ev in events:
            ev["emoji"] = EventCategory.get_emoji(ev["category"])
        return events

    def get_all_birthdays(self):
        cursor = self.conn.execute("SELECT * FROM birthdays ORDER BY strftime('%m-%d', birth_date)")
        return [dict(row) for row in cursor.fetchall()]

    def save_trace_step(self, session_id, step_type, tool_name=None,
                        tool_args=None, tool_result=None, thought=None,
                        latency_ms=0, success=True):
        self.conn.execute(
            """INSERT INTO trace_steps (session_id, step_type, tool_name, tool_args,
               tool_result, thought, latency_ms, success)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, step_type, tool_name, tool_args,
             tool_result[:1000] if tool_result else None,
             thought[:500] if thought else None,
             latency_ms, success)
        )
        self.conn.commit()

    def get_trace_stats(self, days=7):
        since = (date.today() - timedelta(days=days)).isoformat()
        total = self.conn.execute(
            "SELECT COUNT(*) as c FROM trace_steps WHERE created_at >= ?", (since,)
        ).fetchone()["c"]
        by_type = {}
        for row in self.conn.execute(
            "SELECT step_type, COUNT(*) as c FROM trace_steps WHERE created_at >= ? GROUP BY step_type",
            (since,)
        ):
            by_type[row["step_type"]] = row["c"]
        success_rate = self.conn.execute(
            "SELECT ROUND(100.0*SUM(success)/COUNT(*),1) as r FROM trace_steps WHERE created_at >= ?",
            (since,)
        ).fetchone()["r"] or 100
        return {"total": total, "by_type": by_type, "success_rate": success_rate, "days": days}

    def search_traces(self, query, limit=10):
        rows = self.conn.execute(
            """SELECT * FROM trace_steps WHERE tool_name LIKE ? OR thought LIKE ? 
               ORDER BY created_at DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]
