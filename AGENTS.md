# Project: AURA OS

> 🌙 AURA — она живёт в твоём компьютере. Персональный AI-компаньон с женским характером, глубокой памятью и душой.

## Tech Stack
- **Python 3.11** — основной язык
- **DeepSeek v4 Pro** — основной LLM (через OpenAI-совместимый API)
- **DeepSeek v4 Flash** — компрессор диалогов
- **SQLite + FTS5** — память и полнотекстовый поиск
- **FastAPI + uvicorn** — веб-интерфейс
- **python-telegram-bot** — Telegram-бот
- **Silero TTS v5 (baya)** — голос (PyTorch, локально)
- **Piper TTS (irina)** — запасной голос
- **Vosk** — распознавание речи
- **Vue 3 (CDN)** — дашборд (опционально)

## Commands
- **Run**: `python main.py --web` (веб), `python main.py --all` (всё), `python main.py --console` (консоль)
- **Install**: `pip install -r requirements.txt`
- **Setup voice**: `setup_vosk.bat`
- **Env**: скопируй `.env.example` → `.env`, пропиши `DEEPSEEK_API_KEY`

## Code Conventions
- **Скиллы**: `from autogen.beta import tools` + `@tools.tool` — **единственный** правильный способ. Никаких `smolagents`, `@tool` без `.tool`.
- **База данных**: `from database import AuraDatabase, EventCategory`. Конструктор: `AuraDatabase(CONFIG)`.
- **Системный промпт**: `system_prompt.py` — отдельный файл, не трогай без крайней нужды.
- **Возвращаемый тип**: все инструменты возвращают `str`, не `dict`.
- **HTTP**: `httpx` (асинхронный), не `requests`.
- **Пути**: используй `pathlib.Path`, не `os.path`.
- **Логирование**: `loguru` (`from loguru import logger`).
- **Бекапы**: перед правками — `rollback_manager.create_backup(reason="что меняешь")`.

## Project Structure
```
aura_os/
├── main.py               # точка входа (Telegram, Web, Console)
├── aura_core.py           # ядро: агент, инструменты, память (~1500 строк)
├── database.py            # БД: SQLite, FTS5, миграции (~570 строк)
├── system_prompt.py       # личность Ауры (~110 строк)
├── aura_voice.py          # голос: STT + TTS (~930 строк)
├── autogen/beta/          # слой совместимости (Agent, tools, config)
│   ├── agent.py           # ReAct-агент ×30 циклов
│   ├── config.py          # OpenAIConfig
│   └── tools.py           # function_to_openai_tool
├── web/                   # FastAPI + дашборд
│   ├── server.py          # 24+ эндпоинтов + WebSocket
│   ├── templates/         # Jinja2
│   └── static/            # JS, CSS
├── skills/                # 31 скилл
│   ├── builtin/           # 20 встроенных (личность, ядро)
│   ├── custom/            # 10 custom (интеграции, API)
│   └── project/           # Программный цех (отдельные проекты)
├── plugins/               # tray, avatar, orchestraator
├── hooks/                 # жизненный цикл (session_start и др.)
├── database.py            # БД слой
└── system_prompt.py       # личность Ауры
```

## What NOT to touch
- `autogen/beta/agent.py` — ReAct-цикл, менять осторожно
- `system_prompt.py` — личность Ауры, править вдумчиво
- `config.json` — структура критична для работы
- `skills/builtin/auras-heart/`, `auras-care/` — ядро характера

## When fixing skills
1. Сначала `read_skill_file("имя", "skill.py")` — прочитай код
2. `edit_skill_file("имя", "skill.py", content)` — сохрани исправление
3. `reload_skills()` — перезагрузи (автоматически после сохранения)
4. `system_health()` — проверь что всё работает

## Creating new skills
Use `build_skill("описание")` — creates skill in isolated container without conversation history.
The container reads `skills/SKILL.md` + `skills/README.md` and generates all 3 files automatically.

## Key globals
- `_skill_manager_ref` — ссылка на SkillManager
- `_agent_ref` — ссылка на Agent
- `CONFIG` — весь config.json как dict
- `SYSTEM_PROMPT` — личность Ауры (из system_prompt.py)
