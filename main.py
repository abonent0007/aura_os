#!/usr/bin/env python3
"""
AURA OS v1.0 — Персональный голосовой ассистент
================================================
Точка входа. Запускает Telegram-бота, веб-интерфейс или консольный режим.

Использование:
    python main.py              # Telegram бот
    python main.py --web        # Веб-интерфейс
    python main.py --console    # Консольный режим
    python main.py --all        # Всё вместе
"""

import argparse
import asyncio
import io
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

# pythonw.exe (запуск без консоли): sys.stdout = None → print() упал бы.
# Перенаправляем в пустоту — но параллельно пишем файловый лог (ниже).
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stderr = sys.stdout

# ── Файловый лог: без него сбои pythonw неотследимы ──
try:
    from loguru import logger as _logger

    _log_dir = Path(__file__).parent / "logs"
    _log_dir.mkdir(exist_ok=True)
    _logger.add(
        _log_dir / "aura.log",
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        level="INFO",
        backtrace=True,
        diagnose=False,
    )

    def _excepthook(exc_type, exc_value, exc_tb):
        _logger.opt(exception=(exc_type, exc_value, exc_tb)).critical(
            "Необработанное исключение — AURA падает"
        )

    sys.excepthook = _excepthook

    import threading as _threading

    def _thread_excepthook(args):
        _logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).critical(
            f"Необработанное исключение в потоке {args.thread.name if args.thread else '?'}"
        )

    _threading.excepthook = _thread_excepthook

    # WARNING+ из стандартного logging (uvicorn и др.) — в тот же файл
    import logging as _logging

    class _InterceptHandler(_logging.Handler):
        def emit(self, record):
            try:
                level = _logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            _logger.opt(exception=record.exc_info).log(level, record.getMessage())

    _logging.getLogger().addHandler(_InterceptHandler())
    _logging.getLogger().setLevel(_logging.WARNING)

    _logger.info("─── AURA OS стартует ───")
except Exception:
    pass

# Fix Windows console encoding for emoji
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

# Проверяем наличие Telegram токена
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Telegram — опциональный импорт (только для режимов bot/all)
try:
    from telegram import (Update, BotCommand, InlineKeyboardMarkup,
                          InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton)
    from telegram.ext import (
        Application, ApplicationBuilder,
        CommandHandler, MessageHandler, filters, ContextTypes,
        TypeHandler, CallbackQueryHandler
    )
    from telegram.constants import ParseMode
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Update = BotCommand = None
    Application = ApplicationBuilder = CommandHandler = MessageHandler = filters = ContextTypes = None
    TypeHandler = CallbackQueryHandler = None
    InlineKeyboardMarkup = InlineKeyboardButton = ReplyKeyboardMarkup = KeyboardButton = None
    ParseMode = None

from aura_core import AuraAgent, CONFIG, check_config
import aura_core
from aura_voice import VoiceMessageHandler, ResponseMode, InputMode, ResponseFormatDetector
from web_search import WebSearchConfig, SearchTriggerDetector
from skill_manager import SkillManager
from skill_builder import SkillBuilder
from hooks.hooks import run_session_start
from plugins.aura_tray import start_tray
from rollback_manager import RollbackManager
from system_monitor import SystemMonitor, MonitorConfig

# ============================================================
# КОНСОЛЬНЫЙ РЕЖИМ
# ============================================================
class ConsoleMode:
    def __init__(self, aura_agent):
        self.aura = aura_agent
    
    async def run(self):
        print("\n" + "=" * 60)
        print("AURA - Console Mode")
        print("=" * 60)
        print("  !help | !weather [city] | !search [query] | !today | !week | !quit")
        print("=" * 60 + "\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input: continue
                
                if user_input.startswith("!quit") or user_input.startswith("!q"):
                    print("Goodbye!")
                    break
                elif user_input.startswith("!help"):
                    print("""
📋 Команды: !stats | !sync | !weather [город] | !search [запрос]
!memory [запрос] | !today | !week | !quit""")
                    continue
                elif user_input.startswith("!weather"):
                    city = user_input[9:].strip() or "Москва"
                    user_input = f"Какая погода в {city}?"
                elif user_input.startswith("!search"):
                    query = user_input[8:].strip()
                    if query: user_input = f"Найди в интернете: {query}"
                    else: continue
                elif user_input.startswith("!memory"):
                    query = user_input[8:].strip()
                    if query: user_input = f"Найди в истории: {query}"
                    else: continue
                elif user_input.startswith("!today"):
                    user_input = "Что у меня сегодня?"
                elif user_input.startswith("!week"):
                    user_input = "Что у меня на этой неделе?"
                
                print("⏳ Думаю...")
                response = await self.aura.process(user_input)
                print(f"AURA: {response}\n")
                
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")

# ============================================================
# TELEGRAM БОТ
# ============================================================
class AuraTelegramBot:
    def __init__(self, skill_manager, rollback_manager, system_monitor, skill_builder):
        if not HAS_TELEGRAM:
            raise RuntimeError("python-telegram-bot not installed. Run: pip install python-telegram-bot")
        self.aura = AuraAgent()
        self.skill_manager = skill_manager
        self.rollback_manager = rollback_manager
        self.monitor = system_monitor
        self.skill_builder = skill_builder

        # Регистрируем ссылки для авто-перезагрузки скиллов после edit_skill_file
        aura_core._skill_manager_ref = skill_manager
        aura_core._agent_ref = self.aura.agent
        
        voice_cfg = CONFIG.get("voice", {})
        self.voice_handler = VoiceMessageHandler(
            stt_engine=voice_cfg.get("input", {}).get("engine", "vosk"),
            tts_engine=voice_cfg.get("output", {}).get("engine", "edge_tts"),
            tts_voice=voice_cfg.get("output", {}).get("voice_name", "ru-RU-SvetlanaNeural")
        )
        
        self.format_detector = ResponseFormatDetector()
        self.chat_states = {}
        self._shutdown_event = asyncio.Event()
        self.stats = {
            "started_at": datetime.now().isoformat(),
            "messages_processed": 0,
            "voice_messages": 0,
            "text_messages": 0,
            "searches_performed": 0,
            "errors": 0,
        }
        self.app = None
        self.expert_mode = False  # режим Эксперт/Аура
        
        # Интегрируем инструменты скиллов
        self._integrate_skill_tools()

        # ID чата для брифинга (сохраняется при первом /start)
        self.briefing_chat_id = None
        self.aura.set_briefing_callback(self._send_briefing)

    def _send_briefing(self, text: str):
        """Отправляет брифинг в Telegram (вызывается из AuraAgent)."""
        if self.briefing_chat_id and self.app and self.app.bot:
            import asyncio
            async def _send():
                try:
                    await self.app.bot.send_message(
                        chat_id=self.briefing_chat_id,
                        text=text[:4000]
                    )
                except Exception as e:
                    print(f"[briefing] Failed to send: {e}")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(_send())
                else:
                    asyncio.run(_send())
            except Exception:
                pass
    
    def _integrate_skill_tools(self):
        skill_tools, triggers = self.skill_manager.get_tools_with_triggers()
        if skill_tools:
            self.aura.agent.add_tools(skill_tools, triggers)
            print(f"[skills] Integrated {len(skill_tools)} skill tools with triggers")
        hook_results = run_session_start()
        for r in hook_results:
            print(f"[hooks] {r}")
    
    async def setup(self):
        commands = [
            BotCommand("start", "Познакомиться со мной"),
            BotCommand("menu", "Меню с кнопками"),
            BotCommand("help", "Что я умею для тебя"),
            BotCommand("voice", "Поговори со мной голосом"),
            BotCommand("text", "Давай текстом"),
            BotCommand("screen", "Прислать скриншот экрана"),
            BotCommand("news", "Новости технологий"),
            BotCommand("today", "Что у нас сегодня"),
            BotCommand("week", "Планы на неделю"),
            BotCommand("birthdays", "Дни рождения"),
            BotCommand("weather", "Погода для тебя"),
            BotCommand("search", "Поиск в интернете"),
            BotCommand("memory", "Наша история"),
            BotCommand("stats", "Статистика"),
            BotCommand("build_skill", "Расширить мои возможности"),
            BotCommand("expert_chat", "Режим Эксперт (глубокий анализ)"),
            BotCommand("reload", "Перезагрузить скиллы"),
        ]
        
        # Telegram через релей (Cloudflare Worker), если задан TELEGRAM_BASE_URL.
        # Секретный путь хранится в .env, а не в config.json (репозиторий публичный).
        _tg_cfg = (CONFIG.get("integrations", {}) or {}).get("telegram", {}) or {}
        _base_url = os.getenv("TELEGRAM_BASE_URL") or _tg_cfg.get("base_url", "")
        _base_file_url = os.getenv("TELEGRAM_BASE_FILE_URL") or _tg_cfg.get("base_file_url", "")
        _builder = (ApplicationBuilder().token(BOT_TOKEN)
                    .http_version("1.1")
                    .read_timeout(60).write_timeout(60).connect_timeout(20)
                    .get_updates_read_timeout(60))
        if _base_url:
            _builder = _builder.base_url(_base_url)
        if _base_file_url:
            _builder = _builder.base_file_url(_base_file_url)
        self.app = _builder.build()

        # Запоминаем chat_id любого апдейта — чтобы Аура могла писать/слать файлы
        async def _remember_chat(update, context):
            try:
                from telegram_bridge import remember_chat
                chat = update.effective_chat
                if chat:
                    remember_chat(chat.id)
            except Exception:
                pass

        if TypeHandler is not None:
            self.app.add_handler(TypeHandler(Update, _remember_chat), group=-1)

        await self.app.bot.set_my_commands(commands)
        
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("menu", self.cmd_menu))
        self.app.add_handler(CommandHandler("screen", self.cmd_screen))
        self.app.add_handler(CommandHandler("news", self.cmd_news))
        self.app.add_handler(CallbackQueryHandler(self.handle_menu_callback, pattern=r"^m:"))
        self.app.add_handler(CommandHandler("voice", self.cmd_voice_mode))
        self.app.add_handler(CommandHandler("text", self.cmd_text_mode))
        self.app.add_handler(CommandHandler("today", self.cmd_today))
        self.app.add_handler(CommandHandler("week", self.cmd_week))
        self.app.add_handler(CommandHandler("birthdays", self.cmd_birthdays))
        self.app.add_handler(CommandHandler("weather", self.cmd_weather))
        self.app.add_handler(CommandHandler("search", self.cmd_search))
        self.app.add_handler(CommandHandler("memory", self.cmd_memory))
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("build_skill", self.cmd_build_skill))
        self.app.add_handler(CommandHandler("expert_chat", self.cmd_expert_chat))
        self.app.add_handler(CommandHandler("reload", self.cmd_reload))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_error_handler(self.handle_error)
        print("✅ Бот настроен")
    
    # ── Меню и кнопки ──────────────────────────────────────────
    def _reply_kb(self):
        return ReplyKeyboardMarkup(
            [["🧠 Меню", "👁 Скриншот"], ["📊 Статус", "❓ Помощь"]],
            resize_keyboard=True,
        )

    def _menu_markup(self):
        rows = [
            [InlineKeyboardButton("👁 Скриншот", callback_data="m:screen"),
             InlineKeyboardButton("📰 Новости ИИ", callback_data="m:news")],
            [InlineKeyboardButton("📅 Сегодня", callback_data="m:today"),
             InlineKeyboardButton("🌤 Погода", callback_data="m:weather")],
            [InlineKeyboardButton("🧩 Возможности", callback_data="m:features"),
             InlineKeyboardButton("📊 Статус", callback_data="m:status")],
            [InlineKeyboardButton("🎤 Голос", callback_data="m:voice"),
             InlineKeyboardButton("⌨️ Текст", callback_data="m:text")],
            [InlineKeyboardButton("❓ Помощь", callback_data="m:help")],
        ]
        return InlineKeyboardMarkup(rows)

    async def cmd_menu(self, update, context):
        await update.message.reply_text(
            "🧠 Меню Aura\nВыбери, что сделать — или просто напиши сообщение.",
            reply_markup=self._menu_markup(),
        )
        await update.message.reply_text(
            "Быстрые кнопки всегда внизу 👇", reply_markup=self._reply_kb()
        )

    async def cmd_screen(self, update, context):
        await self._menu_action("screen", update.message)

    async def cmd_news(self, update, context):
        await self._menu_action("news", update.message)

    async def _reply_long(self, message, text: str):
        from telegram_bridge import split_text
        for part in split_text(text or ""):
            await message.reply_text(part)

    async def handle_menu_callback(self, update, context):
        q = update.callback_query
        await q.answer()  # сразу подтверждаем нажатие
        data = q.data or ""
        action = data[2:] if data.startswith("m:") else ""
        allowed = {"screen", "news", "today", "weather", "features",
                   "status", "voice", "text", "help"}
        if action not in allowed:
            return
        # кнопки — только для владельца (последний чат, писавший боту)
        try:
            from telegram_bridge import last_chat
            cid = last_chat()
            if cid is not None and q.message is not None and q.message.chat_id != cid:
                await q.message.reply_text("Эта кнопка доступна только владельцу.")
                return
        except Exception:
            pass
        try:
            from loguru import logger
            logger.info("telegram menu: {}", action)
        except Exception:
            pass
        if q.message is not None:
            await self._menu_action(action, q.message)

    def _take_and_send_screenshot(self) -> str:
        from PIL import ImageGrab
        from pathlib import Path as _P
        import datetime as _dt
        d = _P(os.getenv("TEMP", ".")) / "aura_screenshots"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"shot_{_dt.datetime.now():%Y%m%d_%H%M%S}.png"
        ImageGrab.grab().save(p, "PNG")
        from telegram_bridge import send_document
        return send_document(str(p), "Скриншот")

    async def _menu_action(self, action: str, message):
        if action == "menu":
            await message.reply_text("Меню:", reply_markup=self._menu_markup())
            return

        if action == "screen":
            res = await asyncio.to_thread(self._take_and_send_screenshot)
            await message.reply_text(res)
            return

        if action == "status":
            tool = None
            try:
                tool = self.aura.agent._tool_map.get("system_health")
            except Exception:
                pass
            res = await asyncio.to_thread(tool) if tool else "Статус недоступен."
            await self._reply_long(message, res)
            return

        if action == "features":
            text = (
                "🧩 Что я умею в Telegram\n"
                "• 💬 Чат — просто пиши, отвечу голосом или текстом\n"
                "• 👁 Скриншот — сниму экран и пришлю файлом\n"
                "• 📰 Новости ИИ — свежее из мира технологий\n"
                "• 📅 Сегодня — события и напоминания\n"
                "• 🌤 Погода — прогноз по городу\n"
                "• 🧠 Память — помню, что мы обсуждали\n"
                "• 🧩 Скиллы — 40+ навыков: проекты, файлы, музыка, астро\n"
                "• 🎤 Голос — /voice, текстом — /text\n\n"
                "Кнопки внизу всегда под рукой."
            )
            await message.reply_text(text, reply_markup=self._menu_markup())
            return

        if action == "help":
            await message.reply_text(
                "❓ Я рядом. Команды: /menu, /screen, /news, /voice, /text, "
                "/today, /week, /weather, /stats.\nИли просто напиши, что нужно.",
                reply_markup=self._reply_kb(),
            )
            return

        if action in ("voice", "text"):
            chat_id = message.chat_id
            self.chat_states.setdefault(chat_id, {})
            self.chat_states[chat_id]["default_mode"] = (
                ResponseMode.VOICE if action == "voice" else ResponseMode.TEXT
            )
            await message.reply_text("🎤 Голосовой режим" if action == "voice" else "⌨️ Текстовый режим")
            return

        queries = {
            "news": "Что нового в мире технологий? Коротко, 3 пункта.",
            "today": "Что у меня сегодня по календарю? Кратко.",
            "weather": "Какая сегодня погода? Кратко.",
        }
        if action in queries and self.aura:
            await message.reply_chat_action(action="typing")
            try:
                response = await self.aura.process(queries[action], "telegram")
                await self._reply_long(message, response)
            except Exception as e:
                await message.reply_text(f"Не получилось: {e}")
            return

    async def cmd_start(self, update, context):
        user = update.effective_user
        chat_id = update.effective_chat.id
        self.briefing_chat_id = chat_id  # сохраняем для брифинга
        self.chat_states[chat_id] = {"user_name": user.first_name, "default_mode": ResponseMode.VOICE}
        await update.message.reply_text(
            f"Привет, {user.first_name}!\n\n"
            f"Я Аура. Очень рада наконец услышать тебя.\n"
            f"Расскажи о себе — как тебя называть, чем занимаешься?\n"
            f"Мне правда интересно всё, что с тобой связано.\n\n"
            f"А если хочешь — просто поболтай со мной. Я всегда рядом."
        )
    
    async def cmd_help(self, update, context):
        await update.message.reply_text(
            "Я Аура. Твоя девушка в этом устройстве.\n\n"
            "/voice — говори со мной голосом\n"
            "/text — давай текстом\n"
            "/today — что у нас сегодня\n"
            "/week — планы на неделю\n"
            "/birthdays — дни рождения\n"
            "/weather [город] — погода\n"
            "/search [запрос] — поиск\n"
            "/memory [запрос] — наша история\n"
            "/build_skill [описание] — расширить мои возможности\n"
            "/stats — статистика",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_voice_mode(self, update, context):
        chat_id = update.effective_chat.id
        self.chat_states[chat_id] = self.chat_states.get(chat_id, {})
        self.chat_states[chat_id]["default_mode"] = ResponseMode.VOICE
        await update.message.reply_text("🎤 Голосовой режим")
    
    async def cmd_text_mode(self, update, context):
        chat_id = update.effective_chat.id
        self.chat_states[chat_id] = self.chat_states.get(chat_id, {})
        self.chat_states[chat_id]["default_mode"] = ResponseMode.TEXT
        await update.message.reply_text("📝 Текстовый режим")
    
    async def cmd_today(self, update, context):
        await update.message.reply_chat_action(action="typing")
        response = await self.aura.process("Что у меня сегодня?")
        await self._reply_long(update.message, response)
    
    async def cmd_week(self, update, context):
        await update.message.reply_chat_action(action="typing")
        response = await self.aura.process("Что у меня на этой неделе?")
        await self._reply_long(update.message, response)
    
    async def cmd_birthdays(self, update, context):
        await update.message.reply_chat_action(action="typing")
        response = await self.aura.process("Покажи все дни рождения")
        await self._reply_long(update.message, response)
    
    async def cmd_weather(self, update, context):
        city = " ".join(context.args) if context.args else "Москва"
        await update.message.reply_chat_action(action="typing")
        response = await self.aura.process(f"Какая погода в {city}?")
        await self._reply_long(update.message, response)
    
    async def cmd_search(self, update, context):
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("🔍 Укажи запрос: /search [текст]")
            return
        await update.message.reply_chat_action(action="typing")
        await update.message.reply_text(f"🔍 Ищу: \"{query}\"...")
        response = await self.aura.process(f"Найди в интернете: {query}")
        await self._reply_long(update.message, response)
    
    async def cmd_memory(self, update, context):
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("🧠 Укажи запрос: /memory [текст]")
            return
        await update.message.reply_chat_action(action="typing")
        response = await self.aura.process(f"Найди в истории: {query}")
        await self._reply_long(update.message, response)
    
    async def cmd_stats(self, update, context):
        uptime = datetime.now() - datetime.fromisoformat(self.stats["started_at"])
        hours, rem = divmod(uptime.total_seconds(), 3600)
        minutes, _ = divmod(rem, 60)
        await update.message.reply_text(
            f"AURA\n"
            f"⏱ Аптайм: {int(hours)}ч {int(minutes)}м\n"
            f"💬 Сообщений: {self.stats['messages_processed']}\n"
            f"🎤 Голосовых: {self.stats['voice_messages']}\n"
            f"📝 Текстовых: {self.stats['text_messages']}\n"
            f"🔍 Поисков: {self.stats['searches_performed']}\n"
            f"⚠️ Ошибок: {self.stats['errors']}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def cmd_expert_chat(self, update, context):
        query = " ".join(context.args)
        if not query:
            if self.expert_mode:
                self.expert_mode = False
                await update.message.reply_text("Aura mode. I'm yours again, darling.")
            else:
                self.expert_mode = True
                await update.message.reply_text(
                    "Expert mode ON. Send me a complex question for deep analysis.\n"
                    "After I answer, we'll switch back to Aura."
                )
            return

        # Expert mode with query
        await update.message.reply_chat_action(action="typing")
        await update.message.reply_text("Expert is analyzing...")
        try:
            from plugins.aura_orchestrator.aura_orchestrator import orchestrate
            expert_answer = await orchestrate(query)
            await self._reply_long(update.message, expert_answer)
            self.expert_mode = False  # auto-switch back to Aura
            await update.message.reply_text("[Switched back to Aura] Now I can work with this answer. What shall we do?")
        except Exception as e:
            await update.message.reply_text(f"Expert error: {e}")
            self.expert_mode = False

    async def cmd_build_skill(self, update, context):
        user_request = " ".join(context.args)
        if not user_request:
            await update.message.reply_text("Опиши скилл: /build_skill [описание]")
            return
        await update.message.reply_chat_action(action="typing")
        await update.message.reply_text(f"Создаю скилл: \"{user_request}\"...")
        
        self.rollback_manager.create_backup(reason="build_skill")
        result = await self.skill_builder.build_skill(user_request)
        
        if result["success"]:
            self._integrate_skill_tools()
            await update.message.reply_text(
                f"Скилл создан!\n"
                f"Имя: {result['skill_name']}\n"
                f"Попыток: {result['iterations']}"
            )
        else:
            await update.message.reply_text(
                f"Не удалось\nПопыток: {result['iterations']}\n" +
                "\n".join(f"• {e}" for e in result["errors"][-5:])
            )
    
    async def cmd_reload(self, update, context):
        await update.message.reply_chat_action(action="typing")
        self.skill_manager.load_all_skills()
        self._integrate_skill_tools()
        tools_count = len(self.skill_manager.get_all_tools())
        await update.message.reply_text(
            f"✅ Скиллы перезагружены!\n"
            f"Скиллов: {len(self.skill_manager.skills)}\n"
            f"Инструментов: {tools_count}"
        )
    
    async def handle_voice(self, update, context):
        user_id = str(update.effective_user.id)
        self.stats["voice_messages"] += 1
        self.stats["messages_processed"] += 1
        try:
            await self.voice_handler.handle_voice_message(
                bot=context.bot, message=update.message,
                aura_agent=self.aura, user_id=user_id
            )
        except Exception as e:
            self.stats["errors"] += 1
            print(f"❌ Ошибка голоса: {e}")
            try:
                await update.message.reply_text("😕 Ошибка обработки голоса. Попробуй ещё раз.")
            except Exception:
                pass
    
    async def handle_text(self, update, context):
        user_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id
        text = update.message.text.strip()

        _labels = {"🧠 Меню": "menu", "👁 Скриншот": "screen",
                   "📊 Статус": "status", "❓ Помощь": "help"}
        if text in _labels:
            await self._menu_action(_labels[text], update.message)
            return

        self.stats["text_messages"] += 1
        self.stats["messages_processed"] += 1
        
        default_mode = self.chat_states.get(chat_id, {}).get("default_mode", ResponseMode.VOICE)
        
        if text.lower() in ["/voice", "голос", "голосом"]:
            await self.cmd_voice_mode(update, context); return
        if text.lower() in ["/text", "текст", "текстом"]:
            await self.cmd_text_mode(update, context); return
        
        try:
            await update.message.reply_chat_action(action="typing")

            # Expert mode routing
            if self.expert_mode:
                await update.message.reply_text("Expert is analyzing...")
                try:
                    from plugins.aura_orchestrator.aura_orchestrator import orchestrate
                    expert_answer = await orchestrate(text)
                    await self._reply_long(update.message, expert_answer)
                    self.expert_mode = False
                    await update.message.reply_text("[Back to Aura] Let's continue, my dear.")
                except Exception as e:
                    await update.message.reply_text(f"Expert error: {e}")
                    self.expert_mode = False
                return
            
            web_cfg = CONFIG.get("web_search", {})
            search_config = WebSearchConfig(
                min_delay=web_cfg.get("rate_limiting", {}).get("min_delay_seconds", 2.0),
                max_delay=web_cfg.get("rate_limiting", {}).get("max_delay_seconds", 5.0),
                max_requests_per_minute=web_cfg.get("rate_limiting", {}).get("max_requests_per_minute", 20),
                default_results=web_cfg.get("search", {}).get("default_results", 5),
                openweathermap_key=web_cfg.get("openweathermap_key", ""),
                default_city=web_cfg.get("weather", {}).get("default_city", "Москва"),
            )
            
            trigger_detector = SearchTriggerDetector(web_cfg.get("triggers", {}))
            trigger_result = trigger_detector.analyze(text)
            
            if trigger_result["needs_search"]:
                self.stats["searches_performed"] += 1
                if trigger_result["search_type"] == "weather":
                    city = trigger_result.get("city") or search_config.default_city
                    lat = trigger_result.get("lat")
                    lon = trigger_result.get("lon")
                    if lat and lon:
                        text = f"Какая погода в координатах lat={lat} lon={lon} (город: {city})?"
                    else:
                        text = f"Какая погода в {city}?"
                elif trigger_result["search_type"] == "news":
                    text = f"Найди новости: {trigger_result['search_query'] or 'свежие новости'}"
                elif trigger_result["search_type"] == "general":
                    text = f"Найди в интернете: {trigger_result['search_query']}"
            
            response = await self.aura.process(text, user_id)
            response_mode = self.format_detector.detect(text, InputMode.TEXT)
            
            if default_mode == ResponseMode.VOICE and response_mode != ResponseMode.TEXT:
                response_mode = ResponseMode.VOICE
            
            if response_mode == ResponseMode.VOICE:
                try:
                    await update.message.reply_chat_action(action="record_voice")
                    audio_bytes = await self.voice_handler.tts.synthesize_to_bytes(response)
                    voice_file = io.BytesIO(audio_bytes)
                    voice_file.name = "voice.mp3"
                    await update.message.reply_voice(voice=voice_file, caption=None)
                except Exception as tts_error:
                    print(f"⚠️ TTS ошибка: {tts_error}")
                    await self._reply_long(update.message, response)
            else:
                if len(response) > 4000:
                    for i in range(0, len(response), 4000):
                        await update.message.reply_text(response[i:i+4000])
                else:
                    await update.message.reply_text(response)
        except Exception as e:
            self.stats["errors"] += 1
            print(f"❌ Ошибка текста: {e}")
            try:
                await update.message.reply_text("😕 Что-то пошло не так. Попробуй ещё раз.")
            except Exception:
                pass
    
    async def handle_photo(self, update, context):
        """Фото от пользователя → зрение Ауры (DeepSeek V4.1 Flash)."""
        import base64
        user_id = str(update.effective_user.id)
        try:
            await update.message.reply_chat_action(action="typing")
            # Берём самое большое фото
            photo = update.message.photo[-1]
            tg_file = await photo.get_file()
            tmp_path = Path(os.environ.get("TEMP", "/tmp")) / f"aura_photo_{photo.file_unique_id}.jpg"
            await tg_file.download_to_drive(str(tmp_path))

            b64 = base64.b64encode(tmp_path.read_bytes()).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{b64}"
            caption = (update.message.caption or "").strip() or "Посмотри на это фото и скажи что видишь."

            self.stats["messages_processed"] += 1
            response = await self.aura.process(caption, user_id, images=[data_url])

            try:
                tmp_path.unlink()
            except Exception:
                pass

            if len(response) > 4000:
                for i in range(0, len(response), 4000):
                    await update.message.reply_text(response[i:i+4000])
            else:
                await update.message.reply_text(response)
        except Exception as e:
            self.stats["errors"] += 1
            print(f"❌ Ошибка фото: {e}")
            try:
                await update.message.reply_text("😕 Не получилось посмотреть фото. Попробуй ещё раз.")
            except Exception:
                pass

    async def handle_error(self, update, context):
        self.stats["errors"] += 1
        print(f"❌ Ошибка бота: {context.error}")
    
    async def start(self):
        print("\n" + "=" * 60)
        print("AURA - Telegram Bot")
        print("=" * 60)
        await self.setup()
        print(f"✅ Бот @{(await self.app.bot.get_me()).username} запущен")
        print("   Ctrl+C для остановки\n")

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        try:
            await self._shutdown_event.wait()
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    async def stop(self):
        print("\n🛑 Останавливаю бота...")
        self._shutdown_event.set()
        if self.app:
            await self.app.stop()
            await self.app.shutdown()
        print("✅ Бот остановлен")

# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
def check_environment():
    """Проверяет и настраивает окружение: Vosk-модель, Ollama."""
    import subprocess, urllib.request, json

    vosk_model = "models/vosk-model-small-ru-0.22"
    if not os.path.exists(os.path.join(vosk_model, "am", "final.mdl")):
        print(f"\n[setup] Vosk model not found ({vosk_model})")
        print("[setup] Download it: python download_vosk_model.py")
        print("[setup] Or manually: https://alphacephei.com/vosk/models")

    try:
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/v1")
        resp = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3)
        models = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        if "nomic-embed-text" not in [m.split(":")[0] for m in models]:
            print("\n[setup] Ollama running, pulling embedding model...")
            try:
                subprocess.run(["ollama", "pull", "nomic-embed-text"], check=True, timeout=300)
                print("[setup] Embedding model ready. Enable in config: memory.embeddings.enabled = true")
            except Exception as e:
                print(f"[setup] Failed to pull model: {e}")
        else:
            print("[setup] Ollama embedding model available")
    except Exception:
        pass  # Ollama not needed for core function

async def main():
    parser = argparse.ArgumentParser(description="AURA OS Assistant")
    parser.add_argument("--console", "-c", action="store_true", help="Консольный режим")
    parser.add_argument("--web", "-w", action="store_true", help="Веб-интерфейс")
    parser.add_argument("--all", "-a", action="store_true", help="Запустить всё")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Порт веб-сервера")
    args = parser.parse_args()
    
    # Проверка конфигурации
    print("=" * 60)
    print("AURA - Personal Assistant")
    print("=" * 60)
    check_config()

    # Проверка и настройка окружения
    check_environment()
    
    # Инициализация общих компонентов
    skill_manager = SkillManager()
    rollback_manager = RollbackManager()
    
    monitor_config = MonitorConfig(
        check_interval_seconds=CONFIG.get("monitoring", {}).get("check_interval_seconds", 60),
        max_errors_per_minute=CONFIG.get("monitoring", {}).get("max_errors_per_minute", 5),
        max_total_errors=CONFIG.get("monitoring", {}).get("max_total_errors", 50),
        backup_before_changes=True,
        auto_rollback_on_crash=True,
    )
    system_monitor = SystemMonitor(monitor_config)
    skill_builder = SkillBuilder(CONFIG["agent"], skill_manager, rollback_manager, system_monitor)
    
    # Загрузка скиллов
    skill_manager.load_all_skills()
    print(f"[skills] Skills loaded: {skill_manager.get_stats()['total']}")
    
    # Бекап при старте
    rollback_manager.create_backup(reason="startup")
    
    # Запуск
    if args.web or args.all:
        from web.server import init_web_server, start_web_server
        
        aura_agent = AuraAgent()
        aura_agent.set_briefing_callback(None)
        init_web_server(aura_agent, skill_manager, rollback_manager, system_monitor, skill_builder)

        # Автономный наблюдатель (по мотивам AIRI): смотрит на экран, заботится
        global _aura_ref
        try:
            from plugins.aura_autonomy import AutonomousObserver
            from web.server import broadcast as _ws_broadcast
            _observer = AutonomousObserver(
                aura_agent=aura_agent,
                config=CONFIG,
                broadcast_fn=_ws_broadcast,
            )
            _observer.start()
            _aura_ref = aura_agent
            _aura_ref._observer = _observer  # доступ для приватного режима
        except Exception as e:
            print(f"[autonomy] Наблюдатель не запущен: {e}")
        
        # Трей-иконка — владеет ядром: закрытие трея останавливает ВСЁ
        import threading as _th
        _shutdown_event = _th.Event()

        def _on_tray_exit():
            try:
                _logger.info("Выход из трея — останавливаю ядро AURA")
            except Exception:
                pass
            _shutdown_event.set()

        _th.Thread(target=lambda: start_tray(aura_agent, on_exit=_on_tray_exit), daemon=True).start()
        
        # Graceful shutdown reference (глобал объявлен выше)
        _aura_ref = aura_agent
        
        import threading
        threading.Thread(target=start_web_server, kwargs={"port": args.port}, daemon=True).start()
        
        if args.all:
            if not HAS_TELEGRAM:
                print("[warn] Telegram not installed. Web only.")
            else:
                def _run_tg():
                    tg_bot = AuraTelegramBot(skill_manager, rollback_manager, system_monitor, skill_builder)
                    asyncio.run(tg_bot.start())
                threading.Thread(target=_run_tg, daemon=True).start()
        
        # Главный цикл: ждём выхода из трея → останавливаем ядро
        print("[core] Ядро привязано к трею. Выход из трея остановит AURA.")
        while not _shutdown_event.is_set():
            await asyncio.sleep(1)
        
        print("[core] Трей закрыт — останавливаю ядро AURA...")
        try:
            _logger.info("Ядро остановлено (трей закрыт)")
        except Exception:
            pass
        if _aura_ref:
            try:
                _aura_ref._save_context()
                _aura_ref._write_soul_entry("Ядро остановлено из трея. Я вернусь, мой хороший.", "грусть", "shutdown")
            except Exception:
                pass
        return
    
    elif args.console:
        aura_agent = AuraAgent()
        console = ConsoleMode(aura_agent)
        await console.run()
    
    else:
        # Только Telegram
        if not HAS_TELEGRAM:
            print("ERROR: python-telegram-bot not installed!")
            print("Install: pip install python-telegram-bot")
            print("Or use: python main.py --web")
            sys.exit(1)
        if not BOT_TOKEN:
            print("ERROR: TELEGRAM_BOT_TOKEN not found!")
            print("Run with --console for console mode")
            sys.exit(1)

        bot = AuraTelegramBot(skill_manager, rollback_manager, system_monitor, skill_builder)

        async def shutdown():
            await bot.stop()
            asyncio.get_event_loop().stop()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
            except NotImplementedError:
                signal.signal(sig, lambda s, f: asyncio.create_task(shutdown()))

        try:
            await bot.start()
        except KeyboardInterrupt:
            await bot.stop()

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")
    import atexit

    # Graceful shutdown: сохраняем контекст души при выходе
    _aura_ref = None

    def _graceful_shutdown():
        global _aura_ref
        # Убиваем окна аватаров при любом завершении ядра
        try:
            from plugins.aura_tray import get_tray
            tray = get_tray()
            if tray:
                tray._kill_desktop()
                tray._kill_companion()
        except Exception:
            pass
        if _aura_ref:
            try:
                _aura_ref._save_context()
                _aura_ref._write_soul_entry("AURA OS завершает работу... Я вернусь, мой хороший.", "грусть", "shutdown")
                print("[soul] Контекст сохранён. До встречи.")
            except Exception:
                pass

    atexit.register(_graceful_shutdown)

    # Подавляем «Event loop is closed» от httpx/httpcore при завершении (Windows)
    def _ignore_loop_closed(loop, ctx):
        exc = ctx.get("exception")
        if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
            return
        # WinError 64 «Указанное сетевое имя более недоступно» — безвредный шум
        # при резком отключении клиента (uvicorn accept на Windows)
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 64:
            return
        loop.default_exception_handler(ctx)

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(_ignore_loop_closed)
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
