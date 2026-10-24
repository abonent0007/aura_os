"""
aura_live2d.py — Окна Live2D-аватаров Ауры
Два режима:
  --mode desktop   — Мао на рабочем столе (не поверх окон, прижата к правому нижнему углу)
  --mode companion — выбранный персонаж парит поверх окон (прозрачный, перетаскиваемый)
Окна запускаются ОТДЕЛЬНЫМИ ПРОЦЕССАМИ (PyQt5 WebEngine: WA_TranslucentBackground).
"""
import sys
import subprocess
from pathlib import Path

SCRIPT = Path(__file__)


def spawn(mode: str, model: str = None, port: int = 8000,
          width: int = 600, height: int = 800) -> subprocess.Popen:
    """Запустить окно аватара в отдельном процессе."""
    args = [sys.executable, str(SCRIPT), "--port", str(port),
            "--mode", mode, "--width", str(width), "--height", str(height)]
    if model:
        args += ["--model", model]
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(SCRIPT.parent.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return proc
    except Exception as e:
        print(f"[live2d] Ошибка запуска окна: {e}")
        return None


def start_desktop_avatar(port: int = 8000) -> subprocess.Popen:
    """Мао на рабочем столе — принадлежит процессу трея."""
    proc = spawn(mode="desktop", port=port, width=600, height=920)
    if proc:
        print("[live2d] Мао на рабочем столе запущена")
    return proc


def start_companion(port: int = 8000, model: str = "haru") -> subprocess.Popen:
    """Парящий персонаж поверх окон."""
    proc = spawn(mode="companion", model=model, port=port, width=500, height=820)
    if proc:
        print(f"[live2d] Компаньон {model} запущен")
    return proc


class AvatarApi:
    """JS API: глобальная позиция курсора + выход окна."""
    def __init__(self):
        self._window = None
        self._quit_called = False

    def bind(self, window):
        self._window = window

    def quit(self):
        """Закрыть окно (вызывается из JS когда ядро умерло)."""
        if self._quit_called:
            return {"status": "already"}
        self._quit_called = True
        try:
            if self._window is not None:
                self._window.destroy()
            import webview
            for w in webview.windows:
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        return {"status": "ok"}

    def get_mouse_pos(self):
        try:
            import ctypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return {"x": pt.x, "y": pt.y}
        except Exception:
            return {"x": -1, "y": -1}

    def get_window_pos(self):
        try:
            return {"x": self._window.x, "y": self._window.y,
                    "width": self._window.width, "height": self._window.height}
        except Exception:
            return {"x": 0, "y": 0, "width": 500, "height": 700}


def _run_window(port: int, mode: str, model: str, width: int, height: int):
    import webview
    import time as _time

    # cache-busting: Qt WebEngine кеширует старые страницы
    _v = int(_time.time())
    if model:
        url = f"http://localhost:{port}/avatar-window?v={_v}&model={model}"
    else:
        url = f"http://localhost:{port}/avatar-window?v={_v}"

    api = AvatarApi()

    is_desktop = (mode == "desktop")

    window = webview.create_window(
        "AURA",
        url,
        width=width,
        height=height,
        frameless=True,
        transparent=True,
        easy_drag=not is_desktop,       # Мао не перетаскивается
        resizable=not is_desktop,
        text_select=False,
        zoomable=False,
        js_api=api,
    )
    api.bind(window)

    def on_loaded(*_args):
        if not is_desktop:
            try:
                window.on_top = True     # компаньон — поверх окон
            except Exception:
                pass
        if is_desktop:
            # Мао: прижата к правому нижнему углу, обычный уровень окна
            try:
                screens = webview.screens
                if screens:
                    s = screens[0]
                    window.move(s.width - window.width - 20, s.height - window.height - 60)
            except Exception:
                pass
        else:
            # Компаньон: чуть левее угла, чтобы не перекрывал Мао
            try:
                screens = webview.screens
                if screens:
                    s = screens[0]
                    window.move(s.width - window.width - 460, s.height - window.height - 120)
            except Exception:
                pass
        print(f"[live2d] Окно готово: mode={mode}, model={model or 'server'}")

    webview.start(on_loaded, window, gui="qt")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mode", type=str, default="desktop", choices=["desktop", "companion"])
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--width", type=int, default=600)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()
    _run_window(args.port, args.mode, args.model, args.width, args.height)
