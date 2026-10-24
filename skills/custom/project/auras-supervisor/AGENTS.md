# AGENTS.md — auras-supervisor

## Что это
Внешний супервизор Ауры: запускает ядро, следит за кодом возврата, при падении
откатывает скиллы из последнего снапшота и пишет отчёт об ошибке.

## Стек
- Python 3.11+, только стандартная библиотека (argparse, json, shutil, subprocess, time, pathlib)
- Никаких внешних зависимостей — чтобы работал даже тогда, когда окружение сломано

## Как запускать
```
python supervisor.py sniff      # что найдено: команда, cwd, skills, снапшот
python supervisor.py once       # один запуск
python supervisor.py run        # запуск с авто-восстановлением
python supervisor.py restore    # откат скиллов из свежего снапшота
python supervisor.py status     # последний отчёт
```

## Настройка
`config.json`:
- `command` — команда запуска Ауры (`[]` = авто-поиск main.py/run.py/app.py/aura.py)
- `skills_dir` — папка скиллов (`""` = найти автоматически)
- `max_restarts` — сколько раз пытаться поднять
- `healthy_seconds` — если процесс прожил меньше — считаем запуск неудачным
- `rollback_on_failure` — откатывать скиллы при неудачном запуске

## Тестирование
- `python supervisor.py sniff` — безопасная проверка без запуска
- `python supervisor.py restore --dry-run` — показать, что будет откачено

## Соглашения
- Отчёты только в `logs/`, снапшоты — в `skills/.auras_backups/`
- Не трогать чужие файлы вне `skills/` и `logs/`

## Что нельзя трогать
- `skills/.auras_backups/` вручную — только через `restore`
- `config.json` при запущенном `run` — читается один раз на старте
