# AURA Skills System

Открытая система скиллов. Нейросеть может самостоятельно расширять возможности Ауры.

## Структура скилла

```
my_skill/
├── manifest.json    # Метаданные
├── SKILL.md         # Документация
└── skill.py         # Код с @tools.tool
```

## manifest.json

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "author": "AURA OS",
  "description": "Что делает скилл",
  "category": "tools",
  "dependencies": [],
  "triggers": ["ключевые", "слова"],
  "permissions": ["network"],
  "auto_created": true,
  "stability": "testing"
}
```

## Как создаются скиллы

1. Пользователь: «Аура, создай скилл для...»
2. Skill Builder (LLM) генерирует manifest + SKILL.md + skill.py
3. Валидация → тест в песочнице → интеграция
4. До 3 попыток с авто-исправлением ошибок
5. При провале — откат

## Установленные скиллы

| Скилл | Инструменты | Описание |
|---|---|---|
| `calendar_skill` | 6 | Даты, повторения, недели |
| `web_search_skill` | 2 | Поиск в интернете |
| `content-sanitizer` | 2 | Очистка чувствительных данных |
| `persona-extractor` | 2 | Извлечение портрета пользователя |
| `session-analyzer` | 2 | Анализ сессий диалога |
| `url-content-fetcher` | 2 | Захват содержимого по URL |
| `moex_stock_tracker` | 5 | Акции MOEX + MACD |
| `kazan_direction_trains` | 3 | Расписание электричек |
