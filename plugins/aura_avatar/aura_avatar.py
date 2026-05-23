"""
AURA Avatar — плавающее окно с анимированным лицом для AURA OS.
Потокобезопасный: tkinter всегда в одном потоке, команды через очередь.
"""

import re, time, queue, threading, tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

ASSETS_DIR = Path(__file__).parent / "assets"

VISEME_MAP = {
    'а': 'ah', 'о': 'ah', 'у': 'ah', 'э': 'ah',
    'и': 'ee', 'ы': 'ee', 'е': 'ee', 'ё': 'ee', 'ю': 'ee', 'я': 'ee',
    'б': 'mpb', 'п': 'mpb', 'м': 'mpb',
    'в': 'fv', 'ф': 'fv',
}

MOUTH_IMAGES = {
    "ah": "mouth_ah.png", "ee": "mouth_ee.png",
    "mpb": "mouth_mpb.png", "fv": "mouth_fv.png",
    "silence": "mouth_silence.png",
}
IDLE_IMAGE = "face_idle.png"
AVATAR_SIZE = (400, 400)

def clean_text(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'[#*_~>]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def text_to_visemes(text: str, base_duration: float = 0.12) -> list:
    visemes = [{"time": 0.0, "mouth": "silence"}]
    t = 0.05
    for char in text.lower():
        if 'а' <= char <= 'я' or char == 'ё':
            mouth = VISEME_MAP.get(char, 'silence')
            visemes.append({"time": round(t, 3), "mouth": mouth})
            t += base_duration
            visemes.append({"time": round(t, 3), "mouth": "silence"})
            t += base_duration * 0.4
    return visemes


class AuraAvatar:
    """Основной класс. Все операции с tkinter в выделенном потоке."""

    def __init__(self):
        self._queue = queue.Queue()
        self._running = True
        self._window = None
        self._anim_timer = None
        self._visemes = []
        self._thread = threading.Thread(target=self._tk_thread, daemon=True)
        self._thread.start()
        time.sleep(0.2)  # Даём tkinter запуститься

    def _tk_thread(self):
        """Главный поток tkinter: создаёт окно и обрабатывает очередь."""
        root = tk.Tk()
        root.title("AURA Avatar")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", "black")  # Прозрачный фон
        root.configure(bg="black")

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - AVATAR_SIZE[0]) // 2
        y = (sh - AVATAR_SIZE[1]) // 2
        root.geometry(f"{AVATAR_SIZE[0]}x{AVATAR_SIZE[1]}+{x}+{y}")

        # Drag
        drag_data = {"x": 0, "y": 0}
        def drag_start(e):
            drag_data["x"] = e.x; drag_data["y"] = e.y
        def drag_move(e):
            nx = root.winfo_x() + e.x - drag_data["x"]
            ny = root.winfo_y() + e.y - drag_data["y"]
            root.geometry(f"+{nx}+{ny}")

        canvas = tk.Canvas(root, width=AVATAR_SIZE[0], height=AVATAR_SIZE[1],
                           bg="black", highlightthickness=0)
        canvas.pack()
        for w in (root, canvas):
            w.bind("<Button-1>", drag_start)
            w.bind("<B1-Motion>", drag_move)

        # Load images
        images = {}
        idle_p = ASSETS_DIR / IDLE_IMAGE
        if idle_p.exists():
            img = Image.open(idle_p).resize(AVATAR_SIZE, Image.LANCZOS)
            images["idle"] = ImageTk.PhotoImage(img)
        for key, fn in MOUTH_IMAGES.items():
            p = ASSETS_DIR / fn
            if p.exists():
                img = Image.open(p).resize(AVATAR_SIZE, Image.LANCZOS)
                images[key] = ImageTk.PhotoImage(img)

        def draw_idle():
            canvas.delete("all")
            if "idle" in images:
                canvas.create_image(0, 0, anchor="nw", image=images["idle"])

        def draw_mouth(key):
            canvas.delete("all")
            if key in images:
                canvas.create_image(0, 0, anchor="nw", image=images[key])

        def process_anim():
            if not self._running or not self._visemes:
                draw_idle()
                root.withdraw()  # скрыть после завершения
                self._anim_timer = None
                return
            frame = self._visemes.pop(0)
            draw_mouth(frame["mouth"])
            if self._visemes:
                delay = int((self._visemes[0]["time"] - frame["time"]) * 1000)
            else:
                delay = 100
            delay = max(30, min(delay, 500))
            self._anim_timer = root.after(delay, process_anim)

        def check_queue():
            try:
                while True:
                    cmd, data = self._queue.get_nowait()
                    if cmd == "speak":
                        root.deiconify()
                        root.lift()
                        text, audio_dur = data if isinstance(data, tuple) else (data, None)
                        visemes = text_to_visemes(clean_text(text))
                        if audio_dur and visemes:
                            orig_end = visemes[-1]["time"]
                            if orig_end > 0:
                                scale = audio_dur / orig_end
                                for v in visemes:
                                    v["time"] = round(v["time"] * scale, 3)
                        self._visemes = visemes
                        if self._anim_timer:
                            root.after_cancel(self._anim_timer)
                        process_anim()
                    elif cmd == "stop":
                        self._visemes = []
                        if self._anim_timer:
                            root.after_cancel(self._anim_timer)
                        draw_idle()
                        root.withdraw()
                    elif cmd == "shutdown":
                        self._running = False
                        root.destroy()
                        return
            except queue.Empty:
                pass
            if self._running:
                root.after(50, check_queue)

        draw_idle()
        root.after(50, check_queue)
        root.mainloop()

    def speak(self, text: str, audio_duration: float = None):
        self._queue.put(("speak", (text, audio_duration)))

    def stop(self):
        self._queue.put(("stop", None))

    def shutdown(self):
        self._queue.put(("shutdown", None))
