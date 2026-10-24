"""
Configuration loader. Reads from .env file and environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class Config:
    # --- Telegram ---
    tg_bot_token: str = ""
    tg_channel_id: str = ""        # @channel_username or -100xxx
    tg_admin_ids: List[int] = field(default_factory=list)
    tg_posting_interval_hours: int = 3   # post every N hours
    tg_ad_message_hour: int = 10         # send ad at this hour (UTC)
    
    # --- ePN.bz ---
    epn_api_key: str = ""
    epn_user_id: str = ""
    
    # --- Admitad ---
    admitad_client_id: str = ""
    admitad_client_secret: str = ""
    
    # --- Leadgid ---
    leadgid_api_token: str = ""
    
    # --- NewsAPI ---
    news_api_key: str = ""
    news_topics: List[str] = field(default_factory=lambda: [
        "технологии", "финансы", "бизнес", "скидки"
    ])
    
    # --- RSS Feeds ---
    rss_feeds: List[str] = field(default_factory=lambda: [
        "https://lenta.ru/rss",
        "https://ria.ru/export/rss2/archive/index.xml",
    ])
    
    # --- AI Content (Gemini - free tier) ---
    gemini_api_key: str = ""
    
    # --- Scheduler ---
    check_new_offers_interval_hours: int = 6
    analytics_report_hour: int = 20
    
    # --- Limits ---
    max_subscribers_for_ads: int = 0  # 0 = unlimited, >0 = only send ads if subscribers > X

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "Config":
        """
        Load config from .env file and environment variables.
        Environment variables override .env values.
        """
        # Try to load .env file
        if env_file is None:
            env_file = Path(__file__).parent / ".env"
        
        if Path(env_file).exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        # Strip quotes
                        value = value.strip().strip('"').strip("'")
                        # Only set if not already in environment
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = value
        
        def _get_int(key: str, default: int = 0) -> int:
            val = os.environ.get(key, "")
            return int(val) if val else default
        
        def _get_list_int(key: str) -> List[int]:
            val = os.environ.get(key, "")
            if not val:
                return []
            return [int(x.strip()) for x in val.split(",") if x.strip()]
        
        def _get_list_str(key: str, default: List[str]) -> List[str]:
            val = os.environ.get(key, "")
            if not val:
                return default
            return [x.strip() for x in val.split(",") if x.strip()]
        
        return cls(
            tg_bot_token=os.environ.get("TG_BOT_TOKEN", ""),
            tg_channel_id=os.environ.get("TG_CHANNEL_ID", ""),
            tg_admin_ids=_get_list_int("TG_ADMIN_IDS"),
            tg_posting_interval_hours=_get_int("TG_POSTING_INTERVAL_HOURS", 3),
            tg_ad_message_hour=_get_int("TG_AD_MESSAGE_HOUR", 10),
            epn_api_key=os.environ.get("EPN_API_KEY", ""),
            epn_user_id=os.environ.get("EPN_USER_ID", ""),
            admitad_client_id=os.environ.get("ADMITAD_CLIENT_ID", ""),
            admitad_client_secret=os.environ.get("ADMITAD_CLIENT_SECRET", ""),
            leadgid_api_token=os.environ.get("LEADGID_API_TOKEN", ""),
            news_api_key=os.environ.get("NEWS_API_KEY", ""),
            news_topics=_get_list_str("NEWS_TOPICS", cls.news_topics),
            rss_feeds=_get_list_str("RSS_FEEDS", cls.rss_feeds),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            check_new_offers_interval_hours=_get_int("CHECK_NEW_OFFERS_INTERVAL_HOURS", 6),
            analytics_report_hour=_get_int("ANALYTICS_REPORT_HOUR", 20),
            max_subscribers_for_ads=_get_int("MAX_SUBSCRIBERS_FOR_ADS", 0),
        )


def validate_config(config: Config) -> List[str]:
    """Returns list of configuration errors. Empty list = valid."""
    errors = []
    
    # At least one monetization channel must be configured
    has_cpa = bool(config.epn_api_key or config.admitad_client_id or config.leadgid_api_token)
    has_telegram = bool(config.tg_bot_token)
    
    if not has_telegram:
        errors.append("TG_BOT_TOKEN is required — Telegram is the main distribution channel")
    
    if not has_cpa:
        errors.append("At least one CPA network API key is required (EPN_API_KEY, ADMITAD_CLIENT_ID, or LEADGID_API_TOKEN)")
    
    if config.tg_bot_token and not config.tg_channel_id:
        errors.append("TG_CHANNEL_ID is required when bot is enabled (for autoposting)")
    
    # Warnings (not errors)
    if not config.news_api_key and not config.rss_feeds:
        errors.append("Warning: No news sources configured (set NEWS_API_KEY or RSS_FEEDS)")
    
    if not config.gemini_api_key:
        errors.append("Warning: GEMINI_API_KEY not set — AI content generation disabled, will use RSS only")
    
    return errors
