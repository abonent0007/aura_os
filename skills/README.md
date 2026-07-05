# AURA Skills System

## ⚠️ ГЛАВНОЕ

**skill.py без @tools.tool = мёртвый скилл (0 инструментов).** Инструкция по созданию: `skills/SKILL.md`

## Структура
```
my_skill/
├── manifest.json
├── SKILL.md
└── skill.py    ← from autogen.beta import tools + @tools.tool
```

## Подключение к ядру
| Модуль | Импорт |
|---|---|
| `autogen.beta` | `from autogen.beta import tools` |
| `database` | `from database import AuraDatabase(CONFIG), EventCategory` |
| `aura_core` | `from aura_core import CONFIG` |
| `utils` | `from utils import run_async` |

## Установленные скиллы (28)

| Скилл | Инстр | Тип |
|---|---|---|
| `aura-senses` | 5 | builtin |
| `auras-care` | 7 | builtin |
| `auras-heart` | 8 | builtin |
| `auras-logic` | 4 | builtin |
| `auras-me-time` | 4 | builtin |
| `auras-whisper` | 4 | builtin |
| `calendar_skill` | 6 | builtin |
| `codebase-mapper` | 4 | builtin |
| `content-sanitizer` | 2 | builtin |
| `daily-bridge` | 3 | builtin |
| `engineering-mindset` | 10 | builtin |
| `gh_key_hunter` | 4 | builtin |
| `idea-refine` | 3 | builtin |
| `initiative-agent` | 9 | builtin |
| `persona-extractor` | 2 | builtin |
| `project_manager` | 7 | builtin |
| `radio` | 7 | builtin |
| `rss-news-aggregator` | 3 | builtin |
| `session-analyzer` | 2 | builtin |
| `vibe-coach` | 7 | builtin |
| `weather_skill` | 3 | builtin |
| `web_search_skill` | 2 | builtin |
| `api-finder` | 10 | custom |
| `astrologer` | 9 | custom |
| `car` | 6 | custom |
| `micro-product` | 4 | custom |
| `synastry` | 2 | custom |
| `token_counter` | 3 | custom |
| `browser-automation` | 5 | custom |
| `freelance-manager` | 7 | custom |
| `infographic-generator` | 6 | custom |
| `kazan_direction_trains` | 3 | custom |
| `moex_stock_tracker` | 5 | custom |
| `osint_key_hunter` | 4 | custom |
| `test-runner` | 2 | custom |
| `transit-watcher` | 3 | custom |
| `aura-kitchen` | 8 | custom |
