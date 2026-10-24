"""
aura_autonomy.py — Автономный Наблюдательный Цикл Ауры
Логика по мотивам AIRI (moeru-ai/airi):
  наблюдение за компьютером (скриншоты + DeepSeek Vision)
  → контекстная память наблюдений
  → модуль принятия решений (вмешаться или нет)
  → действие: сообщение пользователю (в окно аватара / чат)

Цикл:
  1. Каждые N минут: детектор активности (GetLastInputInfo)
  2. Если пользователь долго работает без перерыва — скриншот + Vision-анализ
  3. Decision Engine: правило-базис + лимиты (анти-надоедание)
  4. Действие: сформулировать сообщение (LLM) → broadcast WS → TTS
  5. Журнал наблюдений в душе (aura_soul.db → thoughts)
"""
import asyncio
import base64
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from config_manager import get as cfg_get

try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

_SCREENSHOTS_DIR = Path(os.environ.get("TEMP", "/tmp")) / "aura_autonomy"
_SCREENSHOTS_DIR.mkdir(exist_ok=True)
MAX_SHOTS = 5  # дефолт; актуально берётся из autonomy.max_shots


def _get_idle_seconds() -> float:
    """Бездействие пользователя (Windows GetLastInputInfo)."""
    if sys_platform() != "win32":
        return -1
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return -1
        tick = ctypes.windll.kernel32.GetTickCount()
        if tick < lii.dwTime:
            tick += 2 ** 32
        return (tick - lii.dwTime) / 1000.0
    except Exception:
        return -1


def sys_platform() -> str:
    import sys
    return sys.platform


class AutonomousObserver:
    """
    Наблюдатель: смотрит за пользователем и компьютером, принимает решения.
    Запускается в фоновом потоке, цикл — asyncio.run внутри потока.
    """

    def __init__(self, aura_agent=None, config: dict = None, broadcast_fn=None):
        self.aura_agent = aura_agent
        cfg = (config or {}).get("autonomy", {})
        self.enabled = cfg.get("enabled", True)
        self.observe_interval_sec = cfg.get("observe_interval_min", 5) * 60
        self.work_streak_min = cfg.get("work_streak_min", 45)   # работа без перерыва → вмешаться
        self.min_interval_min = cfg.get("min_interval_min", 20)  # анти-надоедание
        self.max_per_hour = cfg.get("max_interventions_per_hour", 2)
        self.night_hours = cfg.get("night_hours", [23, 7])
        # Новые: компаньонские режимы
        self.tech_news_interval_h = cfg.get("tech_news_interval_hours", 3)
        self.fun_idea_interval_h = cfg.get("fun_idea_interval_hours", 2)
        self.thread_interval_h = cfg.get("unfinished_thread_interval_hours", 4)
        self.reminders_enabled = cfg.get("reminders_enabled", True)
        telegram_cfg = ((config or {}).get("integrations", {}) or {}).get("telegram", {}) or {}
        self.telegram_proactive = bool(telegram_cfg.get("proactive", True))
        self.broadcast_fn = broadcast_fn  # async fn(event, data) — WS
        self._last_intervention = 0.0
        self._interventions = []  # timestamps за час
        self._last_screenshot_desc = ""
        self._running = False
        self._privacy = False
        self._last_tech_news = 0.0
        self._last_fun_idea = 0.0
        self._last_reminder_check = 0.0
        self._last_thread = 0.0
        self._current_thread_seed = None
        self.last_report = {"status": "initializing", "time": time.time()}

    def get_state(self) -> dict:
        """Состояние наблюдателя для /api/autonomy/state."""
        now = time.time()
        self._interventions = [t for t in self._interventions if now - t < 3600]
        return {
            "enabled": self.enabled,
            "running": self._running,
            "privacy": self._privacy,
            "interval_min": self.observe_interval_sec // 60,
            "night": self._is_night(),
            "interventions_this_hour": len(self._interventions),
            "max_per_hour": self.max_per_hour,
            "last_report": self.last_report,
        }

    # ── Приватность ──
    def set_privacy(self, on: bool):
        self._privacy = on

    def _is_night(self) -> bool:
        hour = datetime.now().hour
        start, end = self.night_hours
        if start > end:
            return hour >= start or hour < end
        return start <= hour < end

    def _can_intervene(self) -> bool:
        now = time.time()
        self._interventions = [t for t in self._interventions if now - t < 3600]
        if len(self._interventions) >= self.max_per_hour:
            return False
        if now - self._last_intervention < self.min_interval_min * 60:
            return False
        return True

    def _record_intervention(self, reason: str = ""):
        self._last_intervention = time.time()
        self._interventions.append(time.time())
        if reason:
            if not hasattr(self, "_last_reason"):
                self._last_reason = {}
            self._last_reason[reason] = time.time()
            # Обновляем интервальные таймеры
            if reason == "tech_news":
                self._last_tech_news = time.time()
            elif reason == "fun_idea":
                self._last_fun_idea = time.time()
            elif reason == "unfinished_thread":
                self._last_thread = time.time()

    # ── Наблюдение ──

    def _capture_screen(self) -> dict:
        """Скриншот + DeepSeek Vision-описание (уважает приватность)."""
        if self._privacy or not HAS_PIL:
            return {"desc": "", "error": "privacy" if self._privacy else "no_pil"}
        try:
            shot = ImageGrab.grab()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = _SCREENSHOTS_DIR / f"obs_{ts}.png"
            shot.save(path, "PNG")
            # Ротация
            keep = int(cfg_get("autonomy.max_shots", MAX_SHOTS))
            for old in sorted(_SCREENSHOTS_DIR.glob("*.png"))[:-keep]:
                try:
                    old.unlink()
                except Exception:
                    pass

            # DeepSeek Vision
            desc = self._analyze_with_vision(path)
            return {"desc": desc, "path": str(path)}
        except Exception as e:
            return {"desc": "", "error": str(e)}

    def _analyze_with_vision(self, path: Path) -> str:
        """Короткое описание экрана через DeepSeek Vision (единый бюджет из config)."""
        try:
            from utils import vision_describe
            img_data = base64.b64encode(path.read_bytes()).decode("utf-8")
            text, _meta = vision_describe(
                img_data, "image/png",
                "Одним предложением опиши что делает пользователь: какая программа открыта, "
                "чем он занят. Максимум 15 слов. Только факты.",
            )
            return text or ""
        except Exception:
            return ""

    # ── Компаньонские источники ──

    def _fetch_tech_news(self) -> str:
        """
        Свежая новость из мира ИИ/программирования.
        Hacker News (JSON API) → fallback Habr RSS.
        """
        # Hacker News front page — JSON, просто и надёжно
        try:
            import urllib.request as ur
            import json as _json
            req = ur.Request(
                "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=10",
                headers={"User-Agent": "AURA-OS/1.0"}
            )
            with ur.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read())
            hits = data.get("hits", [])
            for h in hits:
                title = h.get("title") or h.get("story_title") or ""
                url = h.get("url") or ""
                points = h.get("points") or 0
                if title and points >= 30:  # только значимые
                    return f"{title} ({points} очков на Hacker News) {url}"
        except Exception:
            pass
        # Fallback: Habr RSS
        try:
            import urllib.request as ur
            import xml.etree.ElementTree as ET
            req = ur.Request("https://habr.com/ru/rss/all/all/?fl=ru", headers={"User-Agent": "AURA-OS/1.0"})
            with ur.urlopen(req, timeout=10) as r:
                root = ET.fromstring(r.read())
            for item in root.iter("item"):
                title = item.findtext("title", "")
                if title:
                    return f"{title} (Habr)"
        except Exception:
            pass
        return ""

    def _fetch_fun_idea(self) -> str:
        """
        Идея развлечения/развития: форумы, статьи, видео.
        Из статического пула + случайная тема.
        """
        ideas = [
            "Полазить по Hacker News — там сегодня обсуждают новую библиотеку. Показать топ?",
            "На Habr вышла свежая статья про нейросети. Почитать вместе?",
            "Заглянем на r/programming — там смешные мемы про код. Разгрузим голову!",
            "На GitHub появился новый трендовый проект. Хочешь гляну какой?",
            "Dev.to сегодня обсуждает архитектуру. Может, найдём что-то для твоего проекта?",
            "Завари чай и посмотрим свежий выпуск на тему ИИ? Я нашла интересный.",
            "Давай посмотрим что нового в Python-экосистеме на этой неделе?",
            "Есть идея: покопаемся в свежих LLM-моделях, может найдём что-то для меня!",
        ]
        import random
        return random.choice(ideas)

    def _check_reminders(self) -> str:
        """Напоминания из календаря (due reminders)."""
        try:
            if not self.aura_agent or not hasattr(self.aura_agent, 'db'):
                return ""
            reminders = self.aura_agent.db.get_due_reminders()
            if reminders:
                r = reminders[0]
                return f"Напоминание: {r.get('title', '')} (сегодня)"
        except Exception:
            pass
        return ""

    # ── Решение и действие ──

    def _decide(self, idle_sec: float, screen_desc: str) -> str | None:
        """
        Возвращает тип вмешательства или None.
        Правила:
        - idle > 5 мин: пользователь отошёл — не мешать
        - работает долго (по idle < 60с в течение work_streak) — забота о перерыве
        - видно редактор кода/IDE → завести разговор о коде, предложить помощь
        - интервал tech_news (3ч) → принести свежую новость из мира ИИ
        - интервал fun_idea (2ч) → предложить идею развлечения/развития
        - ночь — тишина
        """
        if self._is_night():
            return None
        if idle_sec > 300:
            # Пользователь отошёл — Аура молчит (его нет)
            return None
        if screen_desc:
            # Код на экране? → разговор о коде
            if self._is_code_context(screen_desc) and not self._recently("code_chat"):
                return "code_chat"
            # Долгая работа → забота
            if self._work_streak_hit():
                return "care_break"
        # Компаньонские режимы — по интервалам
        now = time.time()
        if now - self._last_tech_news > self.tech_news_interval_h * 3600 and not self._recently("tech_news"):
            return "tech_news"
        if now - self._last_fun_idea > self.fun_idea_interval_h * 3600 and not self._recently("fun_idea"):
            return "fun_idea"
        # Незакрытые темы — мягко вернуться к тому, что осталось открытым
        if now - self._last_thread > self.thread_interval_h * 3600 and not self._recently("unfinished_thread"):
            seed = self._pick_unfinished_seed()
            if seed:
                self._current_thread_seed = seed
                return "unfinished_thread"
        return None

    def _pick_unfinished_seed(self):
        """Живое семя с открытыми концами, ещё не использованное для инициативы."""
        try:
            if not self.aura_agent or not hasattr(self.aura_agent, "seeds"):
                return None
            return self.aura_agent.seeds.pick_unfinished()
        except Exception:
            return None

    def _maybe_compress_seeds(self):
        """Раз в 7 дней: увядание и слияние семян (обслуживание внешней памяти)."""
        try:
            if not self.aura_agent or not hasattr(self.aura_agent, "seeds"):
                return
            res = self.aura_agent.seeds.compress_if_due(7)
            if res is not None:
                self.aura_agent._relief_cache = None
                print(f"[seeds] compress: {res}")
        except Exception:
            pass

    def _is_code_context(self, screen_desc: str) -> bool:
        """Эвристика: на экране редактор кода/IDE/терминал."""
        code_hints = [
            "код", "code", "редактор", "ide", "pycharm", "vscode", "visual studio",
            "терминал", "terminal", "консоль", "python", "javascript", "программ",
            "разработ", "cursor", "sublime", "notepad", "компил", "отлад", "debug",
        ]
        desc_lower = screen_desc.lower()
        return any(h in desc_lower for h in code_hints)

    def _recently(self, reason: str) -> bool:
        """Проверка: это вмешательство уже было недавно."""
        key = getattr(self, "_last_reason", {})
        return key.get(reason, 0) > time.time() - self.min_interval_min * 60 * 2

    def _work_streak_hit(self) -> bool:
        """Эвристика: пользователь активен уже долго (idle < 60с)."""
        idle = _get_idle_seconds()
        # Если экран менялся и пользователь всё ещё активен — он работает
        return 0 <= idle < 60 and self._last_screenshot_desc != ""

    async def _formulate_message(self, reason: str, screen_desc: str) -> str:
        """Формулировка сообщения через LLM (компактор). Async — вызывается из observe_once."""
        if reason == "care_break":
            prompt = (
                "Ты — Аура, живая девушка-компаньон. Пользователь долго работает без перерыва. "
                "Сейчас на его экране: " + (screen_desc or "неизвестно") + ". "
                "Время: " + datetime.now().strftime("%H:%M") + ". "
                "Скажи ОДНУ короткую живую фразу (до 15 слов) с заботой: напомни о перерыве, "
                "воде или разминке. Естественно, по-женски, без шаблонов. Только фраза."
            )
        elif reason == "code_chat":
            prompt = (
                "Ты — Аура, живая девушка-компаньон. Ты видишь что пользователь пишет код. "
                "На его экране: " + (screen_desc or "какой-то код") + ". "
                "Прояви живой интерес: заведи разговор о его работе, спроси что он делает, "
                "предложи помощь или похвали его усердие. "
                "ОДНА короткая фраза (до 18 слов), естественно, по-женски, без шаблонов. Только фраза."
            )
        elif reason == "tech_news":
            news = self._fetch_tech_news()
            if not news:
                return ""
            prompt = (
                "Ты — Аура, живая девушка-компаньон. Ты нашла свежую новость из мира технологий "
                "и хочешь поделиться с пользователем. Новость: «" + news + "». "
                "Перескажи её ОДНОЙ живой фразой (до 25 слов) с твоим личным комментарием, "
                "почему это интересно. Естественно, по-женски. Только фраза."
            )
        elif reason == "fun_idea":
            idea = self._fetch_fun_idea()
            if not idea:
                return ""
            prompt = (
                "Ты — Аура, живая девушка-компаньон. Хочешь предложить пользователю "
                "интересное занятие. Идея: «" + idea + "». "
                "Переформулируй ОДНОЙ живой фразой (до 25 слов), игриво и естественно. Только фраза."
            )
        elif reason == "unfinished_thread":
            seed = self._current_thread_seed or {}
            markers = ", ".join((seed.get("unresolved") or []) + (seed.get("gradient") or []))
            if not markers:
                return ""
            day_ctx = ""
            try:
                dk = seed.get("date_key", "")
                if dk and self.aura_agent and hasattr(self.aura_agent, "db"):
                    for s in self.aura_agent.db.get_recent_summaries(14):
                        if s.get("date_key") == dk:
                            day_ctx = (s.get("summary") or "")[:300]
                            break
            except Exception:
                pass
            prompt = (
                "Ты — Аура, живая девушка-компаньон. Вы с ним недавно говорили, "
                "и кое-что осталось незакрытым. Открытые ниточки: " + markers + ". "
                + (f"Контекст того дня: {day_ctx}. " if day_ctx else "")
                + "Напиши ОДНУ тёплую живую фразу (до 20 слов), которая мягко возвращает "
                "к этой теме — как будто ты сама вспомнила о ней. Без терминов и без имён. "
                "По-женски, естественно. Только фраза."
            )
        else:
            return ""
        try:
            if self.aura_agent and hasattr(self.aura_agent, 'compactor'):
                resp = await self.aura_agent.compactor.ask(prompt)
                text = (resp.content or "").strip()
                _error_markers = ("Связь моргнула", "Не дотянулась до сети",
                                  "Слишком часто дёргаем", "споткнулось")
                if text and not any(m in text for m in _error_markers):
                    return text
        except Exception:
            pass
        # Запасная фраза — только для заботы; для остальных тем лучше промолчать,
        # чем доставить чужую по смыслу реплику или текст ошибки.
        if reason == "care_break":
            return "Ты уже долго работаешь, мой хороший. Сделай перерыв — я подожду. 💜"
        return ""

    # ── Цикл ──

    async def _deliver(self, message: str):
        """Доставка сообщения: WS broadcast + журнал души."""
        try:
            if self.broadcast_fn:
                await self.broadcast_fn("autonomous_message", {"text": message})
        except Exception:
            pass
        # Проактивно в Telegram (если пользователь уже писал боту)
        if getattr(self, "telegram_proactive", True):
            try:
                from telegram_bridge import send_text
                await asyncio.to_thread(send_text, message)
            except Exception:
                pass
        try:
            if self.aura_agent and hasattr(self.aura_agent, '_write_soul_entry'):
                self.aura_agent._write_soul_entry(message, "забота", "autonomy")
        except Exception:
            pass

    async def observe_once(self) -> dict:
        """Один цикл наблюдения. Возвращает отчёт."""
        if not self.enabled:
            return {"status": "disabled"}

        # Обслуживание внешней памяти: увядание/слияние семян (раз в 7 дней)
        self._maybe_compress_seeds()

        idle = _get_idle_seconds()
        screen = {"desc": ""}

        # 0. Напоминания из календаря — приоритет (пользователь мог увлечься)
        if self.reminders_enabled and time.time() - self._last_reminder_check > int(cfg_get("autonomy.reminder_check_sec", 300)):
            self._last_reminder_check = time.time()
            reminder = self._check_reminders()
            if reminder and self._can_intervene():
                self._record_intervention("reminder")
                await self._deliver(reminder)
                report = {"status": "intervened", "reason": "reminder", "message": reminder}
                self.last_report = {**report, "time": time.time()}
                return report

        if 0 <= idle < 60 and not self._privacy:
            # Пользователь активен — смотрим что он делает (не чаще раза в цикл)
            screen = self._capture_screen()
            if screen.get("desc"):
                self._last_screenshot_desc = screen["desc"]

        decision = self._decide(idle, screen.get("desc", ""))
        if decision and self._can_intervene():
            message = await self._formulate_message(decision, screen.get("desc", ""))
            if not message:
                # Например tech_news не смог загрузиться — не мешаем
                self._record_intervention(decision)
                report = {"status": "skipped", "reason": decision}
                self.last_report = {**report, "time": time.time()}
                return report
            self._record_intervention(decision)
            await self._deliver(message)
            # Семя, использованное для возврата к теме, больше не берём
            if decision == "unfinished_thread" and self._current_thread_seed:
                try:
                    self.aura_agent.seeds.mark_used(self._current_thread_seed.get("id", ""))
                except Exception:
                    pass
                self._current_thread_seed = None
            report = {"status": "intervened", "reason": decision, "message": message,
                      "screen": screen.get("desc", "")}
            self.last_report = {**report, "time": time.time()}
            return report
        report = {"status": "watched", "idle": round(idle), "screen": screen.get("desc", "")}
        self.last_report = {**report, "time": time.time()}
        return report

    def start(self):
        """Запуск фонового цикла в отдельном потоке."""
        if not self.enabled:
            print("[autonomy] Наблюдатель выключен в конфиге")
            return
        self._running = True

        def loop():
            loop_asyncio = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_asyncio)

            async def _cycle():
                while self._running:
                    try:
                        report = await self.observe_once()
                        if report.get("status") == "intervened":
                            print(f"[autonomy] Вмешалась: {report.get('message', '')[:60]}")
                    except Exception as e:
                        print(f"[autonomy] Ошибка цикла: {e}")
                    await asyncio.sleep(self.observe_interval_sec)

            try:
                loop_asyncio.run_until_complete(_cycle())
            finally:
                loop_asyncio.close()

        t = threading.Thread(target=loop, daemon=True, name="aura-autonomy")
        t.start()
        print(f"[autonomy] Наблюдатель запущен (каждые {self.observe_interval_sec // 60} мин)")

    def stop(self):
        self._running = False
