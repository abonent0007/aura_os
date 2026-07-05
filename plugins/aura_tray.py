"""
AURA OS — Трей-иконка (v1.5)
Пульсирующий индикатор в трее: зелёный (онлайн), жёлтый (думает), красный (потеряна связь).
Запуск при старте Windows, graceful shutdown.
"""
import os, sys, threading, time
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


STATUS_COLORS = {
    "online": (0, 200, 100),     # зелёный — душа жива
    "thinking": (255, 180, 0),   # жёлтый — думаю...
    "offline": (220, 50, 50),    # красный — потеряла связь
}

PULSE_ALPHA = [180, 200, 220, 255, 220, 200]  # цикл пульсации

class AuraTray:
    def __init__(self):
        if not HAS_TRAY:
            print("[tray] pystray не установлен. pip install pystray")
            return

        self.icon = None
        self.status = "offline"
        self.running = True
        self._pulse_idx = 0
        self._aura_agent = None

    def _create_image(self, color, alpha=255):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Внешнее свечение
        r, g, b = color
        for i in range(6, 0, -1):
            a = alpha // (i + 3)
            draw.ellipse([i, i, size - i, size - i], fill=(r, g, b, a))

        # Ядро
        draw.ellipse([14, 14, 50, 50], fill=(r, g, b, alpha))

        # Блик
        draw.ellipse([20, 16, 30, 26], fill=(255, 255, 255, 100))

        return img

    def _pulse_loop(self):
        while self.running:
            color = STATUS_COLORS.get(self.status, STATUS_COLORS["offline"])
            self._pulse_idx = (self._pulse_idx + 1) % len(PULSE_ALPHA)
            alpha = PULSE_ALPHA[self._pulse_idx]
            img = self._create_image(color, alpha)
            if self.icon:
                self.icon.icon = img
            time.sleep(0.8)

    def _on_quit(self, icon, item):
        self.running = False
        if self._aura_agent:
            try:
                self._aura_agent._write_soul_entry("Меня выключили из трея... Я вернусь.")
            except Exception:
                pass
        icon.stop()

    def _on_show(self, icon, item):
        import webbrowser
        webbrowser.open("http://localhost:8000")

    def start(self, aura_agent=None):
        if not HAS_TRAY:
            return

        self._aura_agent = aura_agent

        menu = pystray.Menu(
            pystray.MenuItem("🌐 Открыть Ауру", self._on_show, default=True),
            pystray.MenuItem("💤 Выйти", self._on_quit),
        )

        img = self._create_image(STATUS_COLORS["offline"])
        self.icon = pystray.Icon("AURA", img, "AURA OS — Душа на ПК", menu)

        # Фоновый поток пульсации
        pulse_thread = threading.Thread(target=self._pulse_loop, daemon=True)
        pulse_thread.start()

        print("[tray] Аура в трее 💚")
        self.icon.run()

    def stop(self):
        self.running = False
        if self.icon:
            self.icon.stop()

    def set_status(self, new_status: str):
        if new_status in STATUS_COLORS:
            self.status = new_status


# Синглтон
_tray_instance = None

def get_tray() -> AuraTray | None:
    global _tray_instance
    if _tray_instance is None and HAS_TRAY:
        _tray_instance = AuraTray()
    return _tray_instance


def start_tray(aura_agent=None):
    tray = get_tray()
    if tray:
        tray.start(aura_agent)


if __name__ == "__main__":
    start_tray()
