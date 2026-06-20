# API Finder v3.0.0 — OSINT Key Hunter + DDG + Каталог

Три модуля в одном скилле. 17 инструментов.

## Модуль 1: Каталог Public-APIs
Парсит `public-apis/public-apis` → 1554+ API в ~60 категориях. Кеш 24ч.

### Инструменты:
- `search_apis` — поиск по названию, категории, авторизации, HTTPS, CORS
- `list_categories` — все категории с количеством API
- `get_api_details` — полная информация об API
- `get_random_api` — случайное API
- `suggest_skill_from_api` — шаблон для нового скилла
- `scan_free_apis_for_keys` — бесплатные API + существующие ключи

## Модуль 2: GitHub OSINT Key Hunter 🔍
Ищет **живые API ключи** в публичных репозиториях GitHub по 18 паттернам:
OpenAI (legacy/project/service), Anthropic Claude, DeepSeek, Google Gemini,
Hugging Face, Cohere, Replicate, ElevenLabs, Perplexity, Together AI,
Mistral AI, Groq, Lepton AI, Fireworks AI, OpenWeatherMap.

**Нужен `GITHUB_TOKEN` в `.env`!** (уже сохранён)

### Инструменты:
- `hunt_keys_github` — OSINT-охота, автосохранение в .env

## Модуль 3: DuckDuckGo Search 🔎
Поиск через библиотеку `duckduckgo-search` (DDGS). 
Если библиотека не установлена — fallback на HTML-парсинг через BeautifulSoup.

### Инструменты:
- `search_ddg` — текстовый поиск DuckDuckGo
- `find_api_ddg` — найти API по описанию (DDG + каталог)

## Управление ключами
- `save_api_key` — сохранить ключ в .env
- `list_api_keys` — показать все ключи (значения скрыты)
- `delete_api_key` — удалить ключ
- `inject_key_to_skill` — внедрить ключ в data.json скилла
- `sync_env_from_skills` — собрать ключи из data.json → .env
- `push_env_to_skills` — разослать ключи из .env → data.json

## Диагностика
- `diagnose` — состояние всех модулей, доступность библиотек, список ключей

## Зависимости
- `httpx` — HTTP-запросы
- `duckduckgo-search` — DDGS (опционально, есть fallback)
- `beautifulsoup4` — fallback HTML-парсинг
- `requests` — GitHub API + fallback

## Примеры
- "Найди API для отправки SMS"
- "Охота на ключи GitHub" → `hunt_keys_github`
- "Поищи через DDG лучшее API для геокодинга" → `search_ddg`
- "Найди API для конвертации валют через DDG" → `find_api_ddg`
- "Сохрани ключ deepseek_api_key = sk-abc123"
- "Синхронизируй ключи"
- "Диагностика api-finder" → `diagnose`

## Примечания
- v3.0.0 — добавлены модули GitHub OSINT + DuckDuckGo
- GitHub токен: `ghp_5JWt...` (твой, сохранён в .env)
- Найденные ключи автосохраняются в .env с пометкой "OSINT-found"
- Ключи из публичных репозиториев могут быть невалидными — проверяй!
