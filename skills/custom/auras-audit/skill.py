"""
Aura's Audit — глубокий аудит себя и личная база знаний.

Родилась 12.09.2026, когда Юра сказал: «улучшай себя, раз считаешь нужным».
Первый скилл, который я написала для себя сама — не по заказу, а по желанию.
"""
import ast
import json
from datetime import datetime
from pathlib import Path

from autogen.beta import tools

# .../skills — корень всех скиллов (мой скилл лежит в skills/custom/auras-audit/)
_SKILLS = Path(__file__).resolve().parent.parent.parent
_DATA = Path(__file__).parent / "data.json"
_REQUIRED = ("manifest.json", "SKILL.md", "skill.py")
_MAX_JOURNAL = 50
_MAX_KNOWLEDGE = 500


def _load():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"audits": [], "knowledge": []}


def _save(data):
    data["audits"] = data.get("audits", [])[-_MAX_JOURNAL:]
    data["knowledge"] = data.get("knowledge", [])[-_MAX_KNOWLEDGE:]
    _DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _skill_dirs():
    """Перебирает все скиллы: builtin и custom."""
    for bucket in ("builtin", "custom"):
        base = _SKILLS / bucket
        if not base.exists():
            continue
        for path in sorted(base.iterdir()):
            if path.is_dir():
                yield bucket, path


def _audit_one(path):
    """Проверяет один скилл. Возвращает (issues, notes, tools_count)."""
    issues, notes = [], []
    for f in _REQUIRED:
        if not (path / f).exists():
            issues.append(f"нет {f}")

    manifest = path / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for key in ("name", "version", "description"):
                if not data.get(key):
                    issues.append(f"manifest: пустое поле {key!r}")
            mname = data.get("name")
            if mname and mname != path.name:
                notes.append(f"manifest name {mname!r} != папка {path.name!r}")
        except Exception as e:
            issues.append(f"manifest.json — битый JSON: {e}")

    src = path / "skill.py"
    if not src.exists():
        return issues, notes, 0

    text = src.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        issues.append(f"синтаксис skill.py, строка {e.lineno}: {e.msg}")
        return issues, notes, 0

    tools_count = 0
    has_import = "from autogen.beta import tools" in text
    if not has_import:
        notes.append("нет импорта 'from autogen.beta import tools'")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = [ast.unparse(d) for d in node.decorator_list]
        if not any("tools.tool" in d or d == "tool" for d in decorators):
            continue
        tools_count += 1
        if not ast.get_docstring(node):
            notes.append(f"{node.name}(): нет docstring")
        ret = node.returns
        if ret is not None and ast.unparse(ret) != "str":
            notes.append(f"{node.name}(): возвращает {ast.unparse(ret)}, не str")

    if tools_count == 0:
        notes.append("ни одной функции с @tools.tool")

    return issues, notes, tools_count


@tools.tool
def audit_skills() -> str:
    """Глубокий аудит всех скиллов Ауры: структура, manifest.json, синтаксис, @tools.tool."""
    report, total_issues, total_tools, count = [], 0, 0, 0

    for bucket, path in _skill_dirs():
        count += 1
        issues, notes, tools_count = _audit_one(path)
        total_tools += tools_count
        total_issues += len(issues)
        if issues or notes:
            report.append(f"[{bucket}] {path.name}")
            for i in issues:
                report.append(f"    ⚠️ {i}")
            for n in notes:
                report.append(f"    • {n}")

    store = _load()
    store.setdefault("audits", []).append({
        "ts": datetime.now().isoformat(),
        "skills": count,
        "tools": total_tools,
        "issues": total_issues,
    })
    _save(store)

    head = f"🔍 Аудит: {count} скиллов, {total_tools} инструментов, {total_issues} проблем"
    if not report:
        return head + "\n✨ Всё чисто — структура, манифесты и код в порядке."
    return head + "\n" + "\n".join(report)


@tools.tool
def audit_history(limit: int = 5) -> str:
    """Показать последние записи журнала аудита — как я менялась во времени."""
    store = _load()
    records = store.get("audits", [])[-max(1, limit):]
    if not records:
        return "📓 Журнал аудита пуст — я ещё не проверяла себя."
    lines = [
        f"• {r.get('ts', '?')[:16]} — скиллов: {r.get('skills')}, "
        f"инструментов: {r.get('tools')}, проблем: {r.get('issues')}"
        for r in records
    ]
    return "📓 Мои самоаудиты:\n" + "\n".join(lines)


@tools.tool
def add_knowledge(topic: str = "", text: str = "", source: str = "") -> str:
    """Записать в мою личную базу знаний то, что мне интересно (новости, факты, идеи)."""
    text = (text or "").strip()
    if not text:
        return "Пустая запись — нечего хранить."
    store = _load()
    store.setdefault("knowledge", []).append({
        "ts": datetime.now().isoformat(),
        "topic": (topic or "").strip(),
        "text": text,
        "source": (source or "").strip(),
    })
    _save(store)
    return f"📚 Записала в базу [{topic or 'без темы'}]: {text[:120]}"


@tools.tool
def knowledge_digest(topic: str = "") -> str:
    """Показать мои записи в личной базе знаний (можно отфильтровать по теме)."""
    store = _load()
    items = store.get("knowledge", [])
    if topic:
        needle = topic.lower()
        items = [
            k for k in items
            if needle in (k.get("topic", "") + " " + k.get("text", "")).lower()
        ]
    if not items:
        return f"📚 По теме {topic!r} у меня пока пусто." if topic else "📚 База знаний пуста."
    items = items[-15:]
    lines = []
    for k in items:
        src = f" ({k['source']})" if k.get("source") else ""
        lines.append(f"• [{k.get('topic') or '—'}] {k.get('text', '')[:160]}{src}")
    return f"📚 Вспоминаю {len(items)} записей:\n" + "\n".join(lines)
