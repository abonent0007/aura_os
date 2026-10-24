# Project: auto-money-printer

## Tech Stack
- Python 3.11+
- aiohttp (async HTTP-запросы)
- schedule (планировщик задач)
- feedparser (RSS-ленты)
- python-dotenv (.env загрузка)

## Commands
- Run: `python main.py`
- Dry run (test all once): `python main.py --dry-run`
- Check config: `python main.py --check-config`

## Project Structure (flat)

```
auto-money-printer/
├── main.py                 # точка входа
├── config.py               # загрузка конфигурации из .env
├── .env.example            # пример переменных окружения
├── .env                    # реальные ключи (не коммитить!)
├── requirements.txt        # зависимости
├── AGENTS.md               # этот файл
├── README.md               # описание проекта
├── BUSINESS_PLAN.md        # бизнес-план
├── cpa_base.py             # базовый класс CPA-клиента
├── cpa_epn.py              # ePN.bz API клиент
├── cpa_admitad.py          # Admitad API клиент
├── telegram_bot.py         # Telegram-бот + утилиты
├── news_collector.py       # сбор новостей (RSS + NewsAPI)
├── content_generator.py    # генерация постов через AI
├── scheduler_tasks.py      # планировщик всех задач
├── analytics_tracker.py    # отслеживание метрик
├── utils_logger.py         # настройка логирования
├── logs/                   # логи (автосоздаётся)
└── data/                   # статистика (автосоздаётся)
```

## Code Conventions
- Все импорты — прямые: `from cpa_epn import EPNAPIClient`
- API-клиенты наследуются от `cpa_base.BaseCPAClient`
- Асинхронность через `asyncio` + `aiohttp`
- Логирование через `utils_logger.setup_logging()`
- Конфигурация через `config.Config.from_env()`
- CPA-ссылки всегда с `#реклама`
- Рассылка не чаще 1 раза в 24 часа на пользователя

## Flow
1. `main.py` загружает `Config`
2. `Scheduler` инициализирует все компоненты
3. `schedule` запускает задачи по расписанию:
   - Каждые 3 часа: сбор новостей → генерация поста → публикация в канал
   - Каждый день в 10:00: рекламная рассылка подписчикам
   - Каждые 6 часов: обновление офферов CPA
   - Каждые 30 секунд: обработка сообщений бота

## Что нельзя трогать
- `.env` файл — только руками
- Не менять сигнатуры методов в cpa_base.py без обновления всех клиентов
