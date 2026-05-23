# google_calendar.py
"""
Модуль синхронизации AURA OS с Google Calendar.
Двусторонняя синхронизация с сохранением категорий AURA.
"""

import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
@dataclass
class GoogleCalendarConfig:
    """Настройки Google Calendar интеграции"""
    credentials_file: str = "credentials.json"
    calendar_id: str = "primary"
    sync_interval_minutes: int = 5
    sync_future_days: int = 90
    sync_past_days: int = 7
    
    # Маппинг AURA-категорий на Google-цвета
    # Цвета Google Calendar: 
    # 1-синий, 2-зеленый, 3-фиолетовый, 4-красный, 5-желтый,
    # 6-оранжевый, 7-бирюзовый, 8-серый, 9-жирный синий, 10-жирный зеленый,
    # 11-жирный красный
    aura_to_google_color: Dict[str, str] = field(default_factory=lambda: {
        "drr": "4",    # Красный — дни рождения
        "zad": "1",    # Синий — задачи
        "nap": "5",    # Желтый — напоминания
        "evt": "3",    # Фиолетовый — события/встречи
        "pln": "6",    # Оранжевый — планы
        "med": "7",    # Бирюзовый — здоровье
    })

    # Имена цветов Google (для обратного маппинга)
    google_color_names: Dict[str, str] = field(default_factory=lambda: {
        "1": "Синий", "2": "Зеленый", "3": "Фиолетовый",
        "4": "Красный", "5": "Желтый", "6": "Оранжевый",
        "7": "Бирюзовый", "8": "Серый", "9": "Темно-синий",
        "10": "Темно-зеленый", "11": "Темно-красный",
    })
    
    # Обратный маппинг: Google-цвет → AURA-категория
    google_color_to_aura: Dict[str, str] = field(default_factory=lambda: {
        "4": "drr",    # Красный → день рождения
        "2": "drr",    # Зеленый → день рождения (часто используют)
        "1": "zad",    # Синий → задача
        "5": "nap",    # Желтый → напоминание
        "11": "zad",   # Темно-красный → задача
        "10": "zad",   # Темно-зеленый → задача
        "3": "evt",    # Фиолетовый → событие
        "6": "pln",    # Оранжевый → план
        "7": "med",    # Бирюзовый → здоровье
        "8": "evt",    # Серый → событие
        "9": "pln",    # Темно-синий → план
    })
    
    # Префиксы заголовков для категорий (используются в Google Calendar)
    category_prefixes: Dict[str, str] = field(default_factory=lambda: {
        "drr": "🎂",
        "zad": "📋",
        "nap": "🔔",
        "evt": "📅",
        "pln": "📌",
        "med": "🏥",
    })


# ============================================================
# 2. КЛИЕНТ GOOGLE CALENDAR
# ============================================================
class GoogleCalendarClient:
    """
    Клиент для работы с Google Calendar API через Service Account.
    """
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self, config: GoogleCalendarConfig = None):
        self.config = config or GoogleCalendarConfig()
        self.service = None
        self._init_service()
    
    def _init_service(self):
        """Инициализация сервиса Google Calendar.
        Поддерживает Service Account (type: service_account) и OAuth Client (installed)."""
        creds_path = self.config.credentials_file

        if not Path(creds_path).exists():
            raise FileNotFoundError(
                f"credentials.json не найден!\n"
                f"   1. Создай Service Account или OAuth Client в Google Cloud Console\n"
                f"   2. Скачай JSON-ключ\n"
                f"   3. Сохрани как credentials.json"
            )

        with open(creds_path, "r") as f:
            creds_data = json.load(f)

        if "type" in creds_data and creds_data["type"] == "service_account":
            credentials = service_account.Credentials.from_service_account_file(
                creds_path, scopes=self.SCOPES
            )
        elif "installed" in creds_data or "web" in creds_data:
            credentials = self._auth_oauth(creds_data)
        else:
            raise ValueError("Неизвестный формат credentials.json. Ожидается Service Account или OAuth Client.")

        self.service = build('calendar', 'v3', credentials=credentials)

        try:
            self.service.calendarList().get(calendarId=self.config.calendar_id).execute()
            print(f"Google Calendar connected: {self.config.calendar_id}")
        except HttpError as e:
            if e.resp.status == 404:
                print(f"Calendar '{self.config.calendar_id}' not found")
                self._list_calendars()
            else:
                raise

    def _auth_oauth(self, creds_data: dict) -> "Credentials":
        """OAuth 2.0 авторизация. Использует token.json (современный формат)."""
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials

        token_path = Path(self.config.credentials_file).parent / "token.json"
        SCOPES = ['https://www.googleapis.com/auth/calendar']

        credentials = None

        # Пробуем загрузить сохранённый токен
        if token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except Exception:
                token_path.unlink(missing_ok=True)

        # Обновляем просроченный токен
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(credentials.to_json())
            except Exception:
                token_path.unlink(missing_ok=True)
                credentials = None

        # Первая авторизация — открываем браузер
        if not credentials or not credentials.valid:
            try:
                client_config = creds_data.get("installed") or creds_data.get("web", creds_data)
                flow = InstalledAppFlow.from_client_config(
                    {"installed": client_config}, SCOPES
                )
                print("\nOpening browser for Google Calendar authorization...")
                print("If the browser doesn't open, check:")
                print("  https://console.cloud.google.com/apis/credentials/consent")
                print("  Add your email as a test user, then try again.")
                credentials = flow.run_local_server(port=0, open_browser=True)

                # Сохраняем токен для будущих запусков
                with open(token_path, "w") as f:
                    f.write(credentials.to_json())
                print("Token saved to token.json")

            except Exception as e:
                raise RuntimeError(
                    f"OAuth authorization failed: {e}\n"
                    f"Fix: https://console.cloud.google.com/apis/credentials/consent\n"
                    f"     Add your email as a test user, or click 'Publish App'."
                )

        return credentials
    
    def _list_calendars(self):
        """Вывести список доступных календарей"""
        try:
            calendars = self.service.calendarList().list().execute()
            for cal in calendars.get('items', []):
                print(f"   • {cal['summary']} (ID: {cal['id']})")
        except Exception:
            pass
    
    # ============ ЧТЕНИЕ СОБЫТИЙ ============
    
    def get_events(
        self,
        time_min: datetime = None,
        time_max: datetime = None,
        max_results: int = 500,
        sync_token: str = None
    ) -> dict:
        """
        Получение событий из Google Calendar.
        singleEvents=True разворачивает повторяющиеся события в отдельные экземпляры.
        """
        now = datetime.now(timezone.utc)
        
        if time_min is None:
            time_min = now - timedelta(days=self.config.sync_past_days)
        if time_max is None:
            time_max = now + timedelta(days=self.config.sync_future_days)
        
        time_min_str = time_min.isoformat()
        time_max_str = time_max.isoformat()
        
        params = {
            'calendarId': self.config.calendar_id,
            'timeMin': time_min_str,
            'timeMax': time_max_str,
            'maxResults': max_results,
            'singleEvents': True,
            'orderBy': 'startTime',
            'showDeleted': False,
        }
        
        if sync_token:
            params['syncToken'] = sync_token
        
        try:
            events_result = self.service.events().list(**params).execute()
            return events_result
        except HttpError as e:
            if e.resp.status == 410:
                # Sync token устарел — полная пересинхронизация
                print("🔄 Sync token устарел, полная пересинхронизация")
                params.pop('syncToken', None)
                return self.service.events().list(**params).execute()
            raise
    
    # ============ СОЗДАНИЕ СОБЫТИЙ ============
    
    def create_event(self, event_data: dict) -> dict:
        """
        Создание события в Google Calendar.
        
        event_data должен содержать:
        - summary: заголовок
        - start: {'dateTime': '...', 'timeZone': '...'} или {'date': '...'}
        - end: аналогично start
        - description (опционально)
        - colorId (опционально, для AURA-категорий)
        """
        # Если передан colorId как имя категории AURA — преобразуем
        if 'aura_category' in event_data:
            aura_cat = event_data.pop('aura_category')
            event_data['colorId'] = self.config.aura_to_google_color.get(aura_cat, "1")
            
            # Добавляем префикс к заголовку
            prefix = self.config.category_prefixes.get(aura_cat, "")
            if prefix and not event_data.get('summary', '').startswith(prefix):
                event_data['summary'] = f"{prefix} {event_data['summary']}"
        
        try:
            result = self.service.events().insert(
                calendarId=self.config.calendar_id,
                body=event_data
            ).execute()
            print(f"✅ Событие создано в Google: {result.get('summary')}")
            return result
        except HttpError as e:
            print(f"❌ Ошибка создания события: {e}")
            raise
    
    # ============ ОБНОВЛЕНИЕ СОБЫТИЙ ============
    
    def update_event(self, event_id: str, event_data: dict) -> dict:
        """Обновление события в Google Calendar"""
        try:
            result = self.service.events().update(
                calendarId=self.config.calendar_id,
                eventId=event_id,
                body=event_data
            ).execute()
            print(f"✅ Событие обновлено: {result.get('summary')}")
            return result
        except HttpError as e:
            print(f"❌ Ошибка обновления: {e}")
            raise
    
    # ============ УДАЛЕНИЕ СОБЫТИЙ ============
    
    def delete_event(self, event_id: str) -> bool:
        """Удаление события из Google Calendar"""
        try:
            self.service.events().delete(
                calendarId=self.config.calendar_id,
                eventId=event_id
            ).execute()
            print(f"🗑️ Событие удалено из Google: {event_id}")
            return True
        except HttpError as e:
            print(f"❌ Ошибка удаления: {e}")
            return False


# ============================================================
# 3. СИНХРОНИЗАТОР AURA ↔ GOOGLE
# ============================================================
class CalendarSynchronizer:
    """
    Двусторонняя синхронизация между AURA и Google Calendar.
    
    Логика:
    1. Читаем события Google → создаем/обновляем в AURA
    2. Читаем события AURA → создаем/обновляем в Google
    3. Разруливаем конфликты по external_id (Google event ID)
    """
    
    def __init__(self, db, config: GoogleCalendarConfig = None):
        self.db = db
        self.config = config or GoogleCalendarConfig()
        self.google = GoogleCalendarClient(self.config)
        
        # Синхронизационные метаданные
        self.sync_token = None
        self.last_sync = None
        
        # Инициализируем таблицу синхронизации
        self._init_sync_table()
    
    def _init_sync_table(self):
        """Создает таблицу для отслеживания синхронизации"""
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
        
        # Загружаем sync token
        row = self.db.conn.execute(
            "SELECT value FROM sync_metadata WHERE key = 'google_sync_token'"
        ).fetchone()
        if row:
            self.sync_token = row["value"]
    
    def _save_sync_token(self, token: str):
        """Сохраняет sync token для инкрементальной синхронизации"""
        self.sync_token = token
        self.db.conn.execute(
            """INSERT OR REPLACE INTO sync_metadata (key, value, updated_at)
               VALUES ('google_sync_token', ?, ?)""",
            (token, datetime.now().isoformat())
        )
        self.db.conn.commit()
    
    # ============ ДВУСТОРОННЯЯ СИНХРОНИЗАЦИЯ ============
    
    async def full_sync(self) -> dict:
        """
        Полная двусторонняя синхронизация.
        Возвращает статистику.
        """
        stats = {
            "google_to_local": 0,
            "local_to_google": 0,
            "updated": 0,
            "deleted": 0,
            "errors": 0,
        }
        
        print("\n🔄 Запуск синхронизации AURA ↔ Google Calendar...")
        
        # 1. Google → AURA
        try:
            g2l = await self._sync_google_to_local()
            stats["google_to_local"] = g2l
        except Exception as e:
            print(f"❌ Ошибка Google→AURA: {e}")
            stats["errors"] += 1
        
        # 2. AURA → Google
        try:
            l2g = await self._sync_local_to_google()
            stats["local_to_google"] = l2g
        except Exception as e:
            print(f"❌ Ошибка AURA→Google: {e}")
            stats["errors"] += 1
        
        # 3. Разруливание удаленных
        try:
            deleted = await self._sync_deletions()
            stats["deleted"] = deleted
        except Exception as e:
            print(f"❌ Ошибка синхронизации удалений: {e}")
            stats["errors"] += 1
        
        self.last_sync = datetime.now()
        print(f"✅ Синхронизация завершена: {stats}")
        
        return stats
    
    async def _sync_google_to_local(self) -> int:
        """
        Синхронизация Google Calendar → AURA.
        Без syncToken — всегда полная выборка, чтобы захватить новые повторения.
        """
        count = 0

        # Всегда полная синхронизация (не инкрементальная) для recurring events
        result = self.google.get_events(sync_token=None)

        for event in result.get('items', []):
            try:
                if self._process_google_event(event):
                    count += 1
            except Exception as e:
                print(f"Error processing event {event.get('id', '?')}: {e}")

        if count > 0:
            print(f"Imported from Google: {count} events")

        return count
    
    def _process_google_event(self, event: dict) -> bool:
        """
        Обрабатывает одно событие из Google Calendar.
        Определяет категорию по цвету/заголовку, создает/обновляет в AURA.
        """
        google_id = event.get('id')
        if not google_id:
            return False
        
        # Проверяем, есть ли уже в синхронизации
        existing_sync = self.db.conn.execute(
            "SELECT * FROM calendar_sync WHERE google_event_id = ?",
            (google_id,)
        ).fetchone()
        
        # Извлекаем данные события
        summary = event.get('summary', 'Без названия')
        description = event.get('description', '')
        
        # Определяем категорию
        aura_category = self._detect_aura_category(event)
        
        # Определяем дату/время
        start = event.get('start', {})
        end = event.get('end', {})
        
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
        
        # Определяем повторения
        recurring_rule = None
        if event.get('recurrence'):
            for rule in event['recurrence']:
                if 'RRULE:FREQ=YEARLY' in rule:
                    recurring_rule = 'yearly'
                    aura_category = 'drr'  # Годовые повторы → дни рождения
                    break
        
        # Статус завершения
        is_completed = event.get('status') == 'cancelled'
        
        if existing_sync:
            # Обновляем существующее
            local_event_id = existing_sync["local_event_id"]
            
            self.db.conn.execute(
                """UPDATE calendar_events 
                   SET title = ?, description = ?, category = ?,
                       event_date = ?, event_time = ?,
                       recurring_rule = ?, is_completed = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (summary, description, aura_category, event_date, event_time,
                 recurring_rule, is_completed, datetime.now().isoformat(),
                 local_event_id)
            )
            
            # Обновляем etag
            self.db.conn.execute(
                "UPDATE calendar_sync SET google_etag = ?, last_synced_at = ?, sync_status = 'synced' WHERE google_event_id = ?",
                (event.get('etag', ''), datetime.now().isoformat(), google_id)
            )
        else:
            # Создаем новое в AURA
            cursor = self.db.conn.execute(
                """INSERT INTO calendar_events 
                   (title, description, category, event_date, event_time, recurring_rule, is_completed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (summary, description, aura_category, event_date, event_time,
                 recurring_rule, is_completed)
            )
            local_id = cursor.lastrowid
            
            # Создаем запись синхронизации
            self.db.conn.execute(
                """INSERT INTO calendar_sync (local_event_id, google_event_id, google_etag, sync_status)
                   VALUES (?, ?, ?, 'synced')""",
                (local_id, google_id, event.get('etag', ''))
            )
        
        self.db.conn.commit()
        return True
    
    def _detect_aura_category(self, event: dict) -> str:
        """
        Определяет категорию AURA на основе Google-события.
        Приоритет: заголовок > цвет > эвристика.
        """
        summary = event.get("summary", "").lower()

        # 1. По заголовку (высший приоритет)
        birthday_keywords = ['день рождения', 'день рождение', 'др ', '🎂', 'birthday', 'родился', 'родилась',
                             'с днем рождения', 'happy birthday']
        if any(kw in summary for kw in birthday_keywords):
            return 'drr'

        task_keywords = ['задача', 'сделать', 'выполнить', 'дедлайн', '📋', 'проект', 'заявление', 'написать']
        if any(kw in summary for kw in task_keywords):
            return 'zad'

        medical_keywords = ['врач', 'доктор', 'больниц', 'клиник', 'анализ', 'процедур', 'спорт', 'тренировк', '🏥']
        if any(kw in summary for kw in medical_keywords):
            return 'med'

        # 2. По цвету (если заголовок не определил)
        color_id = event.get("colorId", "")
        if color_id in self.config.google_color_to_aura:
            return self.config.google_color_to_aura[color_id]

        # 3. По умолчанию — событие
        return "evt"
    
    async def _sync_local_to_google(self) -> int:
        """
        Синхронизация AURA → Google Calendar.
        Отправляет локальные события, которых ещё нет в Google.
        """
        count = 0
        
        # Находим локальные события без Google-связки
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
            except Exception as e:
                print(f"⚠️ Ошибка отправки события #{ev['id']}: {e}")
        
        if count > 0:
            print(f"📤 Отправлено в Google: {count} событий")
        
        return count
    
    def _push_local_event_to_google(self, event: dict) -> bool:
        """Отправляет одно локальное событие в Google Calendar"""
        aura_category = event.get('category', 'nap')
        
        # Формируем тело события для Google
        google_event = {
            'summary': event.get('title', ''),
            'description': event.get('description', ''),
            'colorId': self.config.aura_to_google_color.get(aura_category, '1'),
        }
        
        # Дата/время
        event_date = event['event_date']
        event_time = event.get('event_time')
        
        if event_time:
            dt_start = f"{event_date}T{event_time}:00"
            # По умолчанию +1 час если нет end_date
            dt = datetime.strptime(f"{event_date} {event_time}", "%Y-%m-%d %H:%M")
            dt_end = dt + timedelta(hours=1)
            dt_end_str = dt_end.strftime("%Y-%m-%dT%H:%M:00")
            
            google_event['start'] = {
                'dateTime': dt_start,
                'timeZone': 'Europe/Moscow'
            }
            google_event['end'] = {
                'dateTime': dt_end_str,
                'timeZone': 'Europe/Moscow'
            }
        else:
            google_event['start'] = {'date': event_date}
            google_event['end'] = {'date': event_date}
        
        # Повторения
        if event.get('recurring_rule') == 'yearly':
            google_event['recurrence'] = ['RRULE:FREQ=YEARLY']
        
        # Создаем в Google
        result = self.google.create_event(google_event)
        
        if result and result.get('id'):
            # Сохраняем связку
            self.db.conn.execute(
                """INSERT INTO calendar_sync (local_event_id, google_event_id, google_etag, sync_status)
                   VALUES (?, ?, ?, 'synced')""",
                (event['id'], result['id'], result.get('etag', ''))
            )
            self.db.conn.commit()
            return True
        
        return False
    
    async def _sync_deletions(self) -> int:
        """
        Синхронизация удалений: если в AURA помечено завершенным,
        удаляем из Google (кроме дней рождения).
        """
        count = 0
        
        # Находим завершенные локальные задачи/напоминания с Google-связкой
        completed = self.db.conn.execute(
            """SELECT ce.*, cs.google_event_id 
               FROM calendar_events ce
               JOIN calendar_sync cs ON ce.id = cs.local_event_id
               WHERE ce.is_completed = 1 
               AND ce.category != 'drr'
               AND cs.sync_status = 'synced'"""
        ).fetchall()
        
        for ev in completed:
            google_id = ev['google_event_id']
            if google_id and self.google.delete_event(google_id):
                # Обновляем статус синхронизации
                self.db.conn.execute(
                    "UPDATE calendar_sync SET sync_status = 'deleted', last_synced_at = ? WHERE google_event_id = ?",
                    (datetime.now().isoformat(), google_id)
                )
                count += 1
        
        self.db.conn.commit()
        
        if count > 0:
            print(f"🗑️ Удалено из Google: {count} завершенных задач")
        
        return count


# ============================================================
# 4. ФОНОВЫЙ СИНХРОНИЗАТОР
# ============================================================
class BackgroundSynchronizer:
    """
    Фоновый шедулер для периодической синхронизации.
    """
    
    def __init__(self, synchronizer: CalendarSynchronizer, interval_minutes: int = 5):
        self.synchronizer = synchronizer
        self.interval = interval_minutes * 60  # в секундах
        self.is_running = False
        self._task = None
    
    async def start(self):
        """Запуск фоновой синхронизации"""
        self.is_running = True
        print(f"🔄 Фоновая синхронизация каждые {self.interval // 60} мин.")
        
        while self.is_running:
            try:
                await self.synchronizer.full_sync()
            except Exception as e:
                print(f"❌ Ошибка фоновой синхронизации: {e}")
            
            await asyncio.sleep(self.interval)
    
    def stop(self):
        """Остановка"""
        self.is_running = False
        print("🛑 Фоновая синхронизация остановлена")


# ============================================================
# 5. ТЕСТ
# ============================================================
async def test_google_calendar():
    """Тест подключения и синхронизации"""
    from aura_core import AuraDatabase
    
    print("=" * 60)
    print("🧪 Тест Google Calendar синхронизации")
    print("=" * 60)
    
    # Проверяем наличие credentials.json
    if not Path("credentials.json").exists():
        print("\n❌ credentials.json не найден!")
        print("\n📋 Инструкция по настройке:")
        print("1. Иди в https://console.cloud.google.com")
        print("2. Создай проект и включи Google Calendar API")
        print("3. Создай Service Account")
        print("4. Скачай JSON-ключ → переименуй в credentials.json")
        print("5. Дай сервисному аккаунту доступ к календарю")
        print("   (email аккаунта → добавить в настройках календаря)")
        return
    
    # Инициализация
    db = AuraDatabase()
    config = GoogleCalendarConfig(
        credentials_file="credentials.json",
        calendar_id="primary",
        sync_interval_minutes=5
    )
    
    try:
        sync = CalendarSynchronizer(db, config)
        
        # Тестовая синхронизация
        stats = await sync.full_sync()
        print(f"\n📊 Статистика синхронизации:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        # Показываем события после синхронизации
        events = db.get_upcoming_events(days=7)
        print(f"\n📅 Событий в AURA после синхронизации: {len(events)}")
        for ev in events[:5]:
            emoji = ev.get('emoji', '📌')
            print(f"   {emoji} {ev['title']} — {ev['event_date']}")
        
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_google_calendar())