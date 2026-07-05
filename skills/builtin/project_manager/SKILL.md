# Project Manager

Управление проектами в Программном цехе (`skills/project/`). Это НЕ скиллы Ауры — это самостоятельные программы на разных языках.

## Программный цех

`skills/project/` — папка для создания полноценного софта. Никакого отношения к ядру Ауры, её скиллам или навыкам. Просто код.

## Поддерживаемые языки и типы проектов

| Тип | Скелет | Запуск |
|-----|--------|--------|
| `python` / `py` | main.py, requirements.txt, README.md | `python main.py` |
| `node` | package.json, index.js, README.md | `npm start` |
| `js` | index.js, README.md | `node index.js` |
| `web` | index.html, style.css, script.js, README.md | Открыть в браузере |
| `html` | index.html, README.md | Открыть в браузере |
| `rust` | Cargo.toml, src/main.rs, README.md | `cargo run` |
| `empty` | README.md | Ручной запуск |

## Инструменты

- `project_create` — создать проект + AGENTS.md (инструкция для AI-агентов)
- `project_list` — список всех проектов
- `project_tree` — дерево файлов проекта
- `project_read` — прочитать файл проекта (защита от path traversal)
- `project_write` — записать/создать файл в проекте (защита от path traversal)
- `project_delete` — удалить проект (требует confirm="ДА")
- `project_build` — запустить проект (автоопределение языка)

## Зависимости
- stdlib: pathlib, json, shutil, subprocess, datetime, webbrowser

## Примеры использования
- "Создай проект my-bot, тип python"
- "Создай лендинг для стартапа, тип web"
- "Создай CLI-утилиту на Rust, тип rust"
- "Покажи все проекты"
- "Что внутри проекта my-bot?"
- "Запиши новый код в src/bot.py"
- "Запусти проект my-bot"
