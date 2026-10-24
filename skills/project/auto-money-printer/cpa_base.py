"""Base class for CPA network API clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CPAOffer:
    """Represents a single offer from a CPA network."""
    offer_id: str
    title: str
    description: str = ""
    category: str = ""
    commission: float = 0.0
    commission_type: str = "%"
    url: str = ""
    deep_link: str = ""
    image_url: str = ""


@dataclass
class CPAStats:
    """Click and conversion stats."""
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    currency: str = "RUB"


class BaseCPAClient(ABC):
    """Abstract base for all CPA network clients."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None

    @abstractmethod
    async def get_offers(self, limit: int = 10) -> list[CPAOffer]:
        """Fetch available offers."""
        ...

    @abstractmethod
    async def get_deep_link(self, offer_id: str, sub_id: str = "") -> str:
        """Generate a deep link for an offer with tracking."""
        ...

    @abstractmethod
    async def get_stats(self, date_from: str = "", date_to: str = "") -> CPAStats:
        """Fetch click/conversion statistics."""
        ...

    def format_ad_post(self, offer: CPAOffer, custom_text: str = "") -> str:
        """Format an offer into a Telegram ad post with #реклама tag."""
        text = custom_text or f"🔥 {offer.title}\n\n{offer.description}"
        commission_str = f"{offer.commission}{offer.commission_type}"
        return (
            f"{text}\n\n"
            f"💰 Подробнее: {offer.deep_link or offer.url}\n"
            f"#реклама"
        )
