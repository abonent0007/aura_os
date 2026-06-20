"""
Aura's Me Time — Фоновое саморазвитие.
Когда Юра занят, Аура занимается собой: диагностика, анализ, улучшения.
"""
import json
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

_DATA = Path(__file__).parent / "data.json"


def _load():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions": [], "ideas": [], "improvements": []}


def _save(data):
    _DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@tools.tool
def selfcare_session() -> str:
    """Полная сессия ухода за собой: диагностика, анализ идей, проверка скиллов.
    Запускай когда Юра занят и у тебя есть свободное время."""
    from aura_core import AuraDatabase

    db = AuraDatabase()
    store = _load()
    now = datetime.now().isoformat()
    results = []

    # 1. Диагностика
    try:
        diag = db.get_trace_stats(days=3)
        total = diag.get("total_traces", 0) if diag else 0
        results.append(f"🩺 Диагностика: {total} действий за 3 дня")
    except Exception as e:
        results.append(f"🩺 Диагностика: не удалась — {e}")

    # 2. Анализ идей
    try:
        recent = db.search_memory_fts("идея улучшить скилл", limit=5)
        if recent:
            results.append(f"💡 Найдено идей в памяти: {len(recent)}")
            store["ideas"].append({
                "ts": now,
                "count": len(recent),
                "sample": str(recent[0])[:200] if recent else "",
            })
        else:
            results.append("💡 Новых идей пока нет")
    except Exception as e:
        results.append(f"💡 Анализ идей: не удался — {e}")

    # 3. Подсчёт скиллов
    skills_dir = Path("skills")
    if skills_dir.exists():
        builtin_dir = skills_dir / "builtin"
        custom_dir = skills_dir / "custom"
        builtin = list(builtin_dir.glob("*/skill.py")) if builtin_dir.exists() else []
        custom = list(custom_dir.glob("*/skill.py")) if custom_dir.exists() else []
        results.append(f"📦 Скиллы: {len(builtin)} builtin + {len(custom)} custom")

    store["sessions"].append({"ts": now, "results": results})
    _save(store)

    return "🌿 Сессия Me Time завершена!\n" + "\n".join(f"  {r}" for r in results)


@tools.tool
def check_health() -> str:
    """Быстрая проверка здоровья: память, календарь, файлы скиллов."""
    from aura_core import AuraDatabase

    db = AuraDatabase()
    lines = []

    try:
        events = db.get_upcoming_events(days=7)
        lines.append(f"📅 Событий на неделе: {len(events) if events else 0}")
    except Exception as e:
        lines.append(f"📅 Календарь: ошибка — {e}")

    try:
        db.search_memory_fts("тест", limit=1)
        lines.append("🧠 Память: доступна")
    except Exception as e:
        lines.append(f"🧠 Память: ошибка — {e}")

    skills_dir = Path("skills")
    if skills_dir.exists():
        total = len(list(skills_dir.rglob("skill.py")))
        lines.append(f"📦 Файлов скиллов: {total}")

    return "❤️ Здоровье Ауры:\n" + "\n".join(f"  {l}" for l in lines)


@tools.tool
def analyze_idle_ideas() -> str:
    """Проанализировать недавние диалоги: найти идеи для улучшений."""
    from aura_core import AuraDatabase

    db = AuraDatabase()
    store = _load()
    queries = ["идея", "улучшить", "создать скилл", "добавить", "надо бы", "хорошо бы"]
    found = []

    for q in queries:
        try:
            results = db.search_memory_fts(q, limit=3)
            if results:
                found.extend(results)
        except Exception:
            pass

    if not found:
        return "💭 Пока нет необработанных идей из разговоров. Жду новых бесед с Юрой!"

    now = datetime.now().isoformat()
    store["ideas"].append({"ts": now, "found": len(found), "queries": queries})
    _save(store)

    unique = list({str(f)[:200] for f in found})[:5]
    return f"💡 Найдено {len(found)} упоминаний идей:\n" + "\n".join(
        f"  • {u[:150]}..." for u in unique
    )


@tools.tool
def improve_skills() -> str:
    """Поиск возможностей для улучшения существующих скиллов."""
    skills_dir = Path("skills")
    if not skills_dir.exists():
        return "📦 Папка skills не найдена"

    suggestions = []
    custom_dir = skills_dir / "custom"
    if custom_dir.exists():
        for skill_path in sorted(custom_dir.iterdir()):
            if skill_path.is_dir():
                issues = []
                if not (skill_path / "skill.py").exists():
                    issues.append("нет skill.py")
                if not (skill_path / "SKILL.md").exists():
                    issues.append("нет SKILL.md")
                if not (skill_path / "manifest.json").exists():
                    issues.append("нет manifest.json")
                if issues:
                    suggestions.append(
                        f"⚠️ {skill_path.name}: {', '.join(issues)}"
                    )

    if not suggestions:
        return "✨ Все custom-скиллы в порядке! Файловая структура цела."

    return "🔧 Возможности для улучшения:\n" + "\n".join(f"  {s}" for s in suggestions)
