# web_search.py
"""
Модуль интернет-поиска и погоды для AURA OS.
Поддерживает DuckDuckGo и OpenWeatherMap с защитой от блокировок.
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 1. КОНФИГУРАЦИЯ И ТРИГГЕРЫ
# ============================================================
@dataclass
class WebSearchConfig:
    """Конфигурация интернет-поиска"""
    
    # Rate limiting
    min_delay: float = 2.0
    max_delay: float = 5.0
    max_requests_per_minute: int = 20
    use_jitter: bool = True
    
    # Поиск
    default_results: int = 5
    max_results: int = 10
    region: str = "wt-wt"
    safe_search: str = "moderate"
    time_range: Optional[str] = None
    
    # Погода
    default_city: str = "Москва"
    weather_units: str = "metric"
    weather_lang: str = "ru"
    
    # API ключи
    openweathermap_key: str = ""
    newsapi_key: str = ""


class SearchTriggerDetector:
    """
    Определяет, что нужно искать в интернете, и что именно.
    """
    
    def __init__(self, config: dict = None):
        cfg = config or {}
        
        self.search_triggers = cfg.get("search", [])
        self.news_triggers = cfg.get("news", [])
        self.weather_triggers = cfg.get("weather", [])
    
    def analyze(self, text: str) -> dict:
        """
        Анализирует запрос и возвращает:
        - needs_search: bool
        - search_type: 'general' / 'news' / 'weather'
        - search_query: извлеченный запрос
        - city: город для погоды (если найдено)
        """
        text_lower = text.lower()
        result = {
            "needs_search": False,
            "search_type": None,
            "search_query": "",
            "city": None,
            "lat": None,
            "lon": None,
            "matched_triggers": []
        }
        
        # 1. Проверяем погоду (приоритетно — часто содержит город)
        weather_info = self._detect_weather(text_lower)
        if weather_info:
            result["needs_search"] = True
            result["search_type"] = "weather"
            result["city"] = weather_info["city"]
            result["lat"] = weather_info["lat"]
            result["lon"] = weather_info["lon"]
            result["matched_triggers"] = weather_info["triggers"]
            return result
        
        # 2. Проверяем новости
        news_hit = self._match_triggers(text_lower, self.news_triggers)
        if news_hit:
            result["needs_search"] = True
            result["search_type"] = "news"
            result["matched_triggers"] = news_hit
            result["search_query"] = self._extract_query(text, news_hit)
            return result
        
        # 3. Проверяем общий поиск
        search_hit = self._match_triggers(text_lower, self.search_triggers)
        if search_hit:
            result["needs_search"] = True
            result["search_type"] = "general"
            result["matched_triggers"] = search_hit
            result["search_query"] = self._extract_query(text, search_hit)
            return result
        
        return result
    
    def _match_triggers(self, text: str, triggers: list) -> list:
        """Поиск совпадений с триггерами"""
        matches = []
        for trigger in triggers:
            if trigger.lower() in text:
                matches.append(trigger)
        return matches
    
    def _detect_weather(self, text: str) -> Optional[dict]:
        """
        Определяет запрос погоды и извлекает город + координаты.
        """
        weather_triggers = [
            "погода", "температура", "осадки", "прогноз",
            "будет дождь", "будет снег", "ветер", "влажность",
            "брать зонт", "одевать", "потепление", "похолодание"
        ]

        matched = [t for t in weather_triggers if t in text]

        if not matched:
            if "погода" not in text:
                return None
            matched = ["погода"]

        # Извлекаем координаты если есть (55.451260° с.ш. и 38.442188° в.д.)
        lat, lon = self._extract_coordinates(text)

        # Извлекаем город
        city = None
        city_patterns = [
            r'(?:погода|прогноз).*?(?:в|для|на)\s+([\w\-\s]+?)(?:$|[.,!?;]|\s+(?:на|по|с|для|в|сегодня|завтра|недел|район|област|улиц|дом|я\s|там\s))',
            r'(?:в|для|на)\s+(?:город[еа]?|пос[ёе]л[кео][кеа]?)\s+([\w\-]+)',
            r'в\s+(?:городе|гор\.)\s+([\w\-]+)',
            r'(?:в|из)\s+([\w\-]+)\s+(?:погода|температура|прогноз)',
        ]

        for pattern in city_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                stop_words = {"сегодня", "завтра", "неделю", "будет", "есть", "там", "тут",
                              "московской", "московская", "района", "области", "улице", "улица", "дом"}
                if name.lower() not in stop_words and len(name) > 1:
                    city = name.capitalize()
                    break

        # Если координаты есть, город может быть не найден — используем координаты
        if not city and lat:
            city = None  # будет использован default_city

        forecast_date = "today"
        if "завтра" in text:
            forecast_date = "tomorrow"
        elif "недел" in text:
            forecast_date = "week"

        return {
            "triggers": matched,
            "city": city,
            "lat": lat,
            "lon": lon,
            "forecast_date": forecast_date
        }

    def _extract_coordinates(self, text: str) -> tuple:
        """Извлекает lat/lon из текста пользователя."""
        # Паттерн: 55.451260° с.ш. и 38.442188° в.д.
        coord_pattern = r'(\d{1,2}\.\d+)\s*°?\s*[сs]\.?\s*[шw]\.?\s*(?:и|,|&)?\s*(\d{1,2}\.\d+)\s*°?\s*[вe]\.?\s*[дd]\.?'
        match = re.search(coord_pattern, text, re.IGNORECASE)
        if match:
            lat = float(match.group(1))
            lon = float(match.group(2))
            return lat, lon

        # Паттерн: lat:55.45 lon:38.44 или 55.45, 38.44
        coord_pattern2 = r'(?:lat|широта|ш\.)[:\s]*(\d{1,2}\.\d+)[,\s]+(?:lon|долгота|д\.)[:\s]*(\d{1,2}\.\d+)'
        match = re.search(coord_pattern2, text, re.IGNORECASE)
        if match:
            return float(match.group(1)), float(match.group(2))

        return None, None
    
    def _extract_query(self, text: str, triggers: list) -> str:
        """Извлекает поисковый запрос, убирая триггеры"""
        query = text
        
        # Удаляем известные триггеры
        for trigger in triggers:
            query = re.sub(re.escape(trigger), '', query, flags=re.IGNORECASE)
        
        # Чистим
        query = query.strip().strip('.,!?;:').strip()
        
        if len(query) < 2:
            # Если после очистки ничего не осталось — берем исходный
            query = text.strip().strip('.,!?;:').strip()
        
        return query[:200]  # Ограничиваем длину


# ============================================================
# 2. RATE LIMITER
# ============================================================
class RateLimiter:
    """
    Защита от блокировок: паузы, jitter, счетчик запросов.
    """
    
    def __init__(self, config: WebSearchConfig):
        self.config = config
        self.request_times: list = []  # Время последних запросов
        self._lock = asyncio.Lock()
    
    async def wait(self):
        """Ждать перед запросом с учетом лимитов"""
        async with self._lock:
            now = time.time()
            
            # Удаляем старые записи (старше 1 минуты)
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            # Проверяем лимит в минуту
            if len(self.request_times) >= self.config.max_requests_per_minute:
                # Ждем до сброса самого старого
                oldest = min(self.request_times)
                wait_time = 60 - (now - oldest) + 1
                print(f"⏳ Лимит запросов, жду {wait_time:.0f}с...")
                await asyncio.sleep(wait_time)
                self.request_times = []
            
            # Случайная пауза с jitter
            if self.config.use_jitter:
                delay = random.uniform(self.config.min_delay, self.config.max_delay)
            else:
                delay = self.config.min_delay
            
            # Добавляем экспоненциальный backoff если много запросов
            if len(self.request_times) > 10:
                delay *= 2
            
            await asyncio.sleep(delay)
            
            self.request_times.append(time.time())


# ============================================================
# 3. ПОИСК DUCKDUCKGO
# ============================================================
class DuckDuckGoSearch:
    """
    Асинхронный поиск через DuckDuckGo с fallback-стратегией.
    """
    
    def __init__(self, config: WebSearchConfig):
        self.config = config
        self.rate_limiter = RateLimiter(config)
    
    async def search(self, query: str, max_results: int = None) -> List[dict]:
        """
        Основной метод поиска.
        Возвращает список: [{title, url, snippet, source}, ...]
        """
        if max_results is None:
            max_results = self.config.default_results
        
        await self.rate_limiter.wait()
        
        # Стратегия 1: ddgs (основной)
        results = await self._search_ddgs(query, max_results)
        if results:
            return results
        
        # Стратегия 2: Instant Answer API
        print("🔄 Fallback: Instant Answer API...")
        await self.rate_limiter.wait()
        results = await self._search_instant_answer(query, max_results)
        if results:
            return results
        
        # Стратегия 3: HTML парсинг
        print("🔄 Fallback: HTML парсинг...")
        await self.rate_limiter.wait()
        results = await self._search_html(query, max_results)
        
        return results
    
    async def search_news(self, query: str = "", max_results: int = None) -> List[dict]:
        """Поиск новостей"""
        if not query:
            query = "новости сегодня"
        
        if max_results is None:
            max_results = self.config.default_results
        
        # Добавляем "новости" если нет
        if "новост" not in query.lower():
            query = f"новости {query}"
        
        results = await self.search(query, max_results)
        
        # Фильтруем только новостные результаты
        return [r for r in results if self._is_news_result(r)]
    
    async def _search_ddgs(self, query: str, max_results: int) -> List[dict]:
        """Поиск через библиотеку ddgs"""
        try:
            from ddgs import DDGS
            
            loop = asyncio.get_event_loop()
            
            def _sync_search():
                results = []
                with DDGS() as ddgs:
                    for r in ddgs.text(
                        query,
                        region=self.config.region,
                        safesearch=self.config.safe_search,
                        timelimit=self.config.time_range,
                        max_results=max_results
                    ):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", ""),
                            "source": "ddgs"
                        })
                return results
            
            results = await loop.run_in_executor(None, _sync_search)
            return results[:max_results]
            
        except ImportError:
            print("⚠️ ddgs не установлен. pip install ddgs")
            return []
        except Exception as e:
            print(f"⚠️ DDGS ошибка: {e}")
            return []
    
    async def _search_instant_answer(self, query: str, max_results: int) -> List[dict]:
        """Поиск через DuckDuckGo Instant Answer API"""
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1
            }
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                data = response.json()
            
            results = []
            
            # Abstract (краткий ответ)
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("AbstractText", ""),
                    "source": "instant_answer"
                })
            
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                        "source": "instant_answer"
                    })
            
            return results[:max_results]
            
        except Exception as e:
            print(f"⚠️ Instant Answer ошибка: {e}")
            return []
    
    async def _search_html(self, query: str, max_results: int) -> List[dict]:
        """Поиск через парсинг HTML DuckDuckGo"""
        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, data=data)
                soup = BeautifulSoup(response.text, "lxml")
            
            results = []
            for item in soup.select(".result")[:max_results]:
                title_elem = item.select_one(".result__title")
                snippet_elem = item.select_one(".result__snippet")
                link_elem = item.select_one(".result__url")
                
                if title_elem:
                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "url": link_elem.get("href", "") if link_elem else "",
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "source": "html"
                    })
            
            return results
            
        except Exception as e:
            print(f"⚠️ HTML парсинг ошибка: {e}")
            return []
    
    def _is_news_result(self, result: dict) -> bool:
        """Проверяет, похож ли результат на новость"""
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        url = result.get("url", "").lower()
        
        news_indicators = [
            "новост", "news", "статья", "article",
            "сегодня", "today", "опубликован", "published"
        ]
        
        return any(ind in title + snippet + url for ind in news_indicators)


# ============================================================
# 4. ПОГОДА (OpenWeatherMap One Call API 3.0 + fallback 2.5)
# ============================================================
class WeatherService:
    """
    Погода через OpenWeatherMap.
    Основной: One Call API 3.0 (требует подписку).
    Запасной: Current Weather API 2.5 (бесплатный).
    """

    BASE_URL_3 = "https://api.openweathermap.org/data/3.0/onecall"
    BASE_URL_25 = "https://api.openweathermap.org/data/2.5"
    GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"

    def __init__(self, config: WebSearchConfig):
        self.config = config
        self.api_key = config.openweathermap_key or os.getenv("OPENWEATHERMAP_API_KEY", "")
        self.default_city = config.default_city
        self.rate_limiter = RateLimiter(config)

    async def get_weather(self, city: str = None, forecast_type: str = "today") -> str:
        city = city or self.default_city

        await self.rate_limiter.wait()

        if not self.api_key:
            return (
                "OpenWeatherMap API key not configured.\n"
                "1. Register at https://openweathermap.org\n"
                "2. Get a free API key\n"
                "3. Add to config.json: web_search.openweathermap_key"
            )

        try:
            lat, lon = await self._geocode(city)
            if lat is None:
                return f"City '{city}' not found. Try specifying coordinates or a larger nearby city."

            try:
                return await self._get_onecall_v3(lat, lon, forecast_type)
            except Exception:
                return await self._get_weather_v25(city, forecast_type)

        except Exception as e:
            return f"Weather error: {e}"

    async def get_weather_by_coords(self, lat: float, lon: float, forecast_type: str = "today") -> str:
        """Get weather directly by coordinates (no geocoding needed)."""
        await self.rate_limiter.wait()

        if not self.api_key:
            return "OpenWeatherMap API key not configured."

        try:
            try:
                return await self._get_onecall_v3(lat, lon, forecast_type)
            except Exception as e3:
                try:
                    return await self._get_weather_by_coords_v25(lat, lon, forecast_type)
                except Exception as e25:
                    return f"Weather API error: 3.0={e3}, 2.5={e25}"
        except Exception as e:
            return f"Weather error: {e}"

    async def _get_weather_by_coords_v25(self, lat: float, lon: float, forecast_type: str) -> str:
        """Fallback to 2.5 API using coordinates."""
        if forecast_type == "week":
            params = {"lat": lat, "lon": lon, "appid": self.api_key,
                       "units": self.config.weather_units, "lang": self.config.weather_lang,
                       "cnt": 40}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.BASE_URL_25}/forecast", params=params)
                resp.raise_for_status()
                data = resp.json()

            by_day = {}
            for item in data.get("list", []):
                dk = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
                by_day.setdefault(dk, []).append(item)

            lines = [f"Week forecast:\n"]
            for dk, items in list(by_day.items())[:5]:
                dn = datetime.strptime(dk, "%Y-%m-%d").strftime("%d.%m (%A)")
                temps = [it["main"]["temp"] for it in items]
                descs = [it["weather"][0]["description"] for it in items]
                avg_t = sum(temps) / len(temps)
                main_desc = max(set(descs), key=descs.count)
                lines.append(f"{dn}: {avg_t:.0f}C, {main_desc}")
            return "\n".join(lines)

        # Current weather by coordinates
        params = {"lat": lat, "lon": lon, "appid": self.api_key,
                   "units": self.config.weather_units, "lang": self.config.weather_lang}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.BASE_URL_25}/weather", params=params)
            resp.raise_for_status()
            data = resp.json()
        return self._format_weather_v25(data)

    async def _geocode(self, city: str) -> tuple:
        """Convert city name to lat/lon. Tries with increasing context."""
        if not city:
            return None, None

        queries = [
            f"{city}, Russia",
            city,
        ]

        for q in queries[:1]:  # Only first attempt to save time
            try:
                params = {"q": q, "limit": 1, "appid": self.api_key}
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(self.GEO_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    if data:
                        lat = data[0].get("lat")
                        lon = data[0].get("lon")
                        if lat and lon:
                            return lat, lon
            except Exception:
                continue

        return None, None

    # ============ One Call API 3.0 ============

    async def _get_onecall_v3(self, lat: float, lon: float, forecast_type: str) -> str:
        """Current + forecast via One Call API 3.0."""
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": self.config.weather_units,
            "lang": self.config.weather_lang,
        }

        if forecast_type == "today":
            params["exclude"] = "minutely,hourly,alerts"
        elif forecast_type == "tomorrow":
            params["exclude"] = "minutely,hourly,alerts"
        elif forecast_type == "week":
            params["exclude"] = "minutely,alerts"
        else:
            params["exclude"] = "minutely,hourly,daily,alerts"

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(self.BASE_URL_3, params=params)
            resp.raise_for_status()
            data = resp.json()

        if forecast_type == "week":
            return self._format_v3_forecast(data)
        else:
            return self._format_v3_current(data, forecast_type)

    def _format_v3_current(self, data: dict, forecast_type: str) -> str:
        """Format One Call 3.0 current weather response."""
        current = data.get("current", {})
        if not current:
            return "No current weather data available."

        temp = current.get("temp", "?")
        feels_like = current.get("feels_like", "?")
        humidity = current.get("humidity", "?")
        pressure = current.get("pressure", "?")
        wind_speed = current.get("wind_speed", 0)
        weather = current.get("weather", [{}])[0]
        desc = weather.get("description", "")
        emoji = self._get_weather_emoji(desc)
        tz = data.get("timezone", "?").replace("_", " ")

        result = (
            f"{emoji} Weather ({tz}):\n"
            f"  Temperature: {temp:.0f}C (feels like {feels_like:.0f}C)\n"
            f"  Humidity: {humidity}%\n"
            f"  Pressure: {pressure} hPa\n"
            f"  Wind: {wind_speed} m/s\n"
            f"  {desc.capitalize()}"
        )

        # Tomorrow forecast from daily
        if forecast_type == "tomorrow" and "daily" in data and len(data["daily"]) > 1:
            d = data["daily"][1]
            t = d.get("temp", {})
            w = d.get("weather", [{}])[0]
            e = self._get_weather_emoji(w.get("description", ""))
            result += (
                f"\n\nTomorrow:\n"
                f"{e} {w.get('description', '').capitalize()}, "
                f"{t.get('min', '?'):.0f}..{t.get('max', '?'):.0f}C"
            )

        return result

    def _format_v3_forecast(self, data: dict) -> str:
        """Format One Call 3.0 daily forecast."""
        tz = data.get("timezone", "?").replace("_", " ")
        lines = [f"Week forecast ({tz}):\n"]

        for i, d in enumerate(data.get("daily", [])[:7]):
            from datetime import datetime as dt
            day_name = dt.fromtimestamp(d["dt"]).strftime("%d.%m (%A)")
            t = d.get("temp", {})
            w = d.get("weather", [{}])[0]
            e = self._get_weather_emoji(w.get("description", ""))
            lines.append(
                f"{e} {day_name}: {t.get('min', '?'):.0f}..{t.get('max', '?'):.0f}C, "
                f"{w.get('description', '?')}"
            )

        return "\n".join(lines)

    # ============ Fallback: Current Weather API 2.5 ============

    async def _get_weather_v25(self, city: str, forecast_type: str) -> str:
        """Fallback to old 2.5 API."""
        if forecast_type == "week":
            return await self._get_forecast_v25(city)
        else:
            return await self._get_current_v25(city, forecast_type)

    async def _get_current_v25(self, city: str, forecast_type: str) -> str:
        params = {"q": city, "appid": self.api_key,
                   "units": self.config.weather_units, "lang": self.config.weather_lang}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.BASE_URL_25}/weather", params=params)
            resp.raise_for_status()
            data = resp.json()

        result = self._format_weather_v25(data)

        if forecast_type == "tomorrow":
            tomorrow = await self._fetch_forecast_tomorrow_v25(city)
            if tomorrow:
                result += f"\n\nTomorrow:\n{tomorrow}"

        return result

    async def _get_forecast_v25(self, city: str) -> str:
        data = await self._fetch_forecast_v25(city)
        if not data:
            return "Forecast unavailable."

        by_day = {}
        for item in data.get("list", []):
            dk = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
            by_day.setdefault(dk, []).append(item)

        lines = [f"Forecast for {city}:\n"]
        for dk, items in list(by_day.items())[:5]:
            dn = datetime.strptime(dk, "%Y-%m-%d").strftime("%d.%m (%A)")
            temps = [it["main"]["temp"] for it in items]
            descs = [it["weather"][0]["description"] for it in items]
            avg_t = sum(temps) / len(temps)
            main_desc = max(set(descs), key=descs.count)
            e = self._get_weather_emoji(main_desc)
            lines.append(f"{e} {dn}: {avg_t:.0f}C, {main_desc}")

        return "\n".join(lines)

    async def _fetch_forecast_v25(self, city: str) -> Optional[dict]:
        params = {"q": city, "appid": self.api_key,
                   "units": self.config.weather_units, "lang": self.config.weather_lang}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.BASE_URL_25}/forecast", params=params)
            resp.raise_for_status()
            return resp.json()

    async def _fetch_forecast_tomorrow_v25(self, city: str) -> Optional[str]:
        data = await self._fetch_forecast_v25(city)
        if not data:
            return None
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        items = [it for it in data.get("list", [])
                 if datetime.fromtimestamp(it["dt"]).strftime("%Y-%m-%d") == tomorrow]
        if not items:
            return None
        temps = [it["main"]["temp"] for it in items]
        descs = [it["weather"][0]["description"] for it in items]
        main_desc = max(set(descs), key=descs.count)
        e = self._get_weather_emoji(main_desc)
        return f"{e} {main_desc}, {min(temps):.0f}..{max(temps):.0f}C"

    def _format_weather_v25(self, data: dict) -> str:
        city = data.get("name", "?")
        country = data.get("sys", {}).get("country", "")
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        pressure = data["main"]["pressure"]
        wind = data.get("wind", {}).get("speed", 0)
        desc = data["weather"][0]["description"]
        emoji = self._get_weather_emoji(desc)

        return (
            f"{emoji} Weather in {city} ({country}):\n"
            f"  Temperature: {temp:.0f}C (feels like {feels_like:.0f}C)\n"
            f"  Humidity: {humidity}%\n"
            f"  Pressure: {pressure} hPa\n"
            f"  Wind: {wind} m/s\n"
            f"  {desc.capitalize()}"
        )

    def _format_weather(self, data: dict) -> str:
        """Compatibility wrapper — delegates to v3 or v25 based on structure."""
        if "current" in data:
            return self._format_v3_current(data, "today")
        return self._format_weather_v25(data)

    def _get_weather_emoji(self, desc: str) -> str:
        desc = desc.lower()
        if "ясно" in desc or "clear" in desc:
            return "[sun]"
        elif "облачно" in desc or "cloud" in desc:
            return "[cloud]"
        elif "дождь" in desc or "rain" in desc or "морос" in desc:
            return "[rain]"
        elif "снег" in desc or "snow" in desc:
            return "[snow]"
        elif "гроз" in desc or "thunder" in desc:
            return "[storm]"
        elif "туман" in desc or "fog" in desc:
            return "[fog]"
        else:
            return "[weather]"


# ============================================================
# 5. НЕЙРО-ОБРАБОТЧИК РЕЗУЛЬТАТОВ ПОИСКА
# ============================================================
class SearchResultProcessor:
    """
    Обрабатывает сырые результаты поиска через LLM
    для формирования связного, полезного ответа.
    """
    
    def __init__(self, agent_config: dict):
        from autogen.beta import Agent, config as ag_config
        
        self.processor = Agent(
            name="AURA_SearchProcessor",
            config=ag_config.OpenAIConfig(
                model=agent_config.get("model", "deepseek-v4-pro"),
                temperature=0.5,
                max_tokens=1024,
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com/v1"
            )
        )
    
    async def process(self, user_query: str, search_results: List[dict]) -> str:
        """
        Преобразует результаты поиска в связный ответ.
        """
        if not search_results:
            return f"🔍 По запросу '{user_query}' ничего не найдено."
        
        # Формируем контекст из результатов
        results_text = []
        for i, r in enumerate(search_results[:5], 1):
            results_text.append(
                f"[{i}] {r['title']}\n"
                f"    {r['snippet'][:300]}\n"
                f"    {r['url']}"
            )
        
        context = "\n\n".join(results_text)
        
        prompt = (
            "На основе результатов поиска составь краткий, информативный ответ на русском.\n"
            "Выдели главное. Если есть противоречия — укажи.\n"
            "Сохрани ссылки на источники.\n\n"
            f"Запрос: {user_query}\n\n"
            f"Результаты поиска:\n{context}\n\n"
            "Твой ответ (на русском, от имени ассистента AURA):"
        )
        
        try:
            response = await self.processor.ask(prompt)
            return response.content
        except Exception as e:
            # Fallback: возвращаем сырые результаты
            lines = [f"🔍 **Результаты поиска '{user_query}':**\n"]
            for r in search_results[:3]:
                lines.append(f"• [{r['title']}]({r['url']}) — {r['snippet'][:150]}")
            return "\n".join(lines)


# ============================================================
# 6. ТЕСТ
# ============================================================
async def test_web_search():
    """Тест интернет-поиска и погоды"""
    import json
    
    print("=" * 60)
    print("🧪 Тест интернет-поиска AURA")
    print("=" * 60)
    
    # Загружаем конфиг
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    
    web_cfg = config.get("web_search", {})
    
    search_config = WebSearchConfig(
        min_delay=web_cfg.get("rate_limiting", {}).get("min_delay_seconds", 2.0),
        max_delay=web_cfg.get("rate_limiting", {}).get("max_delay_seconds", 5.0),
        max_requests_per_minute=web_cfg.get("rate_limiting", {}).get("max_requests_per_minute", 20),
        default_results=web_cfg.get("search", {}).get("default_results", 5),
        openweathermap_key=web_cfg.get("openweathermap_key", ""),
        default_city=web_cfg.get("weather", {}).get("default_city", "Москва"),
    )
    
    # 1. Тест триггеров
    print("\n📋 Тест триггеров:")
    detector = SearchTriggerDetector(web_cfg.get("triggers", {}))
    
    test_queries = [
        "Какая погода в Москве?",
        "Что нового в мире?",
        "Найди в интернете рецепт борща",
        "Сколько стоит iPhone 16?",
        "Будет дождь завтра в Питере?",
        "Привет, как дела?",  # Не должно сработать
    ]
    
    for q in test_queries:
        result = detector.analyze(q)
        if result["needs_search"]:
            print(f"  🔍 '{q}' → {result['search_type']}: {result['search_query'][:50]}")
        else:
            print(f"  ✖️ '{q}' → не требует поиска")
    
    # 2. Тест поиска
    print("\n🔍 Тест поиска DuckDuckGo:")
    search = DuckDuckGoSearch(search_config)
    
    results = await search.search("Python async programming", 3)
    for r in results:
        print(f"  • {r['title'][:60]}")
        print(f"    {r['snippet'][:100]}")
        print(f"    {r['url']}")
        print()
    
    # 3. Тест погоды
    if search_config.openweathermap_key:
        print("\n🌤 Тест погоды:")
        weather = WeatherService(search_config)
        
        current = await weather.get_weather("Москва")
        print(current[:200])
    else:
        print("\n⚠️ Пропущен тест погоды (нет API ключа)")


if __name__ == "__main__":
    asyncio.run(test_web_search())