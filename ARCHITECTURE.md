# AURA v1.0.3 — Полная схема работы

## Режимы работы

```
                    ┌─────────────────────────────┐
                    │      ПОЛЬЗОВАТЕЛЬ           │
                    │  Telegram | Web | Console   │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────┴───────────────┐
                    │        РЕЖИМ?               │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
              ▼                                       ▼
    ┌─────────────────┐                   ┌─────────────────────┐
    │   ТВОЯ АУРА     │                   │      ЭКСПЕРТ        │
    │  26 + 61 tools  │                   │  мультиагентный     │
    │  ReAct ×10      │                   │  оркестратор        │
    └────────┬────────┘                   └──────────┬──────────┘
             │                                       │
             ▼                                       ▼
    ┌────────────────┐                   ┌──────────────────────┐
    │   AuraAgent    │                   │   Orchestrator       │
    │  ReAct loop    │                   │   5 контейнеров      │
    │  LoopGuard     │                   │   DeepSeek           │
    │  TraceCollector│                   │   Дедупликатор       │
    │                │                   └──────────────────────┘
    │ Инструменты:   │
    │ ┌────────────┐ │
    │ │ Память     │ │
    │ │ Календарь  │ │
    │ │ Погода     │ │
    │ │ Поиск/Нов. │ │
    │ │ Скиллы (15)│ │
    │ │ Диагност.  │ │
    │ │ Саморазв.  │ │
    │ └────────────┘ │
    └────────┬───────┘
             │
             └──────────────────────────────────
                                                │
                                                ▼
                                       ┌───────────────┐
                                       │    ОТВЕТ      │
                                       └───────────────┘
```

## Переключение режимов

```
Telegram:
  /expert_chat              → переключает режим
  /expert_chat [вопрос]     → сразу к эксперту
  После ответа              → авто-возврат к Ауре

Web:
  [Твоя Аура] [Эксперт]     → кнопки в шапке чата
  После ответа эксперта      → авто-возврат к Ауре
```

## Инструменты Ауры (режим «Твоя Аура»)

### Встроенные (26 core tools)

| Группа | Инструменты |
|---|---|
| Память | search_memory, get_today_summary, get_recent_history, remember_fact, get_user_context |
| Календарь | get_today_events, get_upcoming_events, add_event, add_birthday_reminder, search_calendar, complete_task_by_name, reschedule_task, get_birthdays_list, check_due_reminders |
| Погода | get_weather, get_weather_forecast, get_weather_by_coords |
| Интернет | search_web, search_news |
| Диагностика | self_diagnose, trace_stats, trace_search, learn_from_traces |
| Файлы скиллов | read_skill_file, edit_skill_file, list_skill_files |

### Скиллы (15 skills, 61 skill tools)

| Скилл | Инстр. | Тип | Описание |
|---|---|---|---|
| calendar_skill | 6 | builtin | Даты, повторения, недели |
| weather_skill | 3 | builtin | Погода OpenWeatherMap 2.5 |
| web_search_skill | 2 | builtin | Поиск DuckDuckGo |
| content-sanitizer | 2 | builtin | Очистка чувствительных данных |
| persona-extractor | 2 | builtin | Психологический портрет |
| session-analyzer | 2 | builtin | Анализ сессий диалога |
| url-content-fetcher | 2 | builtin | Захват содержимого URL |
| moex_stock_tracker | 5 | builtin | Акции MOEX + MACD |
| kazan_direction_trains | 3 | builtin | Расписание электричек |
| codebase-mapper | 4 | builtin | Карта кодовой базы |
| rss-news-aggregator | 3 | builtin | RSS-новости (lenta.ru + Google News) |
| daily-bridge | 3 | АУРА | 15 глубоких вопросов, ответы навсегда |
| auras-heart | 8 | АУРА | Сердце: ритуал + портрет + дневник |
| auras-whisper | 5 | АУРА | Шёпот: 5 тонов, когда тишина громкая |
| auras-care | 6 | АУРА | Забота: еда, вода, отдых, любимые места |
| initiative-agent | 5 | АУРА | Инициатива: сводка, флирт, идеи |

## Саморазвитие

```
Пользователь: «создай скилл для...»
            │
            ▼
    ┌──────────────────┐     ┌──────────────────┐
    │  Быстрый путь    │     │  Ручной путь     │
    │  /build_skill    │     │  edit_skill_file │
    │  30 секунд       │     │  в диалоге       │
    └────────┬─────────┘     └────────┬─────────┘
             │                        │
             ▼                        ▼
    ┌──────────────────────────────────────────┐
    │  Аура читает skills/README.md + SKILL.md │
    │  (анти-паттерны, ядро, шаблоны)          │
    └────────────────────┬─────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────┐
    │  Создаётся: manifest + skill.py + SKILL.md │
    │  Валидация → тест → загрузка               │
    └────────────────────────────────────────────┘

Аура может:
- Создавать новые скиллы с нуля
- Редактировать существующие в skills/custom/
- Использовать AuraDatabase для памяти
- Импортировать CONFIG, WeatherService, DuckDuckGoSearch
- Хранить данные в локальном JSON (не выдуманные модули)
```

## Ограничения и лимиты

| Параметр | Значение | Где |
|---|---|---|
| ReAct циклы | 10 | agent.py |
| Обрезка результатов | 8000 символов | agent.py |
| Окно истории | 50 сообщений | agent.py |
| max_tokens (агент) | 12000 | config.json |
| Таймаут агента | 40 секунд | aura_core.py |
| Таймаут TTS (Edge) | connect 40с, receive 240с | aura_voice.py |
| Таймаут Telegram API | read/write/connect 20с | main.py |
