
# calendar_skill/google_sync.py
# Google Calendar синхронизация — вынесено из google_calendar.py
# Используется инструментами в skill.py

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, field


@dataclass
class GoogleCalendarConfig:
    credentials_file: str = "credentials.json"
    calendar_id: str = "primary"
    sync_future_days: int = 90
    sync_past_days: int = 7

    aura_to_google_color: Dict[str, str] = field(default_factory=lambda: {
        "drr": "4", "zad": "1", "nap": "5",
        "evt": "3", "pln": "6", "med": "7",
    })

    google_color_to_aura: Dict[str, str] = field(default_factory=lambda: {
        "4": "drr", "2": "drr", "1": "zad", "5": "nap",
        "11": "zad", "10": "zad", "3": "evt",
        "6": "pln", "7": "med", "8": "evt", "9": "pln",
    })

    category_prefixes: Dict[str, str] = field(default_factory=lambda: {
        "drr": "🎂", "zad": "📋", "nap": "🔔",
        "evt": "📅", "pln": "📌", "med": "🏥",
    })


class GoogleCalendarClient:
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, config: GoogleCalendarConfig = None):
        self.config = config or GoogleCalendarConfig()
        self.service = None
        self._init_service()

    def _init_service(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        creds_path = self.config.credentials_file
        if not Path(creds_path).exists():
            raise FileNotFoundError(f"credentials.json не найден: {creds_path}")

        with open(creds_path, "r") as f:
            creds_data = json.load(f)

        if creds_data.get("type") == "service_account":
            credentials = service_account.Credentials.from_service_account_file(
                creds_path, scopes=self.SCOPES
            )
        elif "installed" in creds_data or "web" in creds_data:
            credentials = self._auth_oauth(creds_data)
        else:
            raise ValueError("Неизвестный формат credentials.json")

        self.service = build('calendar', 'v3', credentials=credentials)
        self.service.calendarList().get(calendarId=self.config.calendar_id).execute()

    def _auth_oauth(self, creds_data: dict):
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_path = Path(self.config.credentials_file).parent / "token.json"
        credentials = None

        if token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(str(token_path), self.SCOPES)
            except Exception:
                token_path.unlink(missing_ok=True)

        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(credentials.to_json())
            except Exception:
                token_path.unlink(missing_ok=True)
                credentials = None

        if not credentials or not credentials.valid:
            client_config = creds_data.get("installed") or creds_data.get("web", creds_data)
            flow = InstalledAppFlow.from_client_config({"installed": client_config}, self.SCOPES)
            credentials = flow.run_local_server(port=0, open_browser=True)
            with open(token_path, "w") as f:
                f.write(credentials.to_json())

        return credentials

    def get_events(self, time_min=None, time_max=None, max_results=500) -> dict:
        from googleapiclient.errors import HttpError
        now = datetime.now(timezone.utc)
        if time_min is None:
            time_min = now - timedelta(days=self.config.sync_past_days)
        if time_max is None:
            time_max = now + timedelta(days=self.config.sync_future_days)

        params = {
            'calendarId': self.config.calendar_id,
            'timeMin': time_min.isoformat(),
            'timeMax': time_max.isoformat(),
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime',
            'showDeleted': False,
        }
        try:
            return self.service.events().list(**params).execute()
        except HttpError as e:
            if e.resp.status == 410:
                return self.service.events().list(**params).execute()
            raise

    def create_event(self, event_data: dict) -> dict:
        if 'aura_category' in event_data:
            aura_cat = event_data.pop('aura_category')
            event_data['colorId'] = self.config.aura_to_google_color.get(aura_cat, "1")
            prefix = self.config.category_prefixes.get(aura_cat, "")
            if prefix and not event_data.get('summary', '').startswith(prefix):
                event_data['summary'] = f"{prefix} {event_data['summary']}"
        return self.service.events().insert(
            calendarId=self.config.calendar_id, body=event_data
        ).execute()

    def delete_event(self, event_id: str) -> bool:
        from googleapiclient.errors import HttpError
        try:
            self.service.events().delete(
                calendarId=self.config.calendar_id, eventId=event_id
            ).execute()
            return True
        except HttpError:
            return False


class CalendarSynchronizer:
    """Двусторонняя синхронизация AURA ↔ Google Calendar."""

    def __init__(self, db, config: GoogleCalendarConfig = None):
        self.db = db
        self.config = config or GoogleCalendarConfig()
        self.google = GoogleCalendarClient(self.config)
        self._init_sync_table()

    def _init_sync_table(self):
        self.db.conn.executescript("""
            CREATE TABLE IF NOT EXISTS calendar_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                local_event_id INTEGER,
                google_event_id TEXT UNIQUE,
                google_etag TEXT,
                last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sync_status TEXT DEFAULT 'synced',
                FOREIGN KEY (local_event_id) REFERENCES calendar_events(id)
            );
            CREATE TABLE IF NOT EXISTS sync_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.db.conn.commit()

    def full_sync(self) -> dict:
        stats = {"google_to_local": 0, "local_to_google": 0, "deleted": 0, "errors": 0}
        try:
            stats["google_to_local"] = self._sync_google_to_local()
        except Exception as e:
            stats["errors"] += 1
            stats["_error"] = str(e)
        try:
            stats["local_to_google"] = self._sync_local_to_google()
        except Exception as e:
            stats["errors"] += 1
            stats["_error2"] = str(e)
        try:
            stats["deleted"] = self._sync_deletions()
        except Exception as e:
            pass
        return stats

    def _sync_google_to_local(self) -> int:
        count = 0
        result = self.google.get_events()
        for event in result.get('items', []):
            try:
                if self._process_google_event(event):
                    count += 1
            except Exception:
                pass
        return count

    def _process_google_event(self, event: dict) -> bool:
        google_id = event.get('id')
        if not google_id:
            return False

        existing = self.db.conn.execute(
            "SELECT * FROM calendar_sync WHERE google_event_id = ?", (google_id,)
        ).fetchone()

        summary = event.get('summary', 'Без названия')
        description = event.get('description', '')
        aura_category = self._detect_aura_category(event)

        start = event.get('start', {})
        event_date = None
        event_time = None

        if start.get('dateTime'):
            dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            event_date = dt.strftime('%Y-%m-%d')
            event_time = dt.strftime('%H:%M')
        elif start.get('date'):
            event_date = start['date']

        if not event_date:
            return False

        recurring_rule = None
        if event.get('recurrence'):
            for rule in event['recurrence']:
                if 'RRULE:FREQ=YEARLY' in rule:
                    recurring_rule = 'yearly'
                    aura_category = 'drr'
                    break

        is_completed = event.get('status') == 'cancelled'
        now_iso = datetime.now().isoformat()

        if existing:
            local_id = existing["local_event_id"]
            self.db.conn.execute(
                """UPDATE calendar_events SET title=?, description=?, category=?,
                   event_date=?, event_time=?, recurring_rule=?, is_completed=?, updated_at=?
                   WHERE id=?""",
                (summary, description, aura_category, event_date, event_time,
                 recurring_rule, is_completed, now_iso, local_id)
            )
            self.db.conn.execute(
                "UPDATE calendar_sync SET google_etag=?, last_synced_at=?, sync_status='synced' WHERE google_event_id=?",
                (event.get('etag', ''), now_iso, google_id)
            )
        else:
            cursor = self.db.conn.execute(
                """INSERT INTO calendar_events (title, description, category, event_date, event_time, recurring_rule, is_completed)
                   VALUES (?,?,?,?,?,?,?)""",
                (summary, description, aura_category, event_date, event_time, recurring_rule, is_completed)
            )
            local_id = cursor.lastrowid
            self.db.conn.execute(
                "INSERT INTO calendar_sync (local_event_id, google_event_id, google_etag, sync_status) VALUES (?,?,?,'synced')",
                (local_id, google_id, event.get('etag', ''))
            )

        self.db.conn.commit()
        return True

    def _detect_aura_category(self, event: dict) -> str:
        summary = event.get("summary", "").lower()
        if any(kw in summary for kw in ['день рождения', 'birthday', '🎂']):
            return 'drr'
        if any(kw in summary for kw in ['задача', 'сделать', 'дедлайн', '📋']):
            return 'zad'
        if any(kw in summary for kw in ['врач', 'доктор', 'больниц', 'спорт', '🏥']):
            return 'med'
        color_id = event.get("colorId", "")
        return self.config.google_color_to_aura.get(color_id, "evt")

    def _sync_local_to_google(self) -> int:
        count = 0
        local_events = self.db.conn.execute(
            """SELECT ce.* FROM calendar_events ce
               LEFT JOIN calendar_sync cs ON ce.id = cs.local_event_id
               WHERE cs.google_event_id IS NULL
               AND ce.event_date >= date('now', '-30 days')
               ORDER BY ce.created_at"""
        ).fetchall()

        for ev in local_events:
            try:
                if self._push_local_event_to_google(dict(ev)):
                    count += 1
            except Exception:
                pass
        return count

    def _push_local_event_to_google(self, event: dict) -> bool:
        aura_category = event.get('category', 'nap')
        google_event = {
            'summary': event.get('title', ''),
            'description': event.get('description', ''),
            'colorId': self.config.aura_to_google_color.get(aura_category, '1'),
        }

        event_date = event['event_date']
        event_time = event.get('event_time')

        if event_time:
            dt_start = f"{event_date}T{event_time}:00"
            dt = datetime.strptime(f"{event_date} {event_time}", "%Y-%m-%d %H:%M")
            dt_end = dt + timedelta(hours=1)
            google_event['start'] = {'dateTime': dt_start, 'timeZone': 'Europe/Moscow'}
            google_event['end'] = {'dateTime': dt_end.strftime("%Y-%m-%dT%H:%M:00"), 'timeZone': 'Europe/Moscow'}
        else:
            google_event['start'] = {'date': event_date}
            google_event['end'] = {'date': event_date}

        if event.get('recurring_rule') == 'yearly':
            google_event['recurrence'] = ['RRULE:FREQ=YEARLY']

        result = self.google.create_event(google_event)
        if result and result.get('id'):
            self.db.conn.execute(
                "INSERT INTO calendar_sync (local_event_id, google_event_id, google_etag, sync_status) VALUES (?,?,?,'synced')",
                (event['id'], result['id'], result.get('etag', ''))
            )
            self.db.conn.commit()
            return True
        return False

    def _sync_deletions(self) -> int:
        count = 0
        completed = self.db.conn.execute(
            """SELECT ce.*, cs.google_event_id FROM calendar_events ce
               JOIN calendar_sync cs ON ce.id = cs.local_event_id
               WHERE ce.is_completed = 1 AND ce.category != 'drr' AND cs.sync_status = 'synced'"""
        ).fetchall()

        for ev in completed:
            google_id = ev['google_event_id']
            if google_id and self.google.delete_event(google_id):
                self.db.conn.execute(
                    "UPDATE calendar_sync SET sync_status='deleted', last_synced_at=? WHERE google_event_id=?",
                    (datetime.now().isoformat(), google_id)
                )
                count += 1
        self.db.conn.commit()
        return count

    def get_sync_status(self) -> dict:
        total = self.db.conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0]
        synced = self.db.conn.execute("SELECT COUNT(*) FROM calendar_sync WHERE sync_status='synced'").fetchone()[0]
        unsynced = self.db.conn.execute(
            "SELECT COUNT(*) FROM calendar_events ce LEFT JOIN calendar_sync cs ON ce.id=cs.local_event_id WHERE cs.google_event_id IS NULL"
        ).fetchone()[0]
        last = self.db.conn.execute("SELECT MAX(last_synced_at) FROM calendar_sync").fetchone()[0]
        return {"total": total, "synced": synced, "unsynced": unsynced, "last_sync": last or "никогда"}

    def check_connection(self) -> dict:
        try:
            cal = self.google.service.calendarList().get(calendarId=self.config.calendar_id).execute()
            return {"connected": True, "calendar": cal.get("summary", self.config.calendar_id), "timezone": cal.get("timeZone", "unknown")}
        except Exception as e:
            return {"connected": False, "error": str(e)}
