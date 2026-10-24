"""
google-ai/skill.py — Глубокий веб-синтез Ауры (Google AI Mode).

Даёт связный ответ с источниками: свежая информация, документация библиотек/API,
новости, актуальные примеры кода и лучшие практики для проектов.

Помощник: headed Chrome с доверенным профилем (CDP-порт). Параметры берутся из
config.json (секция google_ai) через config_manager — с кэшем и автообновлением.
"""
import os
import socket
import subprocess
import sys
from pathlib import Path

from autogen.beta import tools
from config_manager import get as cfg_get

_DEFAULT_HELPER = r"C:\lib\google-ai.py"


def _helper() -> Path:
    return Path(cfg_get("google_ai.helper_path", _DEFAULT_HELPER))


def _cdp_port() -> int:
    try:
        return int(cfg_get("google_ai.cdp_port", 9222))
    except (TypeError, ValueError):
        return 9222


def _timeout() -> int:
    try:
        return int(cfg_get("google_ai.timeout_sec", 180))
    except (TypeError, ValueError):
        return 180


def _max_out() -> int:
    try:
        return int(cfg_get("google_ai.max_chars", 14000))
    except (TypeError, ValueError):
        return 14000


def _python_exe() -> str:
    """python.exe вместо pythonw.exe — у pythonw нет консоли."""
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    return exe


def _env() -> dict:
    """UTF-8 в дочернем процессе: иначе Windows ломает кириллицу."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _port_open(port: int = None) -> bool:
    port = _cdp_port() if port is None else port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


@tools.tool
def google_ai(query: str) -> str:
    """
    Глубокий веб-синтез через Google AI Mode: готовый связный ответ с источниками
    (10–20 сек). Для свежей информации, документации библиотек/API, новостей,
    актуальных примеров кода и лучших практик для проектов. Зови, когда нужен
    разбор с источниками, а не просто список ссылок.
    """
    query = (query or "").strip()
    if not query:
        return "❌ Пустой запрос — уточни, что именно узнать."
    helper = _helper()
    if not helper.exists():
        return f"❌ Помощник не найден: {helper}"

    try:
        proc = subprocess.run(
            [_python_exe(), str(helper), query],
            env=_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_timeout(),
        )
    except subprocess.TimeoutExpired:
        return "❌ Синтез не ответил вовремя (похоже, Chrome завис). Попробуй ещё разок."
    except Exception as exc:
        return f"❌ Не удалось запустить синтез: {exc}"

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if "CAPTCHA" in out:
        return (
            "⚠️ Google не узнал доверенный профиль (капча). Это решается только вручную: "
            "открой Chrome с профилем %TEMP%\\siti-cdp-profile и реши капчу один раз. "
            "После этого поиск снова заработает."
        )
    if proc.returncode != 0:
        tail = (err or out or "").strip()[-300:]
        return f"❌ Синтез вернул ошибку (код {proc.returncode}): {tail}"
    if not out:
        return "❌ Пустой ответ — Chrome не отдал страницу. Проверь google_ai_status."

    return out[: _max_out()]


@tools.tool
def google_ai_status() -> str:
    """
    Проверить готовность глубокого веб-синтеза: помощник, playwright,
    Chrome с доверенным профилем (CDP). Если Chrome спит — первый
    запрос сам его разбудит (~25 сек).
    """
    helper = _helper()
    lines = [f"🧠 Помощник: {'на месте' if helper.exists() else 'НЕ найден — ' + str(helper)}"]
    try:
        import playwright  # noqa: F401
        lines.append("🎭 playwright: есть")
    except Exception:
        lines.append("🎭 playwright: нет — pip install playwright")
    lines.append(
        f"🌐 Chrome (CDP :{_cdp_port()}): жив — ответы ~13–15 сек"
        if _port_open()
        else f"🌐 Chrome (CDP :{_cdp_port()}): спит — первый запрос разбудит (~25 сек)"
    )
    return "\n".join(lines)
