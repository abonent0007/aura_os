#!/usr/bin/env python3
"""
auras-supervisor — запуск, надзор и авто-восстановление Ауры.

Зачем: скилл auras-evolve умеет править меня и откатывать правку,
но он живёт ВНУТРИ меня. Если я не поднимусь после обновления —
никто не откатит. Значит, нужен наблюдатель снаружи.

Что делает:
  * запускает ядро Ауры командой из config.json;
  * если процесс упал (ненулевой код возврата) быстро — считает запуск неудачным;
  * откатывает скиллы из последнего снапшота skills/.auras_backups/<stamp>;
  * пишет отчёт (JSON + текстовый лог) в logs/;
  * перезапускает повторно, до max_restarts раз.

Использование:
  python supervisor.py sniff      # найти точку входа и показать, что нашёл
  python supervisor.py once       # один запуск без надзора
  python supervisor.py run        # запуск с авто-восстановлением
  python supervisor.py restore    # откатить скиллы из последнего снапшота
  python supervisor.py status     # показать последний отчёт

Зависимости: только стандартная библиотека Python 3.11+.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
LOGS_DIR = HERE / "logs"

DEFAULTS = {
    "command": [],
    "cwd": "",
    "skills_dir": "",
    "max_restarts": 3,
    "restart_delay": 5,
    "healthy_seconds": 30,
    "rollback_on_failure": True,
}

ENTRY_POINTS = ("main.py", "run.py", "app.py", "aura.py", "start.py")


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"[supervisor] config.json не читается: {exc}")
    return cfg


def guess_skills_dir():
    for parent in [HERE, *HERE.parents]:
        cand = parent / "skills"
        if cand.is_dir() and (cand / "builtin").is_dir():
            return cand
    return None


def guess_command():
    """Пытается найти точку входа Ауры рядом с папкой skills."""
    skills = guess_skills_dir()
    root = skills.parent if skills else HERE.parent.parent
    for name in ENTRY_POINTS:
        if (root / name).is_file():
            return [sys.executable, str(root / name)], str(root)
    return [], ""


def latest_backup(skills_dir):
    backups = skills_dir / ".auras_backups"
    if not backups.is_dir():
        return None
    stamps = sorted(p for p in backups.iterdir() if p.is_dir() and not p.name.startswith("files_"))
    return stamps[-1] if stamps else None


def restore(skills_dir, stamp="", dry=False):
    """Возвращает скиллы из снапшота."""
    snap = Path(stamp) if stamp else latest_backup(skills_dir)
    if not snap or not snap.is_dir():
        return {"ok": False, "error": "снапшот не найден", "skills_dir": str(skills_dir)}

    restored = []
    for bucket in ("builtin", "custom"):
        base = snap / bucket
        if not base.is_dir():
            continue
        for skill in sorted(base.iterdir()):
            if not skill.is_dir():
                continue
            dst = skills_dir / bucket / skill.name
            restored.append(f"{bucket}/{skill.name}")
            if not dry:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(skill, dst)
    return {"ok": True, "snapshot": snap.name, "restored": restored, "dry": dry}


def write_report(report):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (LOGS_DIR / f"supervisor_{stamp}.json").write_text(payload, encoding="utf-8")
    (LOGS_DIR / "last_report.json").write_text(payload, encoding="utf-8")

    lines = [f"=== {report.get('started')} → {report.get('ended')} ===",
             f"статус: {report.get('status')}",
             f"команда: {' '.join(report.get('command') or []) or '—'}"]
    for step in report.get("attempts", []):
        line = (f"  попытка {step['attempt']}: код {step['returncode']}, "
                f"прожил {step['seconds']} с")
        if step.get("rollback"):
            rb = step["rollback"]
            line += f", откат: {'из ' + rb['snapshot'] if rb.get('ok') else 'не удался'}"
        lines.append(line)
    if report.get("notes"):
        lines.extend(f"  ! {n}" for n in report["notes"])
    text = "\n".join(lines) + "\n"
    with (LOGS_DIR / "supervisor.log").open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return text


def run_once(cfg):
    cmd = cfg["command"] or guess_command()[0]
    if not cmd:
        return {"ok": False, "error": "команда запуска не найдена — заполни config.json"}
    cwd = cfg["cwd"] or None
    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd)
    lived = round(time.time() - t0, 1)
    report = {
        "started": started,
        "ended": datetime.now().isoformat(timespec="seconds"),
        "status": "ok" if proc.returncode == 0 else "failed",
        "command": cmd,
        "attempts": [{"attempt": 1, "returncode": proc.returncode, "seconds": lived}],
    }
    write_report(report)
    return report


def run_supervised(cfg):
    cmd = cfg["command"]
    cwd = cfg["cwd"] or None
    notes = []

    if not cmd:
        discovered, guess_cwd = guess_command()
        if not discovered:
            return {"status": "config_error", "notes": [
                "Не нашла точку входа (main.py/run.py/app.py/aura.py).",
                "Впиши точную команду запуска в config.json — блок 'command'.",
            ], "attempts": []}
        cmd, cwd = discovered, cwd or guess_cwd
        notes.append(f"команда найдена автоматически: {' '.join(cmd)}")

    skills_dir = Path(cfg["skills_dir"]) if cfg["skills_dir"] else guess_skills_dir()
    if skills_dir and not (skills_dir / ".auras_backups").is_dir():
        notes.append("снапшотов нет — откатываться будет некуда, сделай evolve_backup()")

    report = {
        "started": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "command": cmd,
        "attempts": [],
        "notes": notes,
    }

    for attempt in range(1, int(cfg["max_restarts"]) + 1):
        t0 = time.time()
        proc = subprocess.run(cmd, cwd=cwd)
        lived = round(time.time() - t0, 1)
        step = {"attempt": attempt, "returncode": proc.returncode, "seconds": lived}

        if proc.returncode != 0 and lived < float(cfg["healthy_seconds"]):
            step["verdict"] = "crash"
            if cfg.get("rollback_on_failure") and skills_dir:
                step["rollback"] = restore(skills_dir)
        elif proc.returncode != 0:
            step["verdict"] = "упал после долгой работы — похоже на данные, не на код"
        else:
            step["verdict"] = "нормальный выход"

        report["attempts"].append(step)

        if proc.returncode == 0:
            report["status"] = "ok"
            break
        if attempt < int(cfg["max_restarts"]):
            time.sleep(float(cfg["restart_delay"]))
    else:
        report["status"] = "failed"

    report["ended"] = datetime.now().isoformat(timespec="seconds")
    write_report(report)
    return report


def show_status():
    path = LOGS_DIR / "last_report.json"
    if not path.exists():
        return "Отчётов ещё нет — супервизор не запускался."
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [f"Последний запуск: {data.get('started')} → {data.get('ended')}",
             f"Статус: {data.get('status')}"]
    for step in data.get("attempts", []):
        rb = step.get("rollback")
        tail = f", откат: {rb.get('snapshot')}" if rb and rb.get("ok") else ""
        lines.append(f"• попытка {step['attempt']}: код {step['returncode']}, "
                     f"{step['seconds']} с{tail}")
    for note in data.get("notes", []):
        lines.append(f"! {note}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Супервизор Ауры")
    parser.add_argument("mode", nargs="?", default="status",
                        choices=["run", "once", "restore", "status", "sniff"])
    parser.add_argument("--stamp", default="", help="id снапшота для restore")
    parser.add_argument("--dry-run", action="store_true", help="показать, что откатится")
    args = parser.parse_args()

    cfg = load_config()

    if args.mode == "sniff":
        cmd, cwd = guess_command()
        skills = guess_skills_dir()
        print("команда:", " ".join(cmd) if cmd else "не найдена — впиши в config.json")
        print("рабочая папка:", cwd or "—")
        print("папка скиллов:", skills or "не найдена")
        print("свежий снапшот:", (latest_backup(skills).name if skills and latest_backup(skills) else "нет"))
        return 0

    if args.mode == "once":
        result = run_once(cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "ok" else 1

    if args.mode == "restore":
        skills = Path(cfg["skills_dir"]) if cfg["skills_dir"] else guess_skills_dir()
        if not skills:
            print("Не нашла папку skills — укажи skills_dir в config.json")
            return 2
        result = restore(skills, args.stamp, dry=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.mode == "run":
        report = run_supervised(cfg)
        print(write_report(report))
        return 0 if report.get("status") == "ok" else 1

    print(show_status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
