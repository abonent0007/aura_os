"""Content generator — creates posts using AI (Gemini free tier) or templates."""

import logging
import random
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Ad templates for when AI is not available
AD_TEMPLATES = [
    "🔥 {title}\n\n{summary}\n\nУзнайте больше по ссылке ниже! 👇",
    "⚡ Только сегодня: {title}\n\n{summary}\n\nНе упусти выгоду! 🛍",
    "💎 Нашли для вас: {title}\n\n{summary}\n\nЖми на ссылку! ✨",
    "🎯 {title}\n\n{summary}\n\nЛучшее предложение дня! 🔥",
    "📦 {title}\n\n{summary}\n\nЗабирай пока в наличии! 🚀",
]

# Engagement hooks for channel posts
HOOKS = [
    "🔥 Вы только посмотрите:",
    "⚡ Срочная новость:",
    "💡 Обратите внимание:",
    "📌 Кстати:",
    "🤔 А вы знали?",
    "🚀 Интересный факт:",
    "✨ Детали:",
    "💬 Обсудим?",
]


class ContentGenerator:
    """Generates engaging posts for Telegram channel."""

    def __init__(self, gemini_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def generate_post(
        self,
        title: str,
        summary: str = "",
        cpa_link: str = "",
        use_ai: bool = True
    ) -> str:
        """
        Generate a Telegram post from news + CPA link.
        Falls back to templates if AI is unavailable.
        """
        if use_ai and self.gemini_api_key:
            ai_text = await self._generate_with_gemini(title, summary)
            if ai_text:
                return self._add_cpa_link(ai_text, cpa_link)

        # Fallback: use template
        template = random.choice(AD_TEMPLATES)
        post = template.format(title=title, summary=summary[:200] if summary else title)
        return self._add_cpa_link(post, cpa_link)

    async def generate_news_post(self, title: str, summary: str, source_url: str,
                                  cpa_link: str = "") -> str:
        """Generate a news-style post with optional CPA link."""
        hook = random.choice(HOOKS)
        post = f"{hook}\n\n<b>{title}</b>\n\n{summary[:250]}"

        if source_url:
            post += f"\n\n🔗 <a href='{source_url}'>Источник</a>"

        if cpa_link:
            post += f"\n\n💰 <a href='{cpa_link}'>Выгодное предложение дня</a>"
            post += "\n#реклама"

        return post

    async def _generate_with_gemini(self, title: str, summary: str) -> str:
        """Use Gemini API to generate an engaging post."""
        try:
            session = await self._get_session()
            prompt = (
                "Ты — редактор Telegram-канала со скидками и выгодными предложениями. "
                "Напиши короткий пост (3-5 предложений) о следующем товаре/новости. "
                "Стиль: дружелюбный, вовлекающий, с эмодзи. "
                "Не используй markdown, только простой текст и эмодзи.\n\n"
                f"Название: {title}\n"
                f"Описание: {summary[:300]}\n"
            )

            async with session.post(
                f"{GEMINI_API}?key={self.gemini_api_key}",
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                else:
                    logger.warning(f"Gemini API returned {resp.status}")
            return ""
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return ""

    def _add_cpa_link(self, text: str, cpa_link: str) -> str:
        """Append CPA link with proper ad labeling."""
        if not cpa_link:
            return text
        return f"{text}\n\n💰 <a href='{cpa_link}'>Посмотреть предложение</a>\n#реклама"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
