# AURA v1.0.3 — Полная схема работы

## Режимы работы

```
                    ┌─────────────────────────────┐
                    │      ПОЛЬЗОВАТЕЛЬ           │
                    │  Telegram | Web | Console    │
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
    │  27 + 89 tools  │                   │  мультиагентный     │
    │  ReAct ×30      │                   │  оркестратор        │
    └────────┬────────┘                   └──────────┬──────────┘
             │                                       │
             ▼                                       ▼
    ┌────────────────┐                   ┌──────────────────────┐
    │   AuraAgent    │                   │   Orchestrator       │
    │  ReAct ×30     │                   │   5 контейнеров      │
    │  LoopGuard     │                   │   DeepSeek           │
    │  TraceCollector│                   │   Дедупликатор       │
    │                │                   └──────────────────────┘
    │ Инструменты:   │
    │ ┌────────────┐ │
    │ │ Память     │ │
    │ │ Календарь  │ │
    │ │ Погода     │ │
    │ │ Поиск/Нов. │ │
    │ │ Браузер    │ │
    │ │ Скиллы (20)│ │
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
                                       │ (markdown,    │
                                       │  таблицы, hr, │
                                       │  код, TTS)    │
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

### Встроенные (27 core tools)

| Группа | Инструменты |
|---|---|
| Память | search_memory, get_today_summary, get_recent_history, remember_fact, get_user_context |
| Календарь | get_today_events, get_upcoming_events, add_event, add_birthday_reminder, search_calendar, complete_task_by_name, reschedule_task, get_birthdays_list, check_due_reminders |
| Погода | get_weather, get_weather_forecast, get_weather_by_coords |
| Интернет | search_web, search_news |
| Браузер | open_url (открыть ссылку в системном браузере) |
| Диагностика | self_diagnose, trace_stats, trace_search, learn_from_traces |
| Файлы skills/ | read_skill_file, edit_skill_file, delete_skill_file, list_skill_files |

### Скиллы (20 skills, 89 skill tools)

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
| api-finder | 12 | АУРА | Поиск API (1554) + ключи + синхронизация |
| daily-bridge | 3 | АУРА | 15 глубоких вопросов |
| auras-heart | 8 | АУРА | Сердце: ритуал + портрет + дневник |
| auras-whisper | 5 | АУРА | Шёпот: 5 тонов |
| auras-care | 6 | АУРА | Забота: еда, вода, отдых |
| initiative-agent | 5 | АУРА | Инициатива: сводка, флирт, идеи |
| radio | 7 | АУРА | Интернет-радио: жанры, настроения |
| sms_sender | 4 | АУРА | Отправка SMS (ключ в .env) |
| radio_browser | 5 | АУРА | Поиск радиостанций |

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
    │  (анти-паттерны, ядро, ключи, шаблоны)   │
    └────────────────────┬─────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────┐
    │  Создаётся: manifest + skill.py + SKILL.md │
    │  Авто-перезагрузка инструментов в агента   │
    │  Валидация → тест → загрузка               │
    └────────────────────────────────────────────┘

Аура может:
- Создавать/редактировать/удалять скиллы во всей папке skills/
- Использовать api-finder для поиска API (1554 шт.)
- Сохранять ключи в skills/custom/.env и синхронизировать
- Импортировать CONFIG, AuraDatabase, WeatherService, DuckDuckGoSearch
- Читать/писать data.json скиллов, README.md, .env
```

## Хранение ключей

```
skills/custom/.env  ←──→  data.json скиллов
       ↑                      ↑
       └── sync_env_from_skills ──┘
       └── push_env_to_skills ────┘
       └── inject_key_to_skill ───┘

Формат: NAME_api_key=VALUE  # описание
Управление: save_api_key, list_api_keys, delete_api_key
```

## Ограничения и лимиты

| Параметр | Значение | Где |
|---|---|---|
| ReAct циклы | 30 | agent.py |
| Обрезка результатов | 8000 символов | agent.py |
| Окно истории | 150 сообщений | agent.py |
| max_tokens (агент) | 36000 | config.json |
| max_tokens (SkillBuilder) | 16000 | skill_builder.py |
| Таймаут агента | 120 секунд | aura_core.py |
| Таймаут TTS (Piper) | безлимитный (локальный) | aura_voice.py |
| Таймаут TTS (Edge) | connect 40с, receive 480с | aura_voice.py |
| Таймаут Telegram API | read/write/connect 20с | main.py |
