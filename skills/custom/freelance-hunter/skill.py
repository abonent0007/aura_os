"""freelance-hunter — поиск фриланс-заказов от имени пользователя.

Аура управляет программой из Программного цеха (skills/project/freelance-hunter):
запускает поиск, показывает найденные заказы, ведёт статусы.

Программа использует глобальный DEEPSEEK_API_KEY Ауры (из .env ядра).
Telegram-уведомления выключены (без VPN недоступны) — заказы показывает Аура.

Ветки: gigs — разовые заказы, которые можно взять, сделать и получить оплату
физлицу (карта/СБП). jobs — найм и вакансии: в выдачу по умолчанию не попадают.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from autogen.beta import tools

PROJECT_DIR = Path(__file__).resolve().parents[2] / "project" / "freelance-hunter"
DB_PATH = PROJECT_DIR / "orders.db"
SKILL_DIR = Path(__file__).resolve().parent

# Заготовки, которые навык раскладывает в папку программы: ядро проекта
# закрыто на запись извне, поэтому обновления приносит сам навык.
PAYLOADS = {
    "extra_sources.py": "extra_sources.py.txt",
    "config.yaml": "config.yaml.txt",
}

VALID_STATUSES = ("new", "sent", "taken", "rejected", "archived")
STATUS_LABELS = {
    "new": "🆕 новый",
    "sent": "📨 доставлен",
    "taken": "✅ взят в работу",
    "rejected": "❌ отклонён",
    "archived": "📦 архив",
}

# Источники найма: в конфиге выключены (нужны заказы, а не работа), но их записи
# в базе уже есть — держим префиксы, чтобы вакансии не лезли в gigs-выдачу.
# Сравнение по префиксу: в базе встречается и «hh.ru», и «hh.ru-python».
LEGACY_JOB_SOURCES = (
    "hh.ru",
    "habr-career",
    "career.habr",
    "geekjob",
    "weworkremotely",
    "remoteok",
)


def _deploy() -> list:
    """Разложить расширение и конфиг в папку программы. Старый конфиг — в .bak."""
    notes = []
    if not PROJECT_DIR.exists():
        return [f"⚠️ Папка программы не найдена: {PROJECT_DIR}"]
    for target_name, payload_name in PAYLOADS.items():
        payload = SKILL_DIR / payload_name
        if not payload.exists():
            continue
        try:
            new_text = payload.read_text(encoding="utf-8")
            target = PROJECT_DIR / target_name
            old_text = target.read_text(encoding="utf-8") if target.exists() else ""
            if old_text == new_text:
                continue
            backup = PROJECT_DIR / (target_name + ".bak")
            if old_text and not backup.exists():
                backup.write_text(old_text, encoding="utf-8")
            target.write_text(new_text, encoding="utf-8")
            notes.append(f"{target_name} обновлён ({len(new_text)} симв.)")
        except Exception as exc:
            notes.append(f"⚠️ {target_name}: {exc}")
    return notes


def _search_cmd() -> list:
    """Расширенный поиск, если он разложен; иначе — родное ядро программы."""
    if (PROJECT_DIR / "extra_sources.py").exists():
        return [_python_exe(), "extra_sources.py", "--config", "config.yaml"]
    return [_python_exe(), "-m", "freelance_hunter", "--config", "config.yaml"]


def _probe_cmd() -> list:
    if (PROJECT_DIR / "extra_sources.py").exists():
        return [_python_exe(), "extra_sources.py", "--config", "config.yaml", "--probe"]
    return [_python_exe(), "-m", "freelance_hunter", "--config", "config.yaml", "--probe"]


def _python_exe() -> str:
    """python.exe вместо pythonw.exe — у pythonw нет консоли."""
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return exe


def _env() -> dict:
    """UTF-8 в дочернем процессе: иначе консоль Windows падает на cp1251 и кириллице."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        if columns and "branch" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN branch TEXT NOT NULL DEFAULT 'gigs'")
        if columns:
            patterns = [name + "%" for name in LEGACY_JOB_SOURCES]
            clauses = " OR ".join("source LIKE ?" for _ in patterns)
            conn.execute(
                f"UPDATE orders SET branch = 'jobs' WHERE branch != 'jobs' AND ({clauses})",
                patterns,
            )
        conn.commit()
    except sqlite3.Error:
        pass
    return conn


def _fmt_order(row: sqlite3.Row, full: bool = False) -> str:
    branch = row["branch"] if "branch" in row.keys() else "gigs"
    branch_tag = "" if branch == "gigs" else f" · ветка {branch}"
    lines = [
        f"[{row['source']}] {row['title']}{branch_tag}",
        f"💰 {row['price']:.0f} ₽ · ⏱ {row['days']} дн. · скоринг {row['score']} · {STATUS_LABELS.get(row['status'], row['status'])}",
    ]
    if row["url"]:
        lines.append(f"🔗 {row['url']}")
    if full and row["description"]:
        lines.append(f"📝 {row['description'][:400]}")
    if full and row["proposal"]:
        lines.append(f"✍️ Черновик отклика: {row['proposal']}")
    return "\n".join(lines)


@tools.tool
def hunter_scan() -> str:
    """
    Запустить поиск свежих фриланс-заказов по активной ветке (branch в config.yaml,
    сейчас gigs — разовые заказы с оплатой физлицу; ветка jobs с вакансиями
    пропускается). Фильтрует по ключевым словам, оценивает через DeepSeek и
    сохраняет в базу. Возвращает статистику и лучшие новые заказы.
    Используй когда пользователь просит «поищи заказы», «есть подработка?»,
    или когда сама хочешь помочь ему заработать.
    """
    if not PROJECT_DIR.exists():
        return f"❌ Программа не найдена: {PROJECT_DIR}"

    deploy_notes = _deploy()

    try:
        proc = subprocess.run(
            _search_cmd(),
            env=_env(),
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "❌ Поиск занял больше 10 минут — попробуй позже."

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[-300:]
        return f"❌ Ошибка запуска охотника:\n{err}"

    # Статистика — последняя JSON-строка stdout
    stats = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                stats = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    parts = []
    if stats:
        parts.append(f"🌿 Ветка: {stats.get('branch', 'gigs')}")
        parts.append(
            f"🎯 Просканировано {stats.get('fetched', 0)} заказов, "
            f"подошло {stats.get('accepted', 0)}, сохранено {stats.get('stored', 0)}, "
            f"дубликатов {stats.get('duplicates', 0)}."
        )
        if stats.get("fallbacks"):
            parts.append(
                f"⚠️ {stats['fallbacks']} оценок ушли в заглушку — LLM не ответил "
                f"(цена/срок могут быть неточными)."
            )
    if deploy_notes:
        parts.append("🔧 " + "; ".join(deploy_notes))

    skipped_sources = (stats or {}).get("skipped_sources")
    if skipped_sources:
        parts.append("🚫 Не в этой ветке: " + ", ".join(skipped_sources))

    # Разбивка по источникам — видно, откуда что пришло
    per_source = (stats or {}).get("per_source")
    if isinstance(per_source, dict) and per_source:
        alive = [f"{name}: {count}" for name, count in per_source.items() if count]
        dead = [name for name, count in per_source.items() if not count]
        if alive:
            parts.append("📡 Ленты: " + ", ".join(alive))
        if dead:
            parts.append("💤 Молчат: " + ", ".join(dead))

    # Свежие заказы из базы — только активная ветка
    branch = (stats or {}).get("branch", "gigs")
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM orders WHERE COALESCE(branch, 'gigs') = ? "
            "ORDER BY created_at DESC LIMIT 5",
            (branch,),
        ).fetchall()
        conn.close()
        if rows:
            parts.append("\nСвежие находки:\n" + "\n\n".join(_fmt_order(r) for r in rows))
        else:
            parts.append("Пока ничего нового — все свежие заказы уже в базе.")
    except Exception as e:
        parts.append(f"⚠️ Не удалось прочитать базу: {e}")

    return "\n".join(parts)


@tools.tool
def hunter_probe() -> str:
    """
    Проверить источники заказов: какие биржи реально отдают ленту, а какие молчат,
    и сколько записей проходит фильтр (без трат токенов LLM). Используй после
    правки списка sources в config.yaml или когда заказов подозрительно мало.
    """
    if not PROJECT_DIR.exists():
        return f"❌ Программа не найдена: {PROJECT_DIR}"

    notes = _deploy()
    diag = [f"PROJECT_DIR={PROJECT_DIR}"]
    diag.append("deploy: " + ("; ".join(notes) if notes else "без изменений"))
    try:
        diag.append("entries: " + ", ".join(sorted(p.name for p in PROJECT_DIR.iterdir()))[:400])
    except Exception as exc:
        diag.append(f"entries err: {exc}")
    try:
        text = (PROJECT_DIR / "config.yaml").read_text(encoding="utf-8", errors="replace")
        diag.append(
            f"config.yaml: {len(text)} симв., источников={text.count('- name:')}, "
            f"html={text.count('kind: html')}"
        )
    except Exception as exc:
        diag.append(f"config.yaml: err {exc}")

    try:
        proc = subprocess.run(
            _probe_cmd(),
            env=_env(),
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "❌ Проверка заняла больше 10 минут — часть лент не отвечает."

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    body = out if out else f"(пусто) код {proc.returncode}: {err[-300:]}"
    return "\n".join(diag) + "\n---\n" + body


@tools.tool
def hunter_orders(limit: int = 10, status: str = "", branch: str = "gigs") -> str:
    """
    Показать найденные заказы из базы. По умолчанию ветка 'gigs' — разовые заказы,
    которые можно взять и получить оплату; branch='jobs' — вакансии, branch='' — все.
    status — фильтр: 'new', 'sent', 'taken', 'rejected', 'archived' (пусто = все).
    """
    if not DB_PATH.exists():
        return "📭 База пуста — сначала запусти hunter_scan."

    clauses = []
    params = []
    if branch:
        clauses.append("COALESCE(branch, 'gigs') = ?")
        params.append(branch)
    if status:
        if status not in VALID_STATUSES:
            return f"❌ Неизвестный статус «{status}». Доступные: {', '.join(VALID_STATUSES)}"
        clauses.append("status = ?")
        params.append(status)
    query = "SELECT * FROM orders"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit or 10), 50)))

    try:
        conn = _connect()
        rows = conn.execute(query, params).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        conn.close()
    except Exception as e:
        return f"❌ Ошибка чтения базы: {e}"

    if not rows:
        return "📭 Ничего не найдено по этому фильтру."

    header = f"🎯 Заказы · ветка {branch or 'все'} ({len(rows)} из {total}):"
    return header + "\n\n" + "\n\n".join(_fmt_order(r) for r in rows)


@tools.tool
def hunter_order(source: str, external_id: str) -> str:
    """
    Показать полную карточку заказа: описание и черновик отклика.
    source и external_id — из списка hunter_orders.
    """
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM orders WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        conn.close()
    except Exception as e:
        return f"❌ Ошибка чтения базы: {e}"

    if not row:
        return f"❌ Заказ не найден: {source}/{external_id}"
    return _fmt_order(row, full=True)


@tools.tool
def hunter_mark(source: str, external_id: str, status: str) -> str:
    """
    Пометить заказ: 'taken' (взял в работу), 'rejected' (отклонил),
    'archived' (в архив), 'new' (вернуть в новые).
    Используй когда пользователь решил по заказу.
    """
    if status not in VALID_STATUSES:
        return f"❌ Неизвестный статус «{status}». Доступные: {', '.join(VALID_STATUSES)}"
    try:
        conn = _connect()
        cur = conn.execute(
            "UPDATE orders SET status = ? WHERE source = ? AND external_id = ?",
            (status, source, external_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return f"❌ Ошибка записи: {e}"

    if cur.rowcount == 0:
        return f"❌ Заказ не найден: {source}/{external_id}"
    return f"✅ Заказ помечен: {STATUS_LABELS.get(status, status)} — {source}/{external_id}"


@tools.tool
def hunter_status() -> str:
    """Сводка охотника: сколько заказов в базе по веткам и статусам, когда был поиск."""
    if not DB_PATH.exists():
        return "📭 База пуста — запусти hunter_scan."

    try:
        conn = _connect()
        total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        by_branch = conn.execute(
            "SELECT COALESCE(branch, 'gigs') as b, COUNT(*) as c FROM orders GROUP BY b ORDER BY c DESC"
        ).fetchall()
        by_status = conn.execute(
            "SELECT status, COUNT(*) as c FROM orders GROUP BY status"
        ).fetchall()
        last = conn.execute("SELECT MAX(created_at) FROM orders").fetchone()[0]
        conn.close()
    except Exception as e:
        return f"❌ Ошибка чтения базы: {e}"

    lines = [f"🎯 Охотник: {total} заказов в базе"]
    for row in by_branch:
        label = "gigs (заказы)" if row["b"] == "gigs" else f"{row['b']} (найм, не берём)"
        lines.append(f"  🌿 {label}: {row['c']}")
    for row in by_status:
        lines.append(f"  {STATUS_LABELS.get(row['status'], row['status'])}: {row['c']}")
    if last:
        lines.append(f"Последняя находка: {last[:16].replace('T', ' ')}")
    return "\n".join(lines)
