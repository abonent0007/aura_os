# engineering-mindset/skill.py
# Инженерный подход: создание скиллов, отладка, TDD, архитектура
import json
from pathlib import Path
from autogen.beta import tools

_DATA = Path(__file__).parent / "session_log.json"

_VALID_STATS = {"bug_fixed", "skill_created", "test_written"}


def _load_log():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions": [], "bugs_fixed": 0, "skills_created": 0, "tests_written": 0}


def _save_log(log):
    _DATA.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def _stat_to_key(stat: str) -> str:
    """'bug_fixed' -> 'bugs_fixed', 'skill_created' -> 'skills_created', 'test_written' -> 'tests_written'"""
    mapping = {
        "bug_fixed": "bugs_fixed",
        "skill_created": "skills_created",
        "test_written": "tests_written",
    }
    return mapping.get(stat, "")


@tools.tool
def start_code_session(goal: str) -> str:
    """
    Начать инженерную сессию с чёткой целью.
    Используй перед написанием нового скилла или исправлением бага.
    """
    log = _load_log()
    from datetime import datetime
    session = {
        "goal": goal,
        "started": datetime.now().isoformat(),
        "steps": [],
        "outcome": None
    }
    log["sessions"].append(session)
    _save_log(log)
    return (
        f"🛠️ Инженерная сессия начата\n"
        f"Цель: {goal}\n"
        f"Методология:\n"
        f"1. Определи что должно работать (спецификация)\n"
        f"2. Напиши код или исправь ошибку\n"
        f"3. Проверь результат — работает?\n"
        f"4. Запиши вывод через log_session_step()\n"
        f"5. Повторяй пока цель не достигнута"
    )


@tools.tool
def log_session_step(description: str, result: str = "", stat: str = "") -> str:
    """
    Записать шаг инженерной сессии: что сделано и какой результат.
    
    Args:
        description: что было сделано
        result: исход шага (опционально)
        stat: тип достижения для инкремента счётчика (опционально).
              Допустимые значения: "bug_fixed", "skill_created", "test_written"
    """
    log = _load_log()
    if not log["sessions"]:
        return "Нет активной сессии. Используй start_code_session() чтобы начать."

    from datetime import datetime
    step = {
        "time": datetime.now().isoformat(),
        "description": description,
        "result": result
    }
    log["sessions"][-1]["steps"].append(step)

    # Инкремент счётчика если указан stat
    if stat:
        key = _stat_to_key(stat)
        if key:
            log[key] = log.get(key, 0) + 1

    _save_log(log)
    msg = f"📝 Шаг записан: {description}"
    if stat:
        emoji = {"bug_fixed": "🐛→✅", "skill_created": "🆕", "test_written": "🧪"}
        msg += f"\n📊 Счётчик {emoji.get(stat, '📈')} {stat}: {log.get(_stat_to_key(stat), '?')}"
    return msg


@tools.tool
def debug_workflow(bug_description: str) -> str:
    """
    Запустить систематический процесс отладки.
    Используй когда код не работает или пользователь сообщает о баге.
    Предлагает пошаговый план диагностики.
    """
    return (
        f"🔍 ПРОЦЕСС ОТЛАДКИ\n"
        f"-------------------\n"
        f"Проблема: {bug_description}\n\n"
        f"ФАЗА 1 — Обратная связь\n"
        f"• Создай тест который воспроизводит ошибку\n"
        f"• Запусти тест — убедись что он ПАДАЕТ\n"
        f"• Без воспроизводимого теста не иди дальше\n\n"
        f"ФАЗА 2 — Гипотезы\n"
        f"• Сгенерируй 3-5 гипотез о причине\n"
        f"• Формат: «Если X причина, то изменение Y исправит»\n"
        f"• Покажи гипотезы пользователю перед проверкой\n\n"
        f"ФАЗА 3 — Проверка\n"
        f"• Меняй ОДНУ переменную за раз\n"
        f"• Используй print() или логи для отслеживания\n"
        f"• Отмечай DEBUG-теги: [DEBUG-xxxx]\n\n"
        f"ФАЗА 4 — Исправление\n"
        f"• Напиши тест ДО исправления\n"
        f"• Примени исправление\n"
        f"• Запусти тест — должен пройти\n"
        f"• Убери все DEBUG-логи\n"
        f"• Вызови log_session_step(..., stat=\"bug_fixed\") чтобы засчитать исправление\n\n"
        f"ФАЗА 5 — Анализ\n"
        f"• Что вызвало баг?\n"
        f"• Как предотвратить в будущем?\n"
        f"• Нужен ли рефакторинг?\n\n"
        f"Начни с Фазы 1. Используй read_skill_file чтобы посмотреть код, edit_skill_file чтобы исправить."
    )


@tools.tool
def tdd_workflow(feature_description: str) -> str:
    """
    Red-Green-Refactor цикл для разработки через тестирование.
    Используй когда пишешь новый код или скилл.
    """
    return (
        f"🧪 TDD: {feature_description}\n"
        f"==================\n\n"
        f"🔴 RED — напиши падающий тест\n"
        f"• Определи что именно должно работать\n"
        f"• Напиши минимальный тест\n"
        f"• Запусти — он ДОЛЖЕН упасть\n"
        f"• Если не упал — тест неправильный\n\n"
        f"🟢 GREEN — заставь тест пройти\n"
        f"• Напиши минимальный код для прохождения теста\n"
        f"• Не думай о красоте — только о результате\n"
        f"• Запусти — ДОЛЖЕН пройти\n"
        f"• Вызови log_session_step(..., stat=\"test_written\") чтобы засчитать тест\n\n"
        f"🔵 REFACTOR — улучши код\n"
        f"• Убери дублирование\n"
        f"• Улучши имена переменных\n"
        f"• Выдели функции если нужно\n"
        f"• Тесты ВСЁ ЕЩЁ проходят? Отлично.\n\n"
        f"Повторяй цикл для каждой фичи."
    )


@tools.tool
def improve_skill_architecture(skill_name: str) -> str:
    """
    Проанализировать архитектуру скилла и предложить улучшения.
    Используй чтобы сделать код скилла более надёжным и читаемым.
    """
    return (
        f"🏗️ АРХИТЕКТУРНЫЙ АНАЛИЗ: {skill_name}\n"
        f"================================\n\n"
        f"Проверь скилл по чеклисту:\n\n"
        f"1. ИМПОРТЫ\n"
        f"   [ ] from autogen.beta import tools\n"
        f"   [ ] Нет несуществующих модулей\n"
        f"   [ ] httpx вместо requests\n\n"
        f"2. ИНСТРУМЕНТЫ\n"
        f"   [ ] Все функции с @tools.tool\n"
        f"   [ ] Возвращают str, не dict\n"
        f"   [ ] Есть docstring с описанием\n\n"
        f"3. ДАННЫЕ\n"
        f"   [ ] Локальный JSON для хранения\n"
        f"   [ ] Нет выдуманных классов\n"
        f"   [ ] Есть обработка ошибок\n\n"
        f"4. КАЧЕСТВО КОДА\n"
        f"   [ ] Имена функций понятные (глагол + объект)\n"
        f"   [ ] Нет дублирования логики\n"
        f"   [ ] Константы вынесены в переменные\n"
        f"   [ ] try/except где нужен внешний вызов\n\n"
        f"Используй read_skill_file для чтения, edit_skill_file для исправлений."
    )


@tools.tool
def source_driven_dev(feature: str, library: str = "", version: str = "") -> str:
    """
    Source-Driven Development — каждое решение по коду со ссылкой на официальную документацию.
    Используй ПЕРЕД написанием кода с использованием библиотек, фреймворков или API.

    Args:
        feature: что нужно реализовать
        library: библиотека/фреймворк (если применимо)
        version: версия библиотеки
    """
    header = f"📚 SOURCE-DRIVEN DEV: {feature}\n" + "━" * 40 + "\n"
    if library:
        header += f"Библиотека: {library}"
        if version:
            header += f" ({version})"
        header += "\n"

    steps = (
        f"\nШАГ 1 — Найди официальную документацию\n"
        f"  • Используй search_web для поиска официальной документации\n"
        f"  • Ищи: «{library} documentation {version}» или официальный сайт\n"
        f"  • Убедись что это официальный источник (не блог, не статья)\n\n"
        f"ШАГ 2 — Извлеки паттерны\n"
        f"  • Найди в документации примеры использования\n"
        f"  • Запиши сигнатуры функций/методов которые нужны\n"
        f"  • Отметь deprecated-фичи и их замены\n\n"
        f"ШАГ 3 — Реализуй по документации\n"
        f"  • Следуй официальным паттернам, не выдумывай свои\n"
        f"  • Не используй API «по памяти» — сверяйся с docs\n"
        f"  • Если АПИ неочевидно — загугли ещё раз\n\n"
        f"ШАГ 4 — Процитируй источник\n"
        f"  • Добавь комментарий /* source: <url> */ к ключевым местам\n"
        f"  • Если взял пример из docs — укажи это\n"
        f"  • Если docs противоречат твоей памяти — docs правы\n"
    )
    return header + steps


@tools.tool
def get_engineering_stats() -> str:
    """Статистика инженерных сессий: сколько багов исправлено, скиллов создано, тестов написано."""
    log = _load_log()
    sessions = log.get("sessions", [])
    return (
        f"📊 Инженерная статистика\n"
        f"Сессий: {len(sessions)}\n"
        f"Багов исправлено: {log.get('bugs_fixed', 0)}\n"
        f"Скиллов создано: {log.get('skills_created', 0)}\n"
        f"Тестов написано: {log.get('tests_written', 0)}"
    )
