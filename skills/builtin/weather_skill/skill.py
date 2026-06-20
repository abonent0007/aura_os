# weather_skill/skill.py — OpenWeatherMap 2.5 API (free tier)
import os,asyncio,threading
from autogen.beta import tools

from web_search import WebSearchConfig, WeatherService


def _run_async(coro):
    result = []
    def _t():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result.append(loop.run_until_complete(coro))
        except Exception as e:
            result.append(f"Error: {e}")
        finally:
            loop.close()
    t = threading.Thread(target=_t)
    t.start()
    t.join(timeout=15)
    return result[0] if result else "Timeout"


def _get_ws():
    key = os.getenv("OPENWEATHERMAP_API_KEY", "")
    return WeatherService(WebSearchConfig(
        openweathermap_key=key,
        default_city="Москва",
        weather_units="metric",
        weather_lang="ru"
    ))


@tools.tool
def weather_current(city: str = "Москва") -> str:
    """Текущая погода. city — город на русском или английском (по умолчанию Москва)."""
    ws = _get_ws()
    result = _run_async(ws.get_weather(city, "today"))
    if not isinstance(result, str):
        return f"Weather error: {result}"
    return result


@tools.tool
def weather_forecast(city: str = "Москва", days: str = "today") -> str:
    """Прогноз погоды. days: 'today'|'tomorrow'|'week'. city — город."""
    ws = _get_ws()
    result = _run_async(ws.get_weather(city, days))
    if not isinstance(result, str):
        return f"Weather error: {result}"
    return result


@tools.tool
def weather_by_coords(lat: float, lon: float, days: str = "today") -> str:
    """Погода по координатам. lat, lon — float. days: 'today'|'tomorrow'|'week'."""
    ws = _get_ws()
    result = _run_async(ws.get_weather_by_coords(lat, lon, days))
    if not isinstance(result, str):
        return f"Weather error: {result}"
    return result
