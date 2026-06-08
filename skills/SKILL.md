# SKILL.md — Шаблон документации скилла

Этот файл — образец для AI. Каждый скилл в AURA OS должен иметь свой `SKILL.md` внутри своей папки.
Структура ниже показывает **что и как писать** в SKILL.md для нового скилла.

---

## Обязательная структура

```markdown
# Название скилла (краткое, на русском)

Краткое описание (1 предложение) — что делает скилл, зачем нужен.

## Возможности
- Пункт 1 — что умеет
- Пункт 2
- Пункт 3

## Инструменты
- `tool_name` — что делает, когда использовать
- `another_tool` — описание

## Зависимости
- `httpx` — для HTTP-запросов
- (если нет — написать «нет»)

## Примеры использования
- "Пример запроса пользователя 1"
- "Пример запроса пользователя 2"
- "Пример запроса пользователя 3"

## Примечания
- Ограничения (если есть)
- Нужен ли API-ключ (где взять)
- Особенности работы
```

---

## Правила написания
1. **Язык:** русский (основной), можно английский для tool-имён
2. **Краткость:** весь SKILL.md ≤ 500 символов (без учёта примеров)
3. **Без эмодзи** в коде и названиях инструментов
4. **Примеры:** 2-4 реальных фраз, которые пользователь может сказать
5. **Зависимости:** только реально используемые библиотеки
6. **API-ключи:** если скиллу нужен ключ — указать где получить и как настроить

---

## АНТИ-ПАТТЕРНЫ (ЧЕГО НЕ ДЕЛАТЬ В skill.py)

### Импорты — только правильные

```python
# ✅ РАЗРЕШЁННЫЕ ИМПОРТЫ
from autogen.beta import tools      # ОБЯЗАТЕЛЬНО - для @tools.tool
import json, os                     # стандартная библиотека
import httpx                        # HTTP-запросы (НЕ requests)
import random                       # если нужен random
from pathlib import Path            # для работы с путями
from datetime import datetime       # даты

# ✅ ПОДКЛЮЧЕНИЕ К ЯДРУ АУРЫ
from utils import run_async         # async→sync мост для httpx/погоды/поиска
from aura_core import CONFIG        # весь config.json как dict (CONFIG["agent"], CONFIG["web_search"], ...)
from aura_core import AuraDatabase  # доступ к памяти и календарю (search_memory_fts, add_quick_fact, get_events_for_date)
from web_search import WebSearchConfig, DuckDuckGoSearch, WeatherService  # поиск и погода
from aura_core import EventCategory # категории календаря: BIRTHDAY="drr", TASK="zad", REMINDER="nap"

# ❌ ЗАПРЕЩЁННЫЕ ИМПОРТЫ — таких модулей НЕТ
from aura.core import tools         # МОДУЛЬ НЕ СУЩЕСТВУЕТ
from aura.memory import MemoryStore # МОДУЛЬ НЕ СУЩЕСТВУЕТ
import requests                     # блокирует event loop, используй httpx
```

### Возвращаемый тип — всегда str
```python
# ✅ ПРАВИЛЬНО
def my_tool(param: str = "") -> str:
    result = do_something(param)
    return f"Результат: {result}"

# ❌ НЕПРАВИЛЬНО
def my_tool(param: str = "") -> dict:
    return {"key": "value"}    # агент плохо читает словари
```

### Хранилище данных — свой JSON, не выдуманный модуль
```python
# ✅ ПРАВИЛЬНО — файл в папке скилла
import json
from pathlib import Path

_DATA = Path(__file__).parent / "data.json"

def _load():
    if _DATA.exists():
        return json.loads(_DATA.read_text(encoding="utf-8"))
    return []

def _save(data):
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ❌ НЕПРАВИЛЬНО
from aura.memory import MemoryStore  # такого модуля НЕТ
memory = MemoryStore()               # класс не существует
```

### HTTP-запросы — через httpx с потоком
```python
# ✅ ПРАВИЛЬНО — httpx в отдельном потоке
import threading, asyncio

def _fetch(url):
    result = []
    def _run():
        loop = asyncio.new_event_loop()
        async def _get():
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(url)
                return r.text
        try:
            result.append(loop.run_until_complete(_get()))
        finally:
            loop.close()
    t = threading.Thread(target=_run); t.start(); t.join(20)
    return result[0] if result else ""

# ❌ НЕПРАВИЛЬНО
import requests                      # синхронный, блокирует
r = requests.get(url)                # НЕ ИСПОЛЬЗОВАТЬ

import urllib.request                # НЕ ИСПОЛЬЗОВАТЬ — используй httpx
```

### Всегда создавай ВСЕ ТРИ файла
- manifest.json — метаданные
- SKILL.md — документация
- skill.py — код

Без любого из трёх файлов скилл не загрузится. Если не успеваешь — скажи пользователю и создай остальные следующим вызовом edit_skill_file.

### manifest.json — только разрешённые поля
Разрешённые поля (ровно эти, без лишних):
```json
{
  "name": "...", "version": "1.0.0", "author": "...", "description": "...",
  "category": "tools|personality|automation|productivity|entertainment|integration",
  "dependencies": [], "python_version": ">=3.11",
  "triggers": [...], "permissions": [...],
  "auto_created": true, "stability": "testing", "created_at": "..."
}
```
❌ НЕ добавляй поля `status`, `tools`, `tones`, `enabled` — их нет в спецификации, скилл упадёт.

### Каждая функция должна иметь @tools.tool
```python
# ✅ ПРАВИЛЬНО
@tools.tool
def my_tool(param: str = "") -> str:
    """Описание инструмента."""
    ...

# ❌ НЕПРАВИЛЬНО
def my_tool(param: str = "") -> str:   # без @tools.tool — не будет обнаружен!
    ...
```
Без `@tools.tool` декоратора SkillLoader не найдёт функцию — скилл загрузится с 0 инструментов.

### Не импортируй из других скиллов
Каждый скилл самодостаточен. Если нужна функция из другого скилла — либо скопируй код, либо используй httpx напрямую.

---

## ПОДКЛЮЧЕНИЕ К ЯДРУ АУРЫ

Скилл может взаимодействовать с ядром через эти реальные модули:

### aura_core.CONFIG — вся конфигурация
```python
from aura_core import CONFIG
# CONFIG["agent"]["model"]        — "deepseek-v4-pro"
# CONFIG["agent"]["max_tokens"]   — 12000
# CONFIG["web_search"]            — ключи, поиск, погода
# CONFIG["memory"]["db_path"]     — путь к БД
# CONFIG["calendar"]              — категории, напоминания
```

### aura_core.AuraDatabase — память и календарь
```python
from aura_core import AuraDatabase
db = AuraDatabase()
db.search_memory_fts("запрос", limit=5)         # поиск по памяти
db.add_quick_fact("факт", source="dialogue")     # сохранить факт
db.get_events_for_date("2026-06-07")             # события на дату
db.get_upcoming_events(days=7)                   # ближайшие события
db.add_event(title, date, category="nap")        # добавить событие
db.save_daily_summary(date_key, compressed, key_topics)  # сохранить итог дня
db.get_trace_stats(days=7)                       # статистика использования
```

### utils.run_async — мост async→sync
```python
from utils import run_async
# Используй когда синхронному @tools.tool нужно вызвать async-функцию:
result = run_async(some_async_function())
```

### web_search.* — поиск и погода
```python
from web_search import WebSearchConfig, DuckDuckGoSearch, WeatherService
# Поиск:
cfg = WebSearchConfig(default_results=5)
searcher = DuckDuckGoSearch(cfg)
results = run_async(searcher.search("запрос", 5))
# Погода:
ws = WeatherService(WebSearchConfig(openweathermap_key="...", default_city="Москва"))
weather = run_async(ws.get_weather("Москва", "today"))
```

### aura_core.EventCategory — категории календаря
```python
from aura_core import EventCategory
# EventCategory.BIRTHDAY = "drr"     🎂 Дни рождения
# EventCategory.TASK = "zad"         📋 Задачи
# EventCategory.REMINDER = "nap"     🔔 Напоминания
# EventCategory.EVENT = "evt"        📅 События
# EventCategory.PLAN = "pln"         📝 Планы
# EventCategory.HEALTH = "med"       💊 Здоровье
```

### autogen.beta — инструменты агента
```python
from autogen.beta import tools      # @tools.tool декоратор
from autogen.beta import Agent      # создать под-агента для сложного анализа
from autogen.beta import config as ag_config  # OpenAIConfig
```

---

## Пример: weather_skill/SKILL.md

```markdown
# Weather Skill

Встроенный скилл AURA OS для получения погоды через OpenWeatherMap 2.5 API.

## Возможности
- Текущая погода по названию города
- Прогноз на завтра и неделю
- Погода по точным координатам

## Инструменты
- `weather_current` — текущая погода для города
- `weather_forecast` — прогноз на today/tomorrow/week
- `weather_by_coords` — погода по lat/lon

## Зависимости
- `httpx`

## Примеры
- "Какая погода в Москве?"
- "Прогноз на завтра в Казани"
- "Какая температура в Лондоне?"

## Примечания
- API: OpenWeatherMap 2.5 (free tier)
- Ключ в .env: OPENWEATHERMAP_API_KEY=...
```

---

## Пример: web_search_skill/SKILL.md

```markdown
# Web Search Skill

Встроенный скилл AURA OS для поиска в интернете через DuckDuckGo.

## Возможности
- Поиск по текстовым запросам
- Поиск новостей

## Инструменты
- `search_web_ddgs` — поиск фактов, цен, рецептов
- `search_news_ddgs` — поиск новостей, событий

## Зависимости
- `ddgs>=8.0`

## Примеры
- "Найди в интернете рецепт борща"
- "Какие новости сегодня?"
```
