# AURA Skills System

Открытая система скиллов. Нейросеть может самостоятельно расширять возможности Ауры.

## Структура скилла

```
my_skill/
├── manifest.json    # Метаданные
├── SKILL.md         # Документация
└── skill.py         # Код с @tools.tool
```

**ВСЕ ТРИ ФАЙЛА ОБЯЗАТЕЛЬНЫ.** Без любого из них скилл не загрузится.

## manifest.json

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "author": "AURA OS",
  "description": "Что делает скилл",
  "category": "tools",
  "dependencies": [],
  "triggers": ["ключевые", "слова"],
  "permissions": ["network"],
  "auto_created": true,
  "stability": "testing"
}
```

## Как создаются скиллы

1. Пользователь: «Аура, создай скилл для...»
2. Skill Builder (LLM) генерирует manifest + SKILL.md + skill.py
3. Валидация → тест в песочнице → интеграция
4. До 3 попыток с авто-исправлением ошибок
5. При провале — откат

## ЧАСТЫЕ ОШИБКИ И КАК ИХ ИЗБЕЖАТЬ

### 1. НЕПРАВИЛЬНЫЕ ИМПОРТЫ
- ❌ `from aura.core import tools` — такого модуля НЕТ
- ❌ `from aura.memory import MemoryStore` — такого модуля НЕТ
- ✅ `from autogen.beta import tools` — единственный правильный импорт для @tools.tool
- ✅ `import json, os, random` — стандартная библиотека
- ✅ `import httpx` — для HTTP (НЕ requests!)

### 2. НЕСУЩЕСТВУЮЩИЕ КЛАССЫ
- ❌ `MemoryStore()` — такого класса нет. Для хранения данных используй JSON-файл.
- ✅ Создай свой класс с `json.loads()` / `json.dumps()` и файлом в папке скилла.
- ✅ Пример ниже в разделе «Хранилище данных».

### 3. ВОЗВРАЩАЕМЫЙ ТИП
- ❌ `return {"key": "value"}` — словарь, плохо читается агентом
- ✅ `return "строка с результатом"` — всегда возвращай str
- ✅ Если нужно вернуть структуру — форматируй как читаемый текст:
  ```python
  return f"Результат:\n  поле1: {val1}\n  поле2: {val2}"
  ```

### 4. НЕЗАВЕРШЁННЫЙ СКИЛЛ
- ❌ Создал только manifest.json и остановился — скилл НЕ загрузится
- ✅ ВСЕГДА создавай все три файла: manifest.json, SKILL.md, skill.py
- Если не успеваешь — скажи пользователю что нужен ещё один вызов edit_skill_file

### 5. ИМПОРТ ИЗ ДРУГИХ СКИЛЛОВ
- ❌ `from skills.builtin.weather_skill.skill import weather_current` — не делай так
- ✅ Каждый скилл самодостаточен. Если нужна чужая функция — скопируй логику или используй httpx напрямую.
- Исключение: `from utils import run_async` — можно, этот модуль общий.

### 6. ЛИШНИЕ ПОЛЯ В manifest.json
- ❌ `"status": "active"` — такого поля нет, скилл упадёт
- ❌ `"tools": [...]` — такого поля нет
- ❌ `"tones": [...]` — такого поля нет
- ✅ Только 12 разрешённых полей: name, version, author, description, category, dependencies, python_version, triggers, permissions, auto_created, stability, created_at

### 7. ЗАБЫТЫЙ @tools.tool ДЕКОРАТОР
- ❌ Функция без `@tools.tool` — SkillLoader её не найдёт, скилл загрузится с 0 инструментов
- ✅ Каждая публичная функция должна быть над `@tools.tool`

## Хранилище данных (ШАБЛОН)

Если скиллу нужно сохранять данные, используй этот паттерн:

```python
import json
from pathlib import Path

_STORE_FILE = Path(__file__).parent / "data.json"

class _Store:
    def __init__(self):
        self._data = []
        if _STORE_FILE.exists():
            try:
                self._data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            except: pass

    def _save(self):
        _STORE_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, entry: str):
        from datetime import datetime
        self._data.append({"text": entry, "ts": datetime.now().isoformat()})
        self._save()

    def search(self, prefix: str, limit: int = 100) -> list:
        return [e["text"] for e in self._data if prefix in e.get("text", "")][-limit:]

store = _Store()
```

## ПОДКЛЮЧЕНИЕ К ЯДРУ АУРЫ

Скилл может использовать эти **реально существующие** модули. Никаких выдуманных!

| Модуль | Импорт | Что даёт |
|---|---|---|
| `autogen.beta` | `from autogen.beta import tools` | `@tools.tool` — ОБЯЗАТЕЛЬНЫЙ декоратор |
| `aura_core` | `from aura_core import CONFIG` | `CONFIG` — весь config.json как dict |
| `aura_core` | `from aura_core import AuraDatabase` | Доступ к памяти, календарю, фактам, трассировке |
| `aura_core` | `from aura_core import EventCategory` | Категории: BIRTHDAY, TASK, REMINDER, EVENT, PLAN, HEALTH |
| `web_search` | `from web_search import WeatherService, WebSearchConfig` | Погода через OpenWeatherMap 2.5 |
| `web_search` | `from web_search import DuckDuckGoSearch, WebSearchConfig` | Поиск через DuckDuckGo |
| `utils` | `from utils import run_async` | Мост async→sync для вызова httpx/погоды/поиска |

**AuraDatabase — главные методы:**
- `db.search_memory_fts("запрос", limit=5)` — поиск по всей памяти
- `db.add_quick_fact("факт")` — сохранить факт навсегда
- `db.get_events_for_date("2026-06-07")` — события на дату
- `db.get_upcoming_events(days=7)` — ближайшие события
- `db.add_event(title, date, category="nap")` — добавить событие
- `db.get_recent_summaries(days=7)` — итоги дней (ключевые темы)
- `db.get_trace_stats(days=7)` — статистика использования инструментов

**CONFIG — самые полезные ключи:**
- `CONFIG["agent"]["model"]` → `"deepseek-v4-pro"`
- `CONFIG["agent"]["max_tokens"]` → `12000`
- `CONFIG["web_search"]["openweathermap_key"]` → ключ погоды
- `CONFIG["memory"]["db_path"]` → путь к aura.db
- `CONFIG["calendar"]` → категории, напоминания

## Установленные скиллы

| Скилл | Инструменты | Описание |
|---|---|---|
| `calendar_skill` | 6 | Даты, повторения, недели |
| `weather_skill` | 3 | Погода OpenWeatherMap 2.5 |
| `web_search_skill` | 2 | Поиск DuckDuckGo |
| `content-sanitizer` | 2 | Очистка чувствительных данных |
| `persona-extractor` | 2 | Извлечение портрета пользователя |
| `session-analyzer` | 2 | Анализ сессий диалога |
| `url-content-fetcher` | 2 | Захват содержимого по URL |
| `moex_stock_tracker` | 5 | Акции MOEX + MACD |
| `kazan_direction_trains` | 3 | Расписание электричек |
| `codebase-mapper` | 4 | Карта кодовой базы проекта |
| `initiative-agent` | 5 | Инициатива, флирт, саморазвитие |
| `auras-heart` | 8 | Сердце: ритуал + портрет + дневник |
| `daily-bridge` | 3 | Мостик: глубокие вопросы |
