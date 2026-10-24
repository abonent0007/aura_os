"""ePN.bz API client — AliExpress partner network."""

import logging
import aiohttp
from typing import Optional
from cpa_base import BaseCPAClient, CPAOffer, CPAStats

logger = logging.getLogger(__name__)
EPN_API_BASE = "https://api.epn.bz/v2"


class EPNAPIClient(BaseCPAClient):
    """Client for ePN.bz partner API."""

    def __init__(self, api_key: str, user_id: str = ""):
        super().__init__(api_key)
        self.user_id = user_id
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
        return self._session

    async def get_offers(self, limit: int = 10) -> list[CPAOffer]:
        try:
            session = await self._get_session()
            async with session.get(
                f"{EPN_API_BASE}/products/top",
                params={"limit": limit, "lang": "ru"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_offers(data, limit)
                logger.warning(f"ePN API returned {resp.status}")
                return []
        except Exception as e:
            logger.error(f"ePN get_offers error: {e}")
            return []

    def _parse_offers(self, data: dict, limit: int) -> list[CPAOffer]:
        offers = []
        products = data.get("products", [])[:limit]
        for p in products:
            offers.append(CPAOffer(
                offer_id=str(p.get("id", "")),
                title=p.get("name", "Товар"),
                description=p.get("description", ""),
                category=p.get("category", ""),
                commission=float(p.get("commission", 0)),
                commission_type="%",
                url=p.get("url", ""),
                image_url=p.get("image", ""),
            ))
        return offers

    async def get_deep_link(self, offer_id: str, sub_id: str = "") -> str:
        try:
            session = await self._get_session()
            async with session.get(
                f"{EPN_API_BASE}/products/{offer_id}/deeplink",
                params={"sub_id": sub_id} if sub_id else {}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("deeplink", "")
                return ""
        except Exception as e:
            logger.error(f"ePN deep_link error: {e}")
            return ""

    async def get_stats(self, date_from: str = "", date_to: str = "") -> CPAStats:
        try:
            session = await self._get_session()
            params = {}
            if date_from:
                params["date_from"] = date_from
            if date_to:
                params["date_to"] = date_to
            async with session.get(f"{EPN_API_BASE}/stats", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return CPAStats(
                        clicks=data.get("clicks", 0),
                        conversions=data.get("sales", 0),
                        revenue=float(data.get("revenue", 0)),
                        currency="RUB",
                    )
                return CPAStats()
        except Exception as e:
            logger.error(f"ePN stats error: {e}")
            return CPAStats()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
