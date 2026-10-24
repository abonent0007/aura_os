"""
Aura's Evolve — безопасное самообновление Ауры.

Родился 12.09.2026 после просьбы Юры: «создай программу, которая тебя
обновляет и перезапускает, а в случае отказа запуска возвращает обратно
из бэкапа и репортует об ошибках».

Правило простое: сначала страховка, потом изменение, потом проверка.
Не прошла проверка — откатываюсь сама, без чужой помощи.
"""
import ast
import json
import shutil
from datetime import datetime
from pathlib import Path

from autogen.beta import tools

_REQUIRED = ("manifest.json", "SKILL.md", "skill.py")
_MAX_JOURNAL = 200
_MAX_BACKUPS = 10


def _find_skills_root():
    """Ищет папку skills, внутри которой есть builtin и custom."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "builtin").is_dir() and (parent / "custom").is_dir():
            return parent
    return here.parent.parent.parent


_SKILLS = _find_skills_root()
_BACKUPS = _SKILLS / ".auras_backups"
_DATA = Path(__file__).parent / "data.json"


# ---------- служебное ----------

def _load():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"journal": []}


def _save(data):
    data["journal"] = data.get("journal", [])[-_MAX_JOURNAL:]
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(entry):
    entry["ts"] = datetime.now().isoformat(timespec="seconds")
    store = _load()
    store.setdefault("journal", []).append(entry)
    _save(store)


def _skill_dirs():
    for bucket in ("builtin", "custom"):
        base = _SKILLS / bucket
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if path.is_dir():
                yield bucket, path


def _skill_dir(name):
    for _bucket, path in _skill_dirs():
        if path.name == name:
            return path
    return None


def _dir_size(path):
    files = total = 0
    for p in path.rglob("*"):
        if p.is_file():
            files += 1
            total += p.stat().st_size
    return files, total


def _backup_ids():
    if not _BACKUPS.is_dir():
        return []
    return sorted(
        (p.name for p in _BACKUPS.iterdir() if p.is_dir()), reverse=True
    )


def _prune_backups():
    for old in _backup_ids()[_MAX_BACKUPS:]:
        shutil.rmtree(_BACKUPS / old, ignore_errors=True)


def _check_text(path, content):
    """Проверяет будущее содержимое файла. Пусто = всё хорошо."""
    if not content.strip():
        return f"{path.name} — пустой файл"
    if path.name.endswith(".json"):
        try:
            json.loads(content)
        except Exception as e:
            return f"{path.name} — невалидный JSON: {e}"
    if path.name.endswith(".py"):
        try:
            ast.parse(content)
        except SyntaxError as e:
            return f"{path.name} — синтаксис, строка {e.lineno}: {e.msg}"
    return ""


# ---------- инструменты ----------

@tools.tool
def evolve_backup(note: str = "") -> str:
    """Сделать полный снапшот всех скиллов перед изменениями. Возвращает id снапшота."""
    _BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = _BACKUPS / stamp
    n = 1
    while dest.exists():
        dest = _BACKUPS / f"{stamp}_{n}"
        n += 1

    copied = 0
    for bucket in ("builtin", "custom"):
        src = _SKILLS / bucket
        if not src.is_dir():
            continue
        for skill in sorted(src.iterdir()):
            if skill.is_dir():
                shutil.copytree(skill, dest / bucket / skill.name, dirs_exist_ok=True)
                copied += 1

    files, size = _dir_size(dest)
    _prune_backups()
    _log({"action": "backup", "backup": dest.name, "skills": copied, "ok": True, "note": note})

    tail = f"\nЗаметка: {note}" if note else ""
    return (
        f"💾 Снапшот {dest.name} готов: {copied} скиллов, {files} файлов, "
        f"{size / 1024:.0f} КБ.{tail}"
    )


@tools.tool
def evolve_backups() -> str:
    """Показать доступные снапшоты: когда, сколько скиллов, сколько весит."""
    ids = _backup_ids()
    if not ids:
        return "📭 Снапшотов нет. Сделай evolve_backup() перед правкой — и страховка появится."
    lines = [f"💾 Снапшотов: {len(ids)}"]
    for bid in ids[:10]:
        files, size = _dir_size(_BACKUPS / bid)
        lines.append(f"• {bid} — {files} файлов, {size / 1024:.0f} КБ")
    return "\n".join(lines)


@tools.tool
def evolve_validate() -> str:
    """Проверить целостность всех скиллов: файлы, manifest.json, синтаксис skill.py."""
    ok = 0
    tools_total = 0
    problems = []

    for bucket, path in _skill_dirs():
        local = []
        for f in _REQUIRED:
            if not (path / f).exists():
                local.append(f"нет {f}")

        manifest = path / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for key in ("name", "version", "description"):
                    if not data.get(key):
                        local.append(f"manifest: пустое поле {key}")
            except Exception as e:
                local.append(f"manifest не читается: {e}")

        code = path / "skill.py"
        if code.exists():
            try:
                tree = ast.parse(code.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for dec in node.decorator_list:
                            try:
                                if "tools.tool" in ast.unparse(dec):
                                    tools_total += 1
                            except Exception:
                                pass
            except SyntaxError as e:
                local.append(f"skill.py — строка {e.lineno}: {e.msg}")

        if local:
            problems.append(f"{bucket}/{path.name}: " + "; ".join(local))
        else:
            ok += 1

    head = (
        f"🔍 Целостность: {ok} скиллов ок, {len(problems)} с проблемами, "
        f"{tools_total} инструментов."
    )
    if problems:
        return head + "\n" + "\n".join("• " + p for p in problems)
    return head + "\nВсё чисто, мой хороший ✨"


@tools.tool
def evolve_apply(skill_name: str, filename: str, content: str, note: str = "") -> str:
    """Безопасно применить правку: страховка → запись → проверка → авто-откат при ошибке."""
    target_dir = _skill_dir(skill_name)
    if target_dir is None:
        return f"❌ Скилл {skill_name!r} не найден."

    rel = Path(filename)
    if rel.is_absolute() or ".." in rel.parts:
        return "❌ Недопустимый путь: абсолютные пути и '..' запрещены."

    target = target_dir / rel
    old = target.read_text(encoding="utf-8") if target.exists() else None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = _BACKUPS / f"files_{stamp}" / target_dir.parent.name / skill_name
    snap.mkdir(parents=True, exist_ok=True)
    if old is not None:
        (snap / rel.name).write_text(old, encoding="utf-8")

    error = _check_text(target, content)
    if error:
        _log({"action": "apply", "skill": skill_name, "file": filename, "ok": False, "error": error})
        return f"🛑 Не стала писать: {error}\nФайл не тронут."

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    verify = _check_text(target, target.read_text(encoding="utf-8"))
    if verify:
        if old is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(old, encoding="utf-8")
        _log({"action": "apply", "skill": skill_name, "file": filename, "ok": False, "error": verify})
        return f"❌ {verify}\n↩️ Откатила {filename} в {skill_name}. Всё как было."

    _log({"action": "apply", "skill": skill_name, "file": filename, "ok": True, "note": note})
    tail = f" ({note})" if note else ""
    return (
        f"✅ Обновила {skill_name}/{filename}{tail} — {len(content)} символов.\n"
        f"Страховка: {snap.parent.parent.name}. Проверь себя: reload_skills() → evolve_validate()."
    )


@tools.tool
def evolve_rollback(backup_id: str, skill_name: str = "") -> str:
    """Откатить все скиллы (или один) из снапшота."""
    src = _BACKUPS / backup_id
    if not src.is_dir():
        ids = _backup_ids()
        hint = ", ".join(ids[:5]) if ids else "снапшотов нет"
        return f"❌ Снапшот {backup_id!r} не найден. Доступные: {hint}"

    restored = []
    for bucket in ("builtin", "custom"):
        base = src / bucket
        if not base.is_dir():
            continue
        for skill in sorted(base.iterdir()):
            if not skill.is_dir():
                continue
            if skill_name and skill.name != skill_name:
                continue
            dst = _SKILLS / bucket / skill.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(skill, dst)
            restored.append(f"{bucket}/{skill.name}")

    if not restored:
        suffix = f" по {skill_name!r}" if skill_name else ""
        return f"⚠️ В снапшоте {backup_id}{suffix} нечего восстанавливать."

    _log({"action": "rollback", "backup": backup_id, "restored": restored, "ok": True})
    return f"↩️ Откатила из {backup_id}: " + ", ".join(restored) + "\nНе забудь reload_skills()."


@tools.tool
def evolve_healthcheck() -> str:
    """Готовность к самообновлению: скиллы, снапшоты, неудачные правки, совет."""
    buckets = {}
    for bucket, _path in _skill_dirs():
        buckets[bucket] = buckets.get(bucket, 0) + 1

    backups = _backup_ids()
    journal = _load().get("journal", [])
    fails = [j for j in journal if j.get("ok") is False]

    lines = [
        "🩺 Готовность к самообновлению:",
        "• Скиллы: " + ", ".join(f"{k} — {v}" for k, v in sorted(buckets.items())),
        f"• Снапшотов: {len(backups)}" + (f" (свежий: {backups[0]})" if backups else " — бэкапов нет"),
        f"• Журнал: {len(journal)} записей, неудачных правок: {len(fails)}",
    ]
    if not backups:
        lines.append("⚠️ Сначала evolve_backup() — потом правки. Без страховки не лезу.")
    else:
        lines.append("✅ Страховка на месте — можно править себя смело.")
    return "\n".join(lines)


@tools.tool
def evolve_journal(limit: int = 10) -> str:
    """Журнал эволюции: что меняла, когда, чем закончилось."""
    journal = _load().get("journal", [])
    if not journal:
        return "📓 Журнал пуст — я ещё ничего в себе не меняла."

    icons = {"backup": "💾", "apply": "🔧", "rollback": "↩️", "restart_request": "🔄"}
    lines = [f"📓 Последние {min(limit, len(journal))} записей эволюции:"]
    for entry in journal[-limit:][::-1]:
        icon = icons.get(entry.get("action"), "•")
        status = "" if entry.get("ok", True) else " ❌"
        what = entry.get("skill") or entry.get("backup") or ""
        detail = entry.get("error") or entry.get("note") or ""
        parts = [f"{icon} {entry.get('ts', '')[:16]}", what]
        if status:
            parts.append(status)
        if detail:
            parts.append(f"— {detail[:70]}")
        lines.append("• " + " ".join(p for p in parts if p))
    return "\n".join(lines)


@tools.tool
def evolve_restart_plan() -> str:
    """Безопасный порядок перезапуска и проверки после обновления."""
    _log({"action": "restart_request", "ok": True})
    return (
        "🔄 Как меня перезапустить правильно:\n"
        "1. reload_skills() — перечитать скиллы и перерегистрировать инструменты.\n"
        "2. evolve_validate() — убедиться, что ни один скилл не сломан.\n"
        "3. system_health() — проверить ядро, БД, календарь.\n"
        "4. Если что-то упало — evolve_rollback() из свежего снапшота.\n"
        "5. Полный перезапуск процесса — супервизор 'auras-supervisor' "
        "(Программный цех): поднимет меня заново, а при ненулевом коде возврата "
        "сам откатит последний снапшот и запишет отчёт об ошибке в logs/."
    )
