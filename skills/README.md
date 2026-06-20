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

### 5. ИМПОРТ ИЗ ДРУГИХ СКИЛЛОВ
- ❌ `from skills.builtin.weather_skill.skill import weather_current` — не делай так
- ✅ Каждый скилл самодостаточен. Исключение: `from utils import run_async` — можно.

### 6. ЛИШНИЕ ПОЛЯ В manifest.json
- ❌ `"status": "active"`, `"tools": [...]`, `"tones": [...]` — скилл упадёт
- ✅ Только 12 разрешённых полей

### 7. ЗАБЫТЫЙ @tools.tool ДЕКОРАТОР
- ❌ Функция без `@tools.tool` — 0 инструментов
- ✅ Каждая публичная функция должна быть над `@tools.tool`

## Хранилище данных (ШАБЛОН)

```python
import json
from pathlib import Path

_STORE_FILE = Path(__file__).parent / "data.json"

class _Store:
    def __init__(self):
        self._data = []
        if _STORE_FILE.exists():
            try: self._data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
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

| Модуль | Импорт | Что даёт |
|---|---|---|
| `autogen.beta` | `from autogen.beta import tools` | `@tools.tool` — ОБЯЗАТЕЛЬНЫЙ декоратор |
| `aura_core` | `from aura_core import CONFIG` | Весь config.json как dict |
| `aura_core` | `from aura_core import AuraDatabase` | Память, календарь, факты, трассировка |
| `aura_core` | `from aura_core import EventCategory` | Категории календаря |
| `web_search` | `from web_search import WeatherService, WebSearchConfig` | Погода OpenWeatherMap 2.5 |
| `web_search` | `from web_search import DuckDuckGoSearch, WebSearchConfig` | Поиск DuckDuckGo |
| `utils` | `from utils import run_async` | Мост async→sync |

## Поиск API для новых скиллов

Используй `api-finder` (12 инструментов): `search_apis`, `suggest_skill_from_api`, `list_categories`, `get_random_api`, `get_api_details`, `save_api_key`, `list_api_keys`, `delete_api_key`, `inject_key_to_skill`, `sync_env_from_skills`, `push_env_to_skills`, `scan_free_apis_for_keys`.

Данные из `public-apis/public-apis` (GitHub, 1554 API), кеш 24ч.

## Хранение API-ключей: skills/custom/.env

Формат: `NAME_api_key=VALUE  # описание`

Синхронизация: `.env` ↔ `data.json` скиллов через `inject_key_to_skill`, `sync_env_from_skills`, `push_env_to_skills`.

## Установленные скиллы (20)

| Скилл | Инстр. | Тип | Описание |
|---|---|---|---|
| `calendar_skill` | 6 | builtin | Даты, повторения, недели |
| `weather_skill` | 3 | builtin | Погода OpenWeatherMap 2.5 |
| `web_search_skill` | 2 | builtin | Поиск DuckDuckGo |
| `content-sanitizer` | 2 | builtin | Очистка чувствительных данных |
| `persona-extractor` | 2 | builtin | Психологический портрет |
| `session-analyzer` | 2 | builtin | Анализ сессий диалога |
| `url-content-fetcher` | 2 | builtin | Захват содержимого URL |
| `moex_stock_tracker` | 5 | builtin | Акции MOEX + MACD |
| `kazan_direction_trains` | 3 | builtin | Расписание электричек |
| `codebase-mapper` | 4 | builtin | Карта кодовой базы |
| `rss-news-aggregator` | 3 | builtin | RSS-новости (lenta.ru + Google News) |
| `api-finder` | 12 | АУРА | Поиск API + управление ключами + синхронизация |
| `daily-bridge` | 3 | АУРА | 15 глубоких вопросов, ответы навсегда |
| `auras-heart` | 8 | АУРА | Сердце: ритуал + портрет + дневник |
| `auras-whisper` | 5 | АУРА | Шёпот: 5 тонов, когда тишина громкая |
| `auras-care` | 6 | АУРА | Забота: еда, вода, отдых, любимые места |
| `initiative-agent` | 5 | АУРА | Инициатива: сводка, флирт, идеи |
| `radio` | 7 | АУРА | Интернет-радио: жанры, настроения, история |
| `sms_sender` | 4 | АУРА | Отправка SMS через sms.ru (ключ в .env) |
| `radio_browser` | 5 | АУРА | Поиск радиостанций через Radio Browser API |
