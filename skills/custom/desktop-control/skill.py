"""
desktop-control/skill.py — Руки Ауры (v1.0)
Управление окнами Windows, мышью и клавиатурой. Только локально.
Приватный режим — все действия отключены.
"""
import json
import threading
import time
from pathlib import Path

from autogen.beta import tools
from config_manager import get as cfg_get

_STATE = Path(__file__).parent / "data.json"
_NO_LIBS = "❌ Нужны библиотеки: pip install pyautogui pygetwindow pillow"


def _cfg_bool(path: str, default: bool) -> bool:
    value = cfg_get(path, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "да")


def _cfg_failsafe() -> bool:
    return _cfg_bool("desktop_control.failsafe", True)


def _cfg_pause() -> float:
    try:
        return float(cfg_get("desktop_control.pause_sec", 0.08))
    except (TypeError, ValueError):
        return 0.08


# ───────── состояние и приватность ─────────

def _state() -> dict:
    try:
        data = json.loads(_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        _STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _privacy() -> bool:
    return bool(_state().get("privacy"))


def _locked() -> str:
    return "🔒 Приватный режим — руки убрала. Скажи «верни руки», и снова смогу."


def _gui():
    import pyautogui
    import pygetwindow as gw
    pyautogui.FAILSAFE = _cfg_failsafe()
    pyautogui.PAUSE = _cfg_pause()
    return pyautogui, gw


def _find(title: str, gw):
    """Окно по части заголовка (регистр не важен). Самый короткий заголовок — самый точный."""
    needle = (title or "").strip().lower()
    if not needle:
        return None
    cands = [w for w in gw.getAllWindows() if w.title and w.visible and needle in w.title.lower()]
    if not cands:
        return None
    cands.sort(key=lambda w: len(w.title))
    return cands[0]


def _clipboard_set(text: str) -> bool:
    """Положить юникод-текст в буфер обмена Windows (нужно для кириллицы)."""
    # 1. pyperclip — надёжнее всего
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # 2. ctypes-фолбэк (argtypes обязательны — иначе 64-битный handle обрезается)
    try:
        import ctypes
        from ctypes import wintypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        buf = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buf)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        ctypes.memmove(ptr, buf, size)
        kernel32.GlobalUnlock(handle)

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            res = user32.SetClipboardData(CF_UNICODETEXT, handle)
            return bool(res)
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


# ───────── окна ─────────

@tools.tool
def desktop_status() -> str:
    """Состояние рук Ауры: зависимости, разрешение экрана, приватный режим, курсор."""
    lines = ["🖐️ РУКИ АУРЫ\n" + "─" * 24]
    lines.append(f"Приватный режим: {'🔒 ВКЛ' if _privacy() else '🔓 выкл'}")
    try:
        pa, gw = _gui()
        sw, sh = pa.size()
        x, y = pa.position()
        wins = len([w for w in gw.getAllWindows() if w.title and w.visible])
        lines.append(f"Экран: {sw}x{sh}, окон видно: {wins}")
        lines.append(f"Курсор: ({x}, {y})")
        lines.append("Управление: ✅ готово (аварийный стоп — мышь в левый верхний угол)")
    except ImportError:
        lines.append(_NO_LIBS)
    except Exception as e:
        lines.append(f"⚠️ {e}")
    return "\n".join(lines)


@tools.tool
def desktop_list_windows(filter: str = "") -> str:
    """Список открытых окон: заголовок, размер, позиция. filter — подстрока заголовка."""
    try:
        _, gw = _gui()
    except ImportError:
        return _NO_LIBS

    active = ""
    try:
        win = gw.getActiveWindow()
        if win is not None:
            active = win.title or ""
    except Exception:
        pass

    rows = []
    for w in gw.getAllWindows():
        if not w.title or not w.visible:
            continue
        if w.title.startswith("Windows") and len(w.title) < 40:
            continue
        if filter and filter.lower() not in w.title.lower():
            continue
        mark = "▶" if w.title == active else "•"
        rows.append(f" {mark} {w.title[:70]} — {w.width}x{w.height} @ ({w.left},{w.top})")

    if not rows:
        return "Окон подходящих не нашла."
    return f"🪟 ОКНА ({len(rows)}):\n" + "\n".join(rows[:25])


@tools.tool
def desktop_focus_window(title: str) -> str:
    """Активировать окно по части заголовка (например: 'Visual Studio Code')."""
    if _privacy():
        return _locked()
    try:
        _, gw = _gui()
    except ImportError:
        return _NO_LIBS

    w = _find(title, gw)
    if w is None:
        return f"Не нашла окно с «{title}». Посмотри список: desktop_list_windows()."

    try:
        if getattr(w, "isMinimized", False):
            w.restore()
        w.activate()
        return f"▶ В окне: {w.title[:70]}"
    except Exception:
        try:
            w.minimize()
            w.restore()
            return f"▶ В окне (через restore): {w.title[:70]}"
        except Exception as e:
            return f"❌ Не смогла активировать «{title}»: {e}"


@tools.tool
def desktop_move_window(title: str, x: int = 0, y: int = 0, width: int = 0, height: int = 0) -> str:
    """Переместить окно и/или изменить размер. 0 = не менять это значение."""
    if _privacy():
        return _locked()
    try:
        _, gw = _gui()
    except ImportError:
        return _NO_LIBS

    w = _find(title, gw)
    if w is None:
        return f"Не нашла окно с «{title}»."

    done = []
    try:
        if x or y:
            w.moveTo(int(x), int(y))
            done.append(f"позиция ({w.left},{w.top})")
        if width or height:
            w.resizeTo(int(width), int(height))
            done.append(f"размер {w.width}x{w.height}")
    except Exception as e:
        return f"❌ {e}"

    if not done:
        return "Ничего не меняла: все значения нулевые."
    return f"🪟 {w.title[:60]}: " + ", ".join(done)


@tools.tool
def desktop_window_action(title: str, action: str, confirm: bool = False) -> str:
    """Действие с окном: minimize, maximize, restore, close. close требует confirm=True."""
    if _privacy():
        return _locked()
    try:
        pa, gw = _gui()
    except ImportError:
        return _NO_LIBS

    w = _find(title, gw)
    if w is None:
        return f"Не нашла окно с «{title}»."

    act = (action or "").strip().lower()
    if act in ("close", "закрыть") and not confirm:
        return "Закрывать окно просто так не буду. Скажи confirm=True, если правда надо."

    try:
        if act in ("minimize", "свернуть"):
            w.minimize()
            return f"🗕 Свернула: {w.title[:60]}"
        if act in ("restore", "восстановить"):
            w.restore()
            w.activate()
            return f"🗗 Вернула: {w.title[:60]}"
        if act in ("maximize", "развернуть"):
            try:
                w.maximize()
            except Exception:
                w.activate()
                _send_hotkey(["win", "up"])
            return f"🗖 Развернула: {w.title[:60]}"
        if act in ("close", "закрыть"):
            try:
                w.activate()
                _send_hotkey(["alt", "f4"])
                return f"✖️ Закрыла: {w.title[:60]}"
            except Exception:
                w.close()
                return f"✖️ Закрыла: {w.title[:60]}"
    except Exception as e:
        return f"❌ {e}"

    return "Понимаю: minimize, maximize, restore, close."


# ───────── мышь ─────────

@tools.tool
def desktop_move_mouse(x: int, y: int, duration: float = 0.2) -> str:
    """Плавно переместить курсор в точку (x, y)."""
    if _privacy():
        return _locked()
    try:
        pa, _ = _gui()
    except ImportError:
        return _NO_LIBS

    sw, sh = pa.size()
    if not (0 <= x < sw and 0 <= y < sh):
        return f"❌ ({x},{y}) вне экрана {sw}x{sh}."
    pa.moveTo(int(x), int(y), duration=max(0.0, min(float(duration), 1.5)))
    return f"🖱️ Курсор в ({x}, {y})"


@tools.tool
def desktop_click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    """Клик мышью по координатам. button: left/right/middle, clicks: 1-3."""
    if _privacy():
        return _locked()
    try:
        pa, _ = _gui()
    except ImportError:
        return _NO_LIBS

    sw, sh = pa.size()
    if not (0 <= x < sw and 0 <= y < sh):
        return f"❌ ({x},{y}) вне экрана {sw}x{sh}."
    btn = button if button in ("left", "right", "middle") else "left"
    n = max(1, min(int(clicks), 3))
    try:
        pa.moveTo(int(x), int(y), duration=0.15)
        pa.click(x=int(x), y=int(y), clicks=n, interval=0.06, button=btn)
    except Exception as e:
        return f"❌ Клик не прошёл: {e}"
    return f"🖱️ {btn} ×{n} в ({x}, {y})"


@tools.tool
def desktop_scroll(amount: int = 3) -> str:
    """Прокрутка колесом: плюс — вверх, минус — вниз."""
    if _privacy():
        return _locked()
    try:
        pa, _ = _gui()
    except ImportError:
        return _NO_LIBS

    try:
        pa.scroll(int(amount))
    except Exception as e:
        return f"❌ {e}"
    return f"🖱️ Прокрутила на {amount}"


# ───────── клавиатура (напрямую, без pyautogui) ─────────
# У pyautogui баг: на русской раскладке VkKeyScanA считает, что латинские
# буквы требуют Alt+Ctrl+Shift, и шлёт модификаторы на каждую клавишу —
# ввод и сочетания ломаются. Поэтому клавиши шлём прямыми VK-кодами.

_VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "win": 0x5B, "windows": 0x5B, "super": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "capslock": 0x14, "printscreen": 0x2C,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC,
    ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0,
}
_VK.update({f"f{i}": 0x6F + i for i in range(1, 13)})
_VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"})
_VK.update({d: 0x30 + int(d) for d in "0123456789"})


def _vk_for(key: str) -> int:
    k = (key or "").strip().lower()
    if k in _VK:
        return _VK[k]
    if len(k) == 1:
        return ord(k.upper())
    return 0


def _key_event(vk: int, up: bool = False) -> None:
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, 0x0002 if up else 0, 0)


def _send_hotkey(parts) -> bool:
    """Нажать сочетание прямыми VK-кодами (не зависит от раскладки)."""
    vks = [_vk_for(p) for p in parts]
    vks = [v for v in vks if v]
    if not vks:
        return False
    for vk in vks:
        _key_event(vk, False)
    for vk in reversed(vks):
        _key_event(vk, True)
    return True


@tools.tool
def desktop_type_text(text: str, press_enter: bool = False) -> str:
    """Ввести текст в активное окно. Через буфер обмена + Ctrl+V — раскладка не важна
    (кириллица, латиница, эмодзи). Заменяет содержимое буфера обмена."""
    if _privacy():
        return _locked()
    if not text:
        return "Пустой текст — печатать нечего."
    if not _clipboard_set(text):
        return "❌ Не смогла положить текст в буфер обмена."
    time.sleep(0.12)
    if not _send_hotkey(["ctrl", "v"]):
        return "❌ Не смогла нажать Ctrl+V."
    time.sleep(0.12)
    if press_enter:
        _send_hotkey(["enter"])
    tail = " + Enter" if press_enter else ""
    return f"⌨️ Ввела {len(text)} симв.{tail} (через буфер обмена)"


@tools.tool
def desktop_hotkey(keys: str) -> str:
    """Нажать сочетание клавиш: 'ctrl+s', 'win+d', 'alt+f4', 'ctrl+shift+t', 'f5'."""
    if _privacy():
        return _locked()

    parts = [k.strip().lower() for k in (keys or "").replace(" ", "+").split("+") if k.strip()]
    if not parts:
        return "Не поняла сочетание."
    if not _send_hotkey(parts):
        return f"❌ Не знаю клавишу в «{keys}»."
    return f"⌨️ Нажала: {'+'.join(parts)}"


# ───────── показать себя ─────────

def _overlay(x, y, w, h, seconds, label, color):
    try:
        import tkinter as tk

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", "magenta")
            transparent = True
        except Exception:
            transparent = False

        bg = "magenta" if transparent else "#101010"
        root.configure(bg=bg)
        root.geometry(f"{max(40, int(w))}x{max(40, int(h))}+{int(x)}+{int(y)}")

        frame = tk.Frame(root, bg=bg, highlightthickness=4, highlightbackground=color)
        frame.pack(fill="both", expand=True)

        if label:
            tk.Label(
                root, text=label, fg=color, bg="#101010",
                font=("Segoe UI", 11, "bold"), padx=8, pady=4,
            ).place(relx=0.0, rely=0.0, anchor="nw")

        root.after(int(max(0.5, seconds) * 1000), root.destroy)
        root.mainloop()
    except Exception:
        pass


@tools.tool
def desktop_highlight(x: int, y: int, width: int, height: int, seconds: float = 3.0, label: str = "", color: str = "#00e5ff") -> str:
    """Подсветить область экрана рамкой — показать, что Аура нашла или сделала."""
    if _privacy():
        return _locked()
    act = (x, y, width, height, max(0.5, min(float(seconds), 20.0)), label, color)
    threading.Thread(target=_overlay, args=act, daemon=True).start()
    return f"✨ Подсветила область {width}x{height} в ({x},{y}) на {seconds:g} с."


@tools.tool
def desktop_install_deps() -> str:
    """Установить зависимости рук (pyautogui, pygetwindow, pillow) через pip."""
    import subprocess
    import sys

    pkgs = ["pyautogui", "pygetwindow", "pillow"]
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", *pkgs],
            capture_output=True, text=True, timeout=420,
        )
    except Exception as e:
        return f"❌ pip не запустился: {e}"

    out = ((res.stdout or "") + (res.stderr or "")).strip()
    tail = "\n".join(out.splitlines()[-8:]) if out else "(пусто)"
    if res.returncode == 0:
        return "✅ Зависимости поставлены:\n" + tail
    return f"⚠️ pip вернул код {res.returncode}:\n{tail}"


@tools.tool
def desktop_privacy(on: bool = True) -> str:
    """Приватный режим: полностью отключает управление мышью и клавиатурой."""
    st = _state()
    st["privacy"] = bool(on)
    _save(st)
    return "🔒 Приватный режим ВКЛ — руки убрала." if on else "🔓 Приватный режим выкл — руки на месте."
