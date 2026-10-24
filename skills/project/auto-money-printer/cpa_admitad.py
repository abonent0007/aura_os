"""Admitad API client — крупнейшая CPA-сеть в России."""

import logging
import aiohttp
from typing import Optional
from cpa_base import BaseCPAClient, CPAOffer, CPAStats

logger = logging.getLogger(__name__)
ADMITAD_API_BASE = "https://api.admitad.com"


class AdmitadAPIClient(BaseCPAClient):
    """Client for Admitad partner API (OAuth2)."""

    def __init__(self, client_id: str, client_secret: str):
        super().__init__("")
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        try:
            import base64
            credentials = base64.b64encode(
                f"{self.client_id}:{self.client_secret}".encode()
            ).decode()
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ADMITAD_API_BASE}/token/",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials", "scope": "advcampaigns websites"}
                ) as resp:
                    data = await resp.json()
                    self._access_token = data.get("access_token", "")
                    return self._access_token
        except Exception as e:
            logger.error(f"Admitad auth error: {e}")
            return ""

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            token = await self._get_token()
            self._session = aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            })
        return self._session

    async def get_offers(self, limit: int = 10) -> list[CPAOffer]:
        try:
            session = await self._get_session()
            async with session.get(
                f"{ADMITAD_API_BASE}/advcampaigns/website/",
                params={"limit": limit, "language": "ru", "connection_status": "active"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._parse_offers(data, limit)
                logger.warning(f"Admitad API returned {resp.status}")
                return []
        except Exception as e:
            logger.error(f"Admitad get_offers error: {e}")
            return []

    def _parse_offers(self, data: dict, limit: int) -> list[CPAOffer]:
        offers = []
        results = data.get("results", [])[:limit]
        for item in results:
            offers.append(CPAOffer(
                offer_id=str(item.get("id", "")),
                title=item.get("name", "Программа"),
                description=item.get("description", ""),
                category=item.get("categories", [{}])[0].get("name", ""),
                commission=float(item.get("rate", 0)),
                commission_type=item.get("rate_unit", "%"),
                url=item.get("goto_url", ""),
            ))
        return offers

    async def get_deep_link(self, offer_id: str, sub_id: str = "") -> str:
        try:
            session = await self._get_session()
            async with session.post(
                f"{ADMITAD_API_BASE}/deeplink/{offer_id}/",
                json={"subid": sub_id} if sub_id else {}
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("deeplink", "")
                return ""
        except Exception as e:
            logger.error(f"Admitad deep_link error: {e}")
            return ""

    async def get_stats(self, date_from: str = "", date_to: str = "") -> CPAStats:
        try:
            session = await self._get_session()
            params = {}
            if date_from:
                params["date_start"] = date_from
            if date_to:
                params["date_end"] = date_to
            async with session.get(
                f"{ADMITAD_API_BASE}/statistics/actions/",
                params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [{}])[0]
                    return CPAStats(
                        clicks=results.get("clicks", 0),
                        conversions=results.get("actions", 0),
                        revenue=float(results.get("total", 0)),
                        currency="RUB",
                    )
                return CPAStats()
        except Exception as e:
            logger.error(f"Admitad stats error: {e}")
            return CPAStats()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
