"""Telegram-бот — главный интерфейс взаимодействия с аудиторией.

Бесплатные функции для привлечения:
- /start — приветствие и подписка
- /weather — погода (через wttr.in, бесплатно)
- /currency — курс валют (через ЦБ РФ API, бесплатно)
- /joke — случайный анекдот
- /horoscope — гороскоп на сегодня

Монетизация: раз в день — рекламное сообщение с CPA-ссылкой.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Set
import aiohttp

logger = logging.getLogger(__name__)

# Lightweight bot implementation without python-telegram-bot dependency
# Uses raw Telegram API via aiohttp for maximum control

TG_API = "https://api.telegram.org"


class TelegramBot:
    """Autonomous Telegram bot with free utility functions and CPA ads."""

    def __init__(self, token: str, channel_id: str = "", admin_ids: set = None):
        self.token = token
        self.channel_id = channel_id
        self.admin_ids = admin_ids or set()
        self._session: Optional[aiohttp.ClientSession] = None
        # Track when each user last received an ad (anti-spam: max 1 ad/day per user)
        self._last_ad_sent: dict[int, datetime] = {}
        # Subscribers set
        self._subscribers: Set[int] = set()
        # Update offset for getUpdates
        self._update_offset: int = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _api_call(self, method: str, params: dict = None) -> dict:
        """Make a call to Telegram Bot API."""
        session = await self._get_session()
        url = f"{TG_API}/bot{self.token}/{method}"
        try:
            async with session.post(url, json=params or {}) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"Telegram API error ({method}): {e}")
            return {"ok": False, "error": str(e)}

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML",
                           disable_notification: bool = False) -> bool:
        """Send a message to a chat."""
        result = await self._api_call("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
            "disable_web_page_preview": False,
        })
        return result.get("ok", False)

    async def send_ad_to_subscriber(self, chat_id: int, ad_text: str) -> bool:
        """Send an ad to a subscriber (with anti-spam check)."""
        now = datetime.now()
        last = self._last_ad_sent.get(chat_id)
        if last and (now - last) < timedelta(hours=23):
            logger.debug(f"Skipping ad for {chat_id}: too soon")
            return False

        success = await self.send_message(chat_id, ad_text)
        if success:
            self._last_ad_sent[chat_id] = now
        return success

    async def broadcast_to_channel(self, text: str) -> bool:
        """Post a message to the configured channel."""
        if not self.channel_id:
            logger.warning("No channel_id configured, skipping post")
            return False
        return await self.send_message(self.channel_id, text)

    async def process_updates(self):
        """Process incoming updates (messages, commands). Non-blocking, called by scheduler."""
        try:
            params = {"timeout": 5, "limit": 10}
            if self._update_offset:
                params["offset"] = self._update_offset

            result = await self._api_call("getUpdates", params)
            if not result.get("ok"):
                return

            for update in result.get("result", []):
                self._update_offset = max(self._update_offset, update["update_id"] + 1)
                await self._handle_update(update)
        except Exception as e:
            logger.error(f"process_updates error: {e}")

    async def _handle_update(self, update: dict):
        """Handle a single update."""
        message = update.get("message", {})
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id", 0)
        text = message.get("text", "").strip()

        if not text or not chat_id:
            return

        # Track subscriber
        self._subscribers.add(chat_id)

        # Command handling
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            command = parts[0].lower()
            await self._handle_command(chat_id, command, parts[1] if len(parts) > 1 else "")

    async def _handle_command(self, chat_id: int, command: str, args: str):
        """Route commands to handlers."""
        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/weather": self._cmd_weather,
            "/currency": self._cmd_currency,
            "/joke": self._cmd_joke,
            "/horoscope": self._cmd_horoscope,
        }

        handler = handlers.get(command)
        if handler:
            try:
                await handler(chat_id, args)
            except Exception as e:
                logger.error(f"Command handler error ({command}): {e}")
                await self.send_message(chat_id, "😅 Что-то пошло не так. Попробуй позже!")

    async def _cmd_start(self, chat_id: int, args: str):
        user_name = args or "друг"
        await self.send_message(chat_id, (
            "👋 Привет! Я твой полезный помощник!\n\n"
            "Я умею:\n"
            "🌤 /weather — погода в любом городе\n"
            "💱 /currency — актуальные курсы валют\n"
            "🤣 /joke — случайный анекдот\n"
            "🔮 /horoscope — гороскоп на сегодня\n\n"
            "А ещё я делюсь выгодными предложениями и скидками! 🛍\n"
            "Оставайся на связи!"
        ))

    async def _cmd_help(self, chat_id: int, args: str):
        await self._cmd_start(chat_id, args)

    async def _cmd_weather(self, chat_id: int, args: str):
        city = args.strip() or "Москва"
        try:
            session = await self._get_session()
            # wttr.in — free weather API, no key needed
            url = f"https://wttr.in/{city}?format=%C+%t+%w+%h&lang=ru"
            async with session.get(url) as resp:
                weather_text = await resp.text()
                await self.send_message(chat_id, f"🌤 Погода в *{city}*:\n\n{weather_text.strip()}")
        except Exception as e:
            logger.error(f"Weather error: {e}")
            await self.send_message(chat_id, "😕 Не смогла получить погоду. Попробуй позже!")

    async def _cmd_currency(self, chat_id: int, args: str):
        """Get currency rates from Central Bank of Russia (free, no API key)."""
        try:
            session = await self._get_session()
            # ЦБ РФ API — бесплатно, без ключа
            async with session.get("https://www.cbr-xml-daily.ru/daily_json.js") as resp:
                data = await resp.json()
                valute = data.get("Valute", {})
                usd = valute.get("USD", {})
                eur = valute.get("EUR", {})
                cny = valute.get("CNY", {})

                msg = (
                    "💱 *Курсы валют ЦБ РФ*\n\n"
                    f"🇺🇸 USD: {usd.get('Value', '?')} ₽\n"
                    f"🇪🇺 EUR: {eur.get('Value', '?')} ₽\n"
                    f"🇨🇳 CNY: {cny.get('Value', '?')} ₽\n"
                    f"📅 Дата: {data.get('Date', '?')}"
                )
                await self.send_message(chat_id, msg)
        except Exception as e:
            logger.error(f"Currency error: {e}")
            await self.send_message(chat_id, "😕 Не смогла получить курсы валют. Попробуй позже!")

    async def _cmd_joke(self, chat_id: int, args: str):
        """Random joke — local collection, no API needed."""
        jokes = [
            "— Почему программисты путают Хэллоуин и Рождество?\n— Потому что Oct 31 == Dec 25! 🎃🎄",
            "— Какой любимый напиток у Python-разработчика?\n— Чай с лимоном и pip-ip-ip! 🐍",
            "— Почему Java-разработчики носят очки?\n— Потому что не могут C#! 👓",
            "— Что говорит один сервер другому?\n— Ты меня ping-понг заколебал! 💻",
            "— Почему ИИ не ходит в спортзал?\n— У него уже есть training data! 🏋️",
            "Решил как-то баг стать фичей... Теперь он на доске почёта! 🐛✨",
            "— Что сказал ноль восьмёрке?\n— Приятный пояс! ⌛",
            "— Почему книга по программированию грустила?\n— У неё было слишком много issues! 📚",
            "Встречаются два бита. Один говорит: «Я в депрессии». Второй: «Не парься, всё будет 0!»",
            "— Как называют программиста, который бросил пить кофе?\n— Без-кофе-ин! ☕",
        ]
        await self.send_message(chat_id, f"🤣 {random.choice(jokes)}")

    async def _cmd_horoscope(self, chat_id: int, args: str):
        """Daily horoscope — simple generator, no API needed."""
        signs = {
            "овен": "♈ Овен", "телец": "♉ Телец", "близнецы": "♊ Близнецы",
            "рак": "♋ Рак", "лев": "♌ Лев", "дева": "♍ Дева",
            "весы": "♎ Весы", "скорпион": "♏ Скорпион", "стрелец": "♐ Стрелец",
            "козерог": "♑ Козерог", "водолей": "♒ Водолей", "рыбы": "♓ Рыбы",
        }

        sign_input = args.strip().lower() if args else ""
        sign_emoji = signs.get(sign_input)
        if not sign_emoji:
            # List available signs
            signs_list = ", ".join(signs.keys())
            await self.send_message(chat_id, f"🔮 Укажи знак зодиака: /horoscope овен\n\nДоступные: {signs_list}")
            return

        predictions = [
            "Звёзды советуют сегодня быть смелее в решениях! Всё получится ✨",
            "День благоприятен для новых знакомств и общения. Не сиди дома! 🌟",
            "Возможны неожиданные поступления. Проверь уведомления! 💰",
            "Сегодня твоя интуиция на высоте — доверяй себе! 🔮",
            "Хороший день чтобы завершить старые дела и начать новые 🚀",
            "Звёзды говорят: отдохни, ты заслужил(а). Сделай паузу 🌙",
            "Будь осторожен(а) с обещаниями. Думай прежде чем говорить 🤔",
            "Творческая энергия зашкаливает — самое время для хобби! 🎨",
        ]

        today = datetime.now().strftime("%d.%m.%Y")
        await self.send_message(chat_id, (
            f"🔮 *Гороскоп на {today}*\n"
            f"{sign_emoji}\n\n"
            f"{random.choice(predictions)}"
        ))

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
