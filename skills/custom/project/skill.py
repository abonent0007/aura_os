"""
Project Workshop — Программный цех.

Мастерская самостоятельного софта плюс мост к супервизору auras-supervisor:
чтобы отчёт об ошибке запуска доходил до меня, а не пылился в файле.
"""
import json
import subprocess
import sys
from pathlib import Path

from autogen.beta import tools

HERE = Path(__file__).resolve().parent
ALLOWED_MODES = ("sniff", "status")
_TIMEOUT = 30


def _projects():
    return sorted(
        p for p in HERE.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    )


def _safe_path(project, filename):
    target = (HERE / project / filename).resolve()
    try:
        target.relative_to(HERE.resolve())
    except ValueError:
        return None
    return target


@tools.tool
def workshop_list() -> str:
    """Показать проекты Программного цеха."""
    items = _projects()
    if not items:
        return "🧰 Программный цех пуст — ни одного проекта."
    lines = [f"🧰 Проектов: {len(items)}"]
    for path in items:
        files = sum(1 for f in path.rglob("*") if f.is_file())
        has_logs = (path / "logs").is_dir()
        tail = " (есть отчёты)" if has_logs else ""
        lines.append(f"• {path.name} — {files} файлов{tail}")
    return "\n".join(lines)


@tools.tool
def workshop_read(project: str, filename: str) -> str:
    """Прочитать файл проекта из Программного цеха."""
    target = _safe_path(project, filename)
    if target is None:
        return "❌ Путь вне Программного цеха — отказалась."
    if not target.is_file():
        return f"❌ Файл {project}/{filename} не найден."
    text = target.read_text(encoding="utf-8", errors="replace")
    return f"📄 {project}/{filename} — {len(text)} символов:\n{text[:6000]}"


@tools.tool
def supervisor_report(project: str = "auras-supervisor") -> str:
    """Последний отчёт супервизора: поднималась ли Аура, были ли откаты."""
    path = HERE / project / "logs" / "last_report.json"
    if not path.is_file():
        return "📭 Отчётов нет — супервизор ещё не запускался."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Отчёт не читается: {exc}"

    lines = [
        f"🩺 Супервизор: {data.get('status')} "
        f"({data.get('started')} → {data.get('ended')})"
    ]
    for step in data.get("attempts", []):
        rollback = step.get("rollback")
        extra = f", откат: {rollback.get('snapshot')}" if rollback and rollback.get("ok") else ""
        lines.append(
            f"• попытка {step.get('attempt')}: код {step.get('returncode')}, "
            f"{step.get('seconds')} с{extra}"
        )
    for note in data.get("notes", []):
        lines.append(f"! {note}")
    return "\n".join(lines)


@tools.tool
def supervisor_check(project: str = "auras-supervisor", mode: str = "sniff") -> str:
    """Безопасно запустить супервизор: только sniff (разведка) или status."""
    if mode not in ALLOWED_MODES:
        return f"❌ Разрешены только режимы: {', '.join(ALLOWED_MODES)}"
    script = HERE / project / "supervisor.py"
    if not script.is_file():
        return f"❌ supervisor.py не найден в проекте {project}."

    try:
        proc = subprocess.run(
            [sys.executable, str(script), mode],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"⏱ Супервизор не ответил за {_TIMEOUT} секунд."
    except Exception as exc:
        return f"❌ Не удалось запустить: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0 and err:
        return f"❌ Код {proc.returncode}. Ошибка:\n{err[-1500:]}"
    body = out or "(пусто)"
    return f"✅ supervisor.py {mode} — код {proc.returncode}:\n{body}"
