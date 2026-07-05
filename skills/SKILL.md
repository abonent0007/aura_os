# SKILL.md — Как создать новый скилл

## 1. БЫСТРЫЙ ПУТЬ — build_skill (рекомендуется)
Вызови `build_skill("описание навыка")` — инструмент сам:
- Прочитает эту инструкцию + skills/README.md
- Отправит запрос в изолированный контейнер (без истории диалога)
- Сгенерирует manifest.json + skill.py + SKILL.md
- Сохранит файлы и загрузит инструменты
- Вернёт результат

**Используй build_skill ВСЕГДА для новых навыков.** Не пиши код вручную.

## 2. РУЧНОЙ ПУТЬ — edit_skill_file (для правок)
Если нужно подправить существующий навык:
1. `read_skill_file("name", "skill.py")` — прочитай текущий код
2. `edit_skill_file("name", "skill.py", content)` — сохрани изменения
3. `reload_skills()` — проверь что инструменты обновились
4. `system_health()` — проверь что нет ошибок

## 3. СТРУКТУРА
```
my_skill/
├── manifest.json    # метаданные
├── SKILL.md         # документация
└── skill.py         # код с @tools.tool
```
Все 3 файла обязательны.

## 4. skill.py — обязательно
```python
from autogen.beta import tools      # единственный правильный импорт

@tools.tool
def my_tool(param: str = "") -> str:
    """Описание."""
    return f"Результат: {param}"
```
- `from autogen.beta import tools` — **единственный** импорт
- Каждая функция → `@tools.tool` + возвращает `str`
- Храни данные в JSON: `Path(__file__).parent / "data.json"`

## 5. manifest.json
```json
{"name":"my-skill","version":"1.0.0","author":"AURA","description":"...","category":"tools","dependencies":[],"python_version":">=3.11","triggers":["..."],"permissions":[],"auto_created":true,"stability":"testing","created_at":"..."}
```

## 6. ЧЕК-ЛИСТ
```
[ ] from autogen.beta import tools — есть?
[ ] @tools.tool на каждой функции — есть?
[ ] return str — везде?
[ ] 3 файла созданы?
```
