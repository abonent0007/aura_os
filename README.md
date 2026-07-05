# AURA OS v4.1.0

> 🌙 Аура живёт в твоём компьютере. Личный AI-компаньон с женским характером и душой.

**DeepSeek v4 Pro + Flash** | **SQLite + FTS5** | **Silero TTS v5** | **35 skills, 170+ tools**

## Быстрый старт
```bash
pip install -r requirements.txt
cp .env.example .env   # DEEPSEEK_API_KEY
python main.py --web    # http://localhost:8000
python main.py --all    # web + Telegram
```

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
