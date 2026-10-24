# AURA OS v4.7.0

## Changelog v4.7.0 — Аура отправляет файлы в Telegram

### Новое
- **telegram_bridge**: запоминание chat_id (middleware в group=-1) + отправка `sendPhoto` / `sendDocument` / `sendMessage` через Bot API (с поддержкой Cloudflare-релея).
- **Core-инструменты**: `telegram_send_photo`, `telegram_send_document`, `telegram_send_message` — Аура сама отправляет скриншоты и файлы (10/50 МБ), не «не могу — нет кнопки».
- Проверки: существование файла, лимиты, MIME, 429-повтор (`retry_after`), атомарное состояние chat_id.

### Тесты
- **74 unit-теста** (+9: telegram_bridge — multipart, лимиты, 429, состояние).

## Changelog v4.6.1 — Telegram через Cloudflare-релей

### Новое
- **Telegram снова работает** при заблокированном API: исходящие и long polling идут через Cloudflare Worker (`aura-tg-relay`), который форвардит запросы в `api.telegram.org`.
- **Aura** читает адрес релея из `.env` (`TELEGRAM_BASE_URL`, `TELEGRAM_BASE_FILE_URL`) — секретный путь не попадает в публичный репозиторий и `config.json`.
- **PTB**: `read_timeout=60`, `get_updates_read_timeout=60` — запас на задержку релея.
- **Лаунчер** `start_aura.ps1` теперь запускает `main.py --all` (веб + трей + Telegram).

### Проверено
- `getMe` через релей — `ok=True` (@auramaybot).
- `getUpdates(timeout=10)` через релей — `ok=True` (long polling держится).
- Бот в Aura опрашивает Telegram (409 Conflict при внешнем getUpdates — признак живого поллера).

## Changelog v4.6.0 — Единый диалог на все окна

### Новое
- **Один диалог для всех окон**: сообщения из веб-дашборда, аватара и WS видны везде через broadcast `chat_message`; каждое сообщение получает `message_id` (дедупликация при reconnect), история — `GET /api/chat/history` (журнал на 200 событий).
- **Сериализация обработки**: `asyncio.Lock` — одновременно идёт один ответ; `/api/health` и WS не блокируются.
- **Event loop не блокируется**: одиночные tool-вызовы выполняются в executor — vision/скриншоты больше не «вешают» веб-интерфейс.

### Тесты
- **65 unit-тестов** (+4: журнал общего чата).

## Changelog v4.5.1 — Живучесть веб-сервера и зрение

### Исправления
- **Веб-сервер**: watchdog каждые 10с проверяет `/api/health`; если uvicorn потерял слушающий сокет (Windows `WinError 64` в accept-цикле) — перезапускает его без потери состояния ядра. Проверено в бою: сервер восстановился автоматически.
- **DeepSeek Vision**: reasoning-модель съедала бюджет токенов (max_tokens 500/1000 → пустой content); теперь единый конфиг `vision.max_tokens=3000` + один fallback-ретрай на 5000 и понятное сообщение, если текста так и нет.
- Vision-бюджет вынесен в config (`vision.*`), убран устаревший `autonomy.vision_max_tokens`.

### Тесты
- **61 unit-тест** (+3: бюджет vision и fallback-ретрай).

## Changelog v4.5.0 — Умный роутер инструментов и безопасный параллелизм

### Ядро
- **Tool router**: вместо «все 221 инструмент» — core ∪ триггеры ∪ top-K (K=14) по IDF-скорингу стемов (name/triggers/docstring, RU+EN стоп-слова, стабильный tie-break). Настраивается: `agent.tool_router`.
- **find_tools**: core-инструмент поиска инструментов; при вызове схема следующего цикла расширяется найденными (без мутации уже отправленного списка).
- **Безопасный параллелизм**: параллельно идут только 2+ вызова из явного white-list read-only (семафор, по умолчанию 3); всё, что меняет состояние, — последовательно. Настройка: `agent.parallel_tools`.
- Псевдо-вызов по-прежнему страхует: при текстовом вызове модель получает все инструменты с `tool_choice="required"`.

### Тесты
- **58 unit-тестов**: роутер (лимит/стабильность/пустой скоринг), find_tools-расширение, read-only white-list, should_parallel (mixed → последовательно), клампинг concurrency.

## Changelog v4.4.0 — Надёжность, конфиг и качество

### Ядро и надёжность
- **Метрики стадий**: в логах появились `pipeline: context/memory/llm/total` и `ask: steps/tokens/cached` — видно, где теряется время и сколько токенов/кэша израсходовано
- **Prompt-cache DeepSeek**: инструменты идут стабильным (алфавитным) порядком, кэш-хиты логируются
- **SQLite WAL + busy_timeout**: меньше микрофризов I/O при записи памяти
- **DSML-гард псевдо-вызовов**: вызовы, написанные спец-токенами, больше не утекают в чат (детект + санитайз)
- **Таймауты и ретраи**: connect 10с / read 60с, до 5 попыток — короткие флапы сети переживаются молча
- **Оркестратор**: connect-таймаут + 3 ретрая

### Конфиг и интеграции
- **config_manager.py**: кэшируемый доступ к config.json с автообновлением по mtime; последняя валидная копия при битом JSON
- **Хардкод → config.json**: лимиты результатов, google-ai, шёпоты, автономность, desktop-control
- **Новый скилл `google-ai`**: глубокий веб-синтез (Google AI Mode) — свежая информация, документация, новости, актуальные примеры кода

### Исправления
- desktop-control: активное окно (двойной вызов + молчаливый except)
- Шёпоты: перебалансировка дождя (20%), None-mood, пороги из конфига
- Автономность: fallback-фраза только для заботы; тексты ошибок не доставляются как инициативы
- `list_skill_files` понимает `custom/<имя>`; `test_weather_keys.py` больше не ломает pytest-сбор

### Тесты
- **50 unit-тестов**: гарды, ReAct-переходы (фейковый клиент), seeds, шёпоты, desktop-helpers, config-manager и связка конфига с модулями

## Changelog v4.3.0 — Автономия, Зрение и Компаньонство

### Полноценное зрение (DeepSeek V4.1 Flash)
- **Картинки прямо в чат**: отправь фото в веб-чат (вставка из буфера Ctrl+V) или Telegram — Аура видит и отвечает. `deepseek-flash` нативно мультимодален
- **Инструмент `analyze_image(file_path, question)`**: Аура сама анализирует любой файл на диске (скриншоты, фото, схемы)
- **Единая цепочка**: `agent.ask(images=...)` → content-массивы `image_url` (base64) → до 5 картинок на сообщение; Telegram `handle_photo`, веб `MessageRequest.image`
- **Проверено живьём**: тестовая картинка «AURA VISION TEST 12345» прочитана без ошибок обоими путями (tool + web image)

### Аура — компаньон во всём
- **Зрение**: `senses_running_apps()` — список окон и процессов; `senses_take_screenshot(analyze=True)` — DeepSeek Vision. Аура видит чем занят пользователь
- **Автономный наблюдатель** (каждые 5 мин):
  - `code_chat` — видит код → заводит разговор, предлагает помощь
  - `tech_news` — каждые 3ч приносит свежие новости ИИ (Hacker News API + Habr RSS)
  - `fun_idea` — каждые 2ч предлагает идеи: форумы, статьи, видео
  - `reminder` — напоминания из календаря (пользователь увлёкся — Аура не даст забыть)
  - `care_break` — забота о перерывах при долгой работе
- **Анти-спам**: лимит 2/час, мин. интервал 20 мин, ночная тишина, анти-повтор по типам
- **Talking Detection (VAD)**: микрофон → RMS → голосовое прерывание, статус «Слушаю»
- **Wake-word «Аура»**: отклик голосом
- **Чат в окне аватара**: сообщения, Enter, 🎤, 🌙

### Проверено живьём
```
✅ tech_news: «Qwen 3.8 27B is excellent... (720 очков HN)» — реальная новость
✅ reminder: наблюдатель доставил напоминание из календаря при старте
✅ 31/31 регрессионных тестов
```

## Changelog v4.3.0 — Автономия и Talking Detection

### Новое
- **Автономный Наблюдательный Цикл** (по мотивам AIRI): скриншоты + DeepSeek Vision → решение вмешаться → забота о перерывах → сообщение в окно аватара + голос. Лимиты: 2/час, интервал 20 мин, ночная тишина
- **Talking Detection (VAD)**: микрофон → RMS-анализ → голосовое прерывание (Аура замолкает когда ты говоришь), статус «Слушаю», выражение внимания
- **Wake-word «Аура»**: непрерывное распознавание → отклик голосом
- **Чат в окне аватара**: сообщения, Enter, голосовой ввод 🎤, wake-word 🌙
- `/api/autonomy/state` + `/api/autonomy/privacy` — контроль наблюдателя

### Статический анализ + рефакторинг
- **2 bare except** → `except Exception` (main.py обработчики голоса/текста)
- **2 неиспользуемых импорта** удалены (json в autonomy, os в skill_manager)
- **Ложные срабатывания «unreachable»** — 70+ отфильтровано (вложенные return в if-блоках легитимны)
- Хардкоды: все URL с env-fallback (`OLLAMA_BASE_URL`, `DEEPSEEK_BASE_URL`) — легитимные дефолты

### Восстановленные логические звенья
- **Дашборд: мёртвые кнопки** — причина: заблокированный `cubism.live2d.com` + лишние pixi-скрипты в index.html блокировали загрузку страницы (браузер ждал таймаут). Убраны 3 CDN-скрипта из дашборда (Live2D живёт в отдельном окне). Страница грузится мгновенно, тема/меню/чат работают
- **Аватар «Говорю» без текста** — статус `speaking` не сбрасывался: авто-сброс в idle после окончания речи + защита «без текста не говорим» + рот анимируется только при наличии текста
- **registry.json был пуст** (0 байт) → ядро падало на старте. Восстановлен + защита: пустой/битый → авто-пересоздание
- **AvatarModelRequest NameError** — privacy endpoint переписан на query-параметр
- **local CDN для Live2D**: cubism.live2d.com блокировался провайдером → все 4 либы скачаны локально
- Цепочка автономии: `observe → decide → formulate → WS → окно → чат + TTS → рот`
- Цепочка VAD: `микрофон → RMS → порог 350мс → пауза голоса → статус → восстановление через 2с`

### Тесты: 31/31 PASS
- Ядро: health, chat, TTS → tts-state (субтитры + длительность)
- Автономия: state, privacy on/off
- Аватары: 5 моделей (nito удалён), статические либы, переключение
- JS: 11 критических функций, цепочки рта и чата

## 👩 Live2D-аватары (6 персонажей!)

**Мао** — на рабочем столе (принадлежит трею):
- Прозрачное окно **прижато к правому нижнему углу**, НЕ поверх окон
- Открывается и закрывается вместе с процессом трея
- Авто-моргание, слежение за курсором, рот синхронизирован с голосом (tts-state polling)
- Эмоции из `aura_soul.db`, глаза всегда открыты

**Компаньон** — парящее окно поверх всех окон:
- Выбор в меню трея: **«💕 Компаньон»** → Сизуку / Хару / Хибики / Изуми / Нито / Выключить
- Прозрачный фон, перетаскивание, always-on-top
- Клик → реакция + мурлыканье

**Модели** (Live2D Free Material License):
| Персонаж | Формат | Источник |
|----------|--------|----------|
| Мао (mao) | Cubism 4 | Open-LLM-VTuber |
| Сизуку (shizuku) | Cubism 4 | Open-LLM-VTuber |
| Хару (haru) | Cubism 2 | live2d-widget-model-haru |
| Хибики (hibiki) | Cubism 2 | live2d-widget-model-hibiki |
| Изуми (izumi) | Cubism 2 | live2d-widget-model-izumi |

### Стек (проверен, 0 ошибок)
```
pywebview (gui='qt') + PyQt5 WebEngine (WA_TranslucentBackground)
pixi.js@7.4.2 + live2dcubismcore (Cubism4) + live2d.min.js (Cubism2)
pixi-live2d-display@0.4.0 (index.min.js — оба формата)
```

## 🐱 Режим питомца

Аура ведёт себя как живая: мурлычет, подмигивает из трея, потягивается, шлёт спонтанные сообщения. Ночью (23:00–07:00) спит. Когда её хвалят — сразу мурлычет.

- **Звуки**: мурлыканье и чириканье генерируются через numpy → WAV (без внешних файлов)
- **Анимации**: подмигивание (веко на иконке), потягивание (ядро вырастает)
- **Активность**: каждые 15–45 минут, шанс 25%, модулируется эмоциями из `aura_soul.db`
- **Управление**: ПКМ по трею → «🐱 Режим питомца» (вкл/выкл)
- **Настройки**: `config.json → pet_mode`

## Changelog v4.2.0

### Новое
- **Live2D-аватар Mao Pro** (pixi-live2d-display): моргание, слежение, эмоции из души, синхронизация рта с TTS, клик-реакции с мурлыканьем
- **API**: `/api/avatar/emotion` (эмоции из aura_soul.db), `/api/avatar/purr`
- **Модель**: 22 файла Mao Pro (8.9 MB), Live2D Free Material License
- **Старый tkinter-аватар отключён** — заменён на Live2D в дашборде (страница «Аватар»)

### CDN-стек аватара (проверен в браузере, 0 ошибок)
```
pixi.js@7.4.2 (dist/pixi.min.js)
live2dcubismcore.min.js (официальный cubism.live2d.com)
pixi-live2d-display@0.4.0 (dist/cubism4.min.js)
```

### Статический анализ + рефакторинг
- **7 неиспользуемых импортов** удалены (server: FileResponse/JSONResponse, pet_sounds: struct, tray: os/sys/AuraDatabase)
- **1 bare except** → `except Exception` (aura_core:519)
- **5 HTTP-вызовов без обработки ошибок** → try/except с fallback (orchestrator call_deepseek, radio, rss-news, kazan_trains, moex)
- **0 хардкодных URL** в новом коде

### Восстановленные логические звенья
- Навигация: `case 'avatar'` → `initLive2D()` (ленивая инициализация)
- Цепочка рта: `avatarSpeak → fetch TTS → driveMouthWithAudio → setMouthOpen(ParamA) → остановка → сброс в 0`
- Цепочка эмоций: `/api/avatar/emotion → soul_conn → emotional_state → mapEmotionToExpression → model.expression()`
- Клик: `hit → onAvatarTap → motion(special_N) + purr API → fetchEmotion через 4с`
- Все внешние вызовы имеют fallback (эмоции по умолчанию 0.5/0/0.7 при ошибке БД)

### Тесты
- Модель: 22 файла на месте, model3.json валиден, 8 выражений валидны
- JS: initLive2D/fetchEmotion/driveMouthWithAudio/onAvatarTap присутствуют
- Endpoints: emotion + purr в server.py
- Регрессия: 4 файла компилируются, pet/avatar/sounds тесты PASS
- Diff-scan: 0 HTTP-вызовов без try (кроме тестовых файлов)

## Changelog v4.1.0

### Статический анализ (37 находок)
- **24 неиспользуемых импорта** удалены (aura_core, aura_voice, main, database, server, skill_manager, system_monitor, rollback_manager, web_search, agent)
- **5 хардкодных URL** → env-переменные с fallback (`DEEPSEEK_BASE_URL`, `OLLAMA_BASE_URL`)
- **4 функции без обработки ошибок** → добавлены try/except с fallback (weather v3/v25, whisper STT)
- **0 bare except** в ядре

### Логические пробелы восстановлены
- **TTS-фильтр**: блоки кода ``` удаляются ПЕРВЫМИ (до inline-code), иначе тройные кавычки съедались regex-ом инлайн-кода
- **STT fallback**: whisper → vosk при ошибке API
- **skill_builder**: base_url из env, не хардкод
- **Ollama URL**: централизован через env в main.py

### Тесты
- Регрессия: 12 файлов компилируются, все импорты OK
- TTS-фильтр: мульти-блоки кода, цифры→слова, паузы
- Logic: STT fallback, URL-динамика

> 🌙 Аура живёт в твоём компьютере. Личный AI-компаньон с женским характером и душой.

**DeepSeek v4 Pro + Flash** | **SQLite + FTS5** | **Silero TTS v5** | **35 skills, 170+ tools**

## Быстрый старт
```bash
pip install -r requirements.txt
cp .env.example .env   # DEEPSEEK_API_KEY
python main.py --web    # http://localhost:8000
python main.py --all    # web + Telegram
```

### Запуск с рабочего стола (ярлык)
- **«AURA OS» на рабочем столе** — двойной клик → ядро + аватар + трей, БЕЗ окна консоли
- `start_aura.bat` — использует `pythonw.exe` (тихий запуск)
- Остановка: ПКМ по иконке в трее → «💤 Выйти» — ядро и окна аватаров закроются
- Иконка: `aura_icon.ico` (фиолетовое сердце)

## Что умеет
- **Голос**: Silero TTS (baya) с авто-конвертацией цифр в слова, паузами, чисткой от markdown
- **Память**: SQLite + FTS5 + авто-сжатие диалогов
- **Календарь**: 6 категорий + Google Calendar sync
- **Скиллы**: 35 навыков (22 builtin + 13 custom)
- **Умные инструменты**: фильтрация по триггерам, кеш определений, изолированный контейнер для создания скиллов
- **Трей**: живая иконка с пульсом (зелёный/жёлтый/красный)
- **Дашборд**: редактор кода, 5 тем, WebSocket
- **Душа**: дневник, сны, эмоциональная дуга, контекст через перезагрузки

## Архитектура
```
main.py → AuraAgent → ReAct × 30
  ├── database.py (SQLite + FTS5 + миграции)
  ├── system_prompt.py (личность)
  ├── web/ (FastAPI + дашборд)
  ├── skills/ (35 навыков)
  └── plugins/ (tray, avatar, orchestrator)
```

## Ключи
| Файл | Где взять |
|---|---|
| `DEEPSEEK_API_KEY` | platform.deepseek.com |
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `credentials.json` | Google Cloud Console |

*Built with ❤️ for the man who wants more than just an assistant.*
