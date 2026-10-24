# Project: freelance-hunter

Охотник за работой по кодированию: собирает заказы и вакансии из RSS
(fl.ru, hh.ru, Habr Career, freelancer.com), фильтрует по ключевым словам,
оценивает через LLM (цена/срок/отклик), складывает в SQLite.
Аура показывает найденное пользователю от его имени.

## Tech Stack
- Python 3.11+
- httpx (HTTP-запросы)
- PyYAML (конфиг)
- pytest (тесты)
- LLM: DeepSeek API (OpenAI-совместимый) — глобальный ключ Ауры

## Commands
- Run (один проход): `python extra_sources.py --config config.yaml`
  (расширенный поиск; ядро `python -m freelance_hunter` — запасной путь)
- Проверка источников: `python extra_sources.py --config config.yaml --probe`
- Цикл (каждые 30 мин): `run_loop.bat`
- Тесты: `python -m pytest tests/ -q`
- Установка зависимостей: `pip install -r requirements.txt`

## Project Structure

```
freelance-hunter/
├── extra_sources.py        # расширенный поиск: RSS + HTML, браузерный UA,
│                           # параллельная оценка, лимит токенов, per-source
├── freelance_hunter/       # ядро (запасной конвейер)
│   ├── cli.py              # точка входа, сборка конвейера
│   ├── config.py           # конфиг + глобальные ключи Ауры (${VAR} из .env)
│   ├── collector.py        # RSS/Atom парсер лент
│   ├── filters.py          # скоринг и фильтрация заказов
│   ├── estimator.py        # LLM-оценка (цена, срок, черновик отклика)
│   ├── notifier.py         # Telegram + NullNotifier (заглушка)
│   ├── pipeline.py         # конвейер: собрать → отфильтровать → оценить → сохранить
│   ├── storage.py          # SQLite (orders.db), дедупликация
│   └── models.py           # Order
├── tests/                  # pytest
├── config.yaml             # рабочая конфигурация
├── config.example.yaml     # шаблон
├── orders.db               # база найденных заказов (создаётся автоматически)
├── AGENTS.md               # этот файл
└── README.md
```

## Источники

Живые (проверено `--probe` 12.09.2026):

| Источник | Лента | Особенности |
|---|---|---|
| fl.ru | `https://www.fl.ru/rss/all.xml` | фриланс-заказы |
| hh.ru-python | `...rss?text=python&area=113` | вакансии Python, вся Россия |
| hh.ru-remote | `...&schedule=remote` | удалёнка |
| habr-career | `https://career.habr.com/vacancies/rss?q=python&remote=true` | IT-вакансии |
| freelancer.com | `https://www.freelancer.com/rss.xml` | англ. биржа, режут англ. ключевые слова |

Не работают с текущей сети (отключены, причины в `config.yaml`): freelance.ru,
freelancejob, weblancer, freelancehunt, habr-freelance, weworkremotely,
remoteok, geekjob, kwork (JS-рендер), youdo (блок).

- Добавить источник = строка в `sources` (RSS/Atom или HTML с `pattern`).
- У источника может быть свой `min_score` (доски вакансий строже).
- `estimate_limit: 30` — сколько заказов оценивать за прогон (бережём токены),
  дубли отсеиваются до оценки.
- `max_workers: 6` — параллельные LLM-оценки (52 оценки ≈ 24 секунды
  вместо ~4 минут последовательно).
- `--probe` проверяет источники без LLM: живые/молчащие + примеры.

## Ключи и интеграция с Аурой

Программа использует **глобальные ключи ядра AURA OS** — те же, что и сама Аура:

| Ключ | Откуда | Для чего |
|---|---|---|
| `DEEPSEEK_API_KEY` | `C:\aura_os\.env` | оценка заказов (LLM) |

В `config.yaml` ключи указываются как `${DEEPSEEK_API_KEY}` — `config.py`
подхватывает их из `.env` ядра (см. `_load_global_env()`).
Локальный `.env` проекта, если создан, имеет приоритет.

**Telegram**: без VPN недоступен — уведомления выключены (`NullNotifier`).
Заказы всё равно сохраняются в `orders.db`, их показывает Аура.
Если появится VPN — заполнить `telegram_token` и `telegram_chat_id`.

## Code Conventions
- Пакет `freelance_hunter`, запуск через `python -m freelance_hunter`
- Все сетевые вызовы инжектируются (fetcher/transport) — тестируемость
- Сбой уведомления не теряет заказ: сначала `storage.add(status="new")`, потом notify
- Дедупликация по `(source, external_id)` в SQLite
- LLM-ответ парсится терпимо (markdown-фенсы, границы `{...}`), при сбое — fallback

## Что нельзя трогать
- `config.yaml` — только руками (или Аурой через project_write)
- Сигнатуры `Collector.collect()` / `Notifier.send()` — контракты конвейера
- Формат таблицы `orders` — на неё завязаны скилл Ауры и CRM
