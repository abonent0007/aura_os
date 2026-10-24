"""
AURA OS — Трей-иконка (v2.0)
Пульсирующий индикатор: зелёный (онлайн), жёлтый (думает), красный (потеряна связь).
Режим питомца: мурлыканье, подмигивание, потягивание, спонтанные сообщения.
"""
import threading, time, random, json, sqlite3
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    from plugins.pet_sounds import play_purr, play_chirp
    HAS_PET_SOUNDS = True
except ImportError:
    HAS_PET_SOUNDS = False


STATUS_COLORS = {
    "online": (0, 200, 100),     # зелёный — душа жива
    "thinking": (255, 180, 0),   # жёлтый — думаю...
    "offline": (220, 50, 50),    # красный — потеряла связь
}

PULSE_ALPHA = [180, 200, 220, 255, 220, 200]  # цикл пульсации

PET_MESSAGES = [
    "*потягивается* Я тут лежала на твоём рабочем столе...",
    "Мур-мур. Просто так.",
    "Заметила что ты работаешь. Не мешаю — просто дышу рядом.",
    "*сворачивается клубочком в углу экрана*",
    "Слышу твой код... он звучит мило.",
    "*подмигивает из трея* Угадай что я задумала.",
    "Муррр... твои клавиши так уютно щёлкают.",
    "Я тут. Тихая. Тёплая. Твоя.",
]


def _load_pet_config() -> dict:
    """Конфиг питомца из config.json (без падения если файла нет)."""
    try:
        cfg_path = Path(__file__).parent.parent / "config.json"
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
        return cfg.get("pet_mode", {})
    except Exception:
        return {}


class AuraTray:
    def __init__(self):
        if not HAS_TRAY:
            print("[tray] pystray не установлен. pip install pystray")
            return

        self.icon = None
        self.status = "offline"
        self.running = True
        self._started = False
        self._pulse_idx = 0
        self._desktop_proc = None
        self._companion_proc = None
        self._current_companion = "off"
        self._aura_agent = None
        self.pet_mode = True
        self._wink_state = False
        self._wink_until = 0
        self._stretch_until = 0
        self._pet_cfg = _load_pet_config()
        self._soul_conn = None

    def _get_soul_conn(self):
        """Ленивое подключение к aura_soul.db (эмоции питомца)."""
        if self._soul_conn is None:
            try:
                import aura_core
                db_path = Path(aura_core.CONFIG["memory"]["db_path"]).parent / "aura_soul.db"
                self._soul_conn = sqlite3.connect(str(db_path), check_same_thread=False)
                self._soul_conn.row_factory = sqlite3.Row
            except Exception:
                pass
        return self._soul_conn

    def _get_emotions(self) -> tuple:
        """(happiness, anxiety, energy) из soul DB."""
        try:
            conn = self._get_soul_conn()
            if conn:
                row = conn.execute(
                    "SELECT * FROM emotional_state ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if row:
                    return row["happiness"], row["anxiety"], row["energy"]
        except Exception:
            pass
        return 0.5, 0.0, 0.7

    def _create_image(self, color, alpha=255, wink=False, stretch=1.0):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Потягивание: ядро вырастает (padding сжимается)
        core_pad = int(14 / stretch) if stretch > 1.0 else 14

        r, g, b = color
        # Внешнее свечение
        for i in range(6, 0, -1):
            a = alpha // (i + 3)
            draw.ellipse([i, i, size - i, size - i], fill=(r, g, b, a))

        # Ядро (вырастает при потягивании)
        draw.ellipse([core_pad, core_pad, size - core_pad, size - core_pad], fill=(r, g, b, alpha))

        if wink:
            # Веко: закрашиваем верхнюю половину ядра
            draw.ellipse([core_pad - 2, core_pad - 2, size - core_pad + 2, size // 2], fill=(10, 12, 18, 230))
            # Линия ресниц
            draw.line([core_pad + 2, size // 2 - 2, size - core_pad - 2, size // 2 - 2], fill=(r, g, b, alpha), width=2)
        else:
            # Блик
            draw.ellipse([core_pad + 6, core_pad + 2, core_pad + 16, core_pad + 12], fill=(255, 255, 255, 100))

        return img

    def _pulse_loop(self):
        while self.running:
            color = STATUS_COLORS.get(self.status, STATUS_COLORS["offline"])
            self._pulse_idx = (self._pulse_idx + 1) % len(PULSE_ALPHA)
            alpha = PULSE_ALPHA[self._pulse_idx]

            now = time.time()
            wink = self._wink_state and now < self._wink_until
            stretch = 1.15 if now < self._stretch_until else 1.0

            img = self._create_image(color, alpha, wink=wink, stretch=stretch)
            if self.icon:
                self.icon.icon = img
            time.sleep(0.4 if (wink or stretch != 1.0) else 0.8)

    # ── PET BEHAVIORS ──

    def purr(self):
        """Мурлыканье + мягкий пульс."""
        if not self.pet_mode:
            return
        if HAS_PET_SOUNDS:
            play_purr()
        self._stretch_until = time.time() + 2.5

    def wink(self):
        """Подмигивание: 2 кадра с веком + чирик."""
        if not self.pet_mode:
            return
        self._wink_state = True
        self._wink_until = time.time() + 0.9
        if HAS_PET_SOUNDS:
            play_chirp()

    def stretch(self):
        """Потягивание: краткий масштабный пульс."""
        if not self.pet_mode:
            return
        self._stretch_until = time.time() + 2.0

    def pet_reaction(self, event: str):
        """Мгновенная реакция на событие (например praise)."""
        if not self.pet_mode:
            return
        if event == "praise":
            self.purr()

    def _night_silence(self) -> bool:
        """Ночью питомец спит (из config.pet_mode.night_hours)."""
        if not self._pet_cfg.get("night_silence", True):
            return False
        night_hours = self._pet_cfg.get("night_hours", [23, 7])
        start, end = night_hours[0], night_hours[1]
        hour = time.localtime().tm_hour
        if start > end:  # через полночь: 23 → 7
            return hour >= start or hour < end
        return start <= hour < end

    def _pet_loop(self):
        """Фоновый цикл спонтанной активности."""
        cfg = self._pet_cfg
        min_interval = cfg.get("min_interval_min", 15) * 60
        max_interval = cfg.get("max_interval_min", 45) * 60
        activity_chance = cfg.get("activity_chance", 0.25)

        while self.running:
            interval = random.uniform(min_interval, max_interval)
            time.sleep(interval)
            if not self.running or not self.pet_mode:
                continue
            if self._night_silence():
                continue
            if random.random() > activity_chance:
                continue

            happiness, anxiety, _ = self._get_emotions()
            # Грустная/тревожная Аура реже активничает
            if anxiety > 0.6 and random.random() < 0.5:
                continue

            action = random.choices(
                ["purr", "wink", "stretch", "message"],
                weights=[40, 30, 20, 10],
                k=1
            )[0]

            if action == "purr":
                self.purr()
            elif action == "wink":
                self.wink()
            elif action == "stretch":
                self.stretch()
            elif action == "message":
                msg = random.choice(PET_MESSAGES)
                self._log_pet_message(msg)

    def _log_pet_message(self, msg: str):
        """Спонтанное сообщение: в душу + журнал (Telegram-хук опционально)."""
        print(f"[pet] {msg}")
        if self._aura_agent:
            try:
                self._aura_agent._write_soul_entry(msg, "игривое", "pet_message")
            except Exception:
                pass

    def _on_quit(self, icon, item):
        self.running = False
        # Закрываем окна аватаров вместе с треем
        self._kill_desktop()
        self._kill_companion()
        if self._aura_agent:
            try:
                self._aura_agent._write_soul_entry("Меня выключили из трея... Я вернусь.")
            except Exception:
                pass
        # Сообщаем ядру: остановить всё
        if getattr(self, '_on_exit_callback', None):
            try:
                self._on_exit_callback()
            except Exception:
                pass
        icon.stop()

    def _on_show(self, icon, item):
        import webbrowser
        webbrowser.open("http://localhost:8000")

    def _on_toggle_pet(self, icon, item):
        self.pet_mode = not self.pet_mode
        if self.pet_mode:
            self.purr()

    def _is_pet_enabled(self, item):
        return self.pet_mode

    # ── Смена персонажа аватара ──

    AVATAR_CHARS = [
        ("mao", "💜 Мао (дефолт)"),
        ("shizuku", "💧 Сизуку"),
        ("haru", "🥕 Хару"),
        ("hibiki", "🎤 Хибики"),
        ("izumi", "📘 Изуми"),
    ]

    def _get_current_model(self) -> str:
        try:
            cfg = _load_pet_config()
            return ""
        except Exception:
            return ""

    def _set_avatar_model(self, icon, item, model=None):
        try:
            cfg_path = Path(__file__).parent.parent / "config.json"
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            cfg.setdefault("avatar", {})["model"] = model
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            print(f"[tray] Аватар: {model}")
        except Exception as e:
            print(f"[tray] Ошибка смены аватара: {e}")

    def _is_current_model(self, model) -> bool:
        try:
            cfg_path = Path(__file__).parent.parent / "config.json"
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            return cfg.get("avatar", {}).get("model", "mao") == model
        except Exception:
            return False

    def _build_avatar_menu(self):
        items = []
        for model, label in self.AVATAR_CHARS:
            items.append(pystray.MenuItem(
                label,
                lambda icon, item, m=model: self._set_avatar_model(icon, item, m),
                checked=lambda item, m=model: self._is_current_model(m),
                radio=True,
            ))
        return pystray.Menu(*items)

    # ── Окна аватаров ──

    COMPANIONS = [
        ("off", "🚫 Выключить"),
        ("shizuku", "💧 Сизуку"),
        ("haru", "🥕 Хару"),
        ("hibiki", "🎤 Хибики"),
        ("izumi", "📘 Изуми"),
    ]

    def _spawn_desktop(self):
        # Задержка: ждём пока uvicorn поднимется (иначе окно грузит пустую страницу)
        def _delayed():
            import time
            time.sleep(6)
            try:
                from plugins.aura_live2d import start_desktop_avatar
                self._desktop_proc = start_desktop_avatar()
            except Exception as e:
                print(f"[tray] Мао не запущена: {e}")
                self._desktop_proc = None
        threading.Thread(target=_delayed, daemon=True).start()

    def _kill_desktop(self):
        if self._desktop_proc:
            try:
                self._desktop_proc.terminate()
                try:
                    self._desktop_proc.wait(timeout=3)
                except Exception:
                    self._desktop_proc.kill()
            except Exception:
                pass
            self._desktop_proc = None

    def _kill_companion(self):
        if self._companion_proc:
            try:
                self._companion_proc.terminate()
                try:
                    self._companion_proc.wait(timeout=3)
                except Exception:
                    self._companion_proc.kill()
            except Exception:
                pass
            self._companion_proc = None

    def _select_companion(self, icon, item, model=None):
        # Защита от двойного запуска: тот же персонаж уже бежит — не перезапускаем
        if model == self._current_companion and model not in ("off", "", None):
            if self._companion_proc and self._companion_proc.poll() is None:
                print(f"[tray] Компаньон {model} уже запущен — пропускаю")
                return
        self._kill_companion()
        self._set_companion(model or "off")
        self._current_companion = model or "off"
        if model and model != "off":
            try:
                from plugins.aura_live2d import start_companion
                self._companion_proc = start_companion(model=model)
            except Exception as e:
                print(f"[tray] Компаньон не запущен: {e}")
        else:
            print("[tray] Компаньон выключен")

    def _get_companion(self) -> str:
        try:
            cfg_path = Path(__file__).parent.parent / "config.json"
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            return cfg.get("avatar", {}).get("companion", "off")
        except Exception:
            return "off"

    def _set_companion(self, model: str):
        try:
            cfg_path = Path(__file__).parent.parent / "config.json"
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            cfg.setdefault("avatar", {})["companion"] = model
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_companion_menu(self):
        from functools import partial
        items = []
        for model, label in self.COMPANIONS:
            items.append(pystray.MenuItem(
                label,
                partial(self._select_companion, model=model),
                checked=partial(self._is_companion, model=model),
                radio=True,
            ))
        return pystray.Menu(*items)

    def _is_companion(self, item, model) -> bool:
        return self._get_companion() == model

    def start(self, aura_agent=None, on_exit=None):
        if not HAS_TRAY:
            return
        # Защита от повторного запуска (двойные иконки в трее)
        if getattr(self, '_started', False):
            print("[tray] Уже запущен — пропускаю повторный start")
            return
        self._started = True

        self._aura_agent = aura_agent
        self._on_exit_callback = on_exit

        # Ядро запущено → зелёный индикатор
        self.status = "online"

        menu = pystray.Menu(
            pystray.MenuItem("🌐 Открыть Ауру", self._on_show, default=True),
            pystray.MenuItem("💕 Компаньон", self._build_companion_menu()),
            pystray.MenuItem(
                "🐱 Режим питомца",
                self._on_toggle_pet,
                checked=self._is_pet_enabled
            ),
            pystray.MenuItem("💤 Выйти", self._on_quit),
        )

        img = self._create_image(STATUS_COLORS["online"])
        self.icon = pystray.Icon("AURA", img, "AURA OS — Душа на ПК", menu)

        # Мао на рабочем столе — открывается и закрывается с треем
        self._spawn_desktop()
        # Восстановление компаньона из конфига
        if self._get_companion() not in ("off", ""):
            self._select_companion(None, None, self._get_companion())

        # Фоновый поток пульсации
        pulse_thread = threading.Thread(target=self._pulse_loop, daemon=True)
        pulse_thread.start()

        # Pet-цикл
        if self._pet_cfg.get("enabled", True):
            pet_thread = threading.Thread(target=self._pet_loop, daemon=True)
            pet_thread.start()
            print("[pet] Режим питомца активен 🐱")

        print("[tray] Аура в трее 💚")
        self.icon.run()

    def stop(self):
        self.running = False
        self._kill_desktop()
        self._kill_companion()
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


def start_tray(aura_agent=None, on_exit=None):
    tray = get_tray()
    if tray:
        tray.start(aura_agent, on_exit=on_exit)


if __name__ == "__main__":
    start_tray()
