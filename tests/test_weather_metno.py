# -*- coding: utf-8 -*-
"""Тесты форматирования MET.no (без сети)."""
from datetime import datetime, timedelta, timezone

from web_search import WeatherService, WebSearchConfig


def _ts(iso, temp, code="cloudy", wind=2.0, hum=70):
    return {
        "time": iso,
        "data": {
            "instant": {"details": {
                "air_temperature": temp,
                "wind_speed": wind,
                "relative_humidity": hum,
            }},
            "next_1_hours": {"summary": {"symbol_code": code}},
        },
    }


def _service():
    return WeatherService(WebSearchConfig())


def test_symbol_ru():
    s = _service()
    assert s._metno_desc("clearsky_day") == "ясно"
    assert s._metno_desc("partlycloudy_night") == "переменная облачность"
    assert s._metno_desc("weird_code") == "weird code"


def test_current_formatting():
    s = _service()
    now = datetime.now(timezone.utc)
    out = s._format_metno([_ts(now.isoformat(), 10.3)], "Москва", "today")
    assert "Москва" in out
    assert "+10°C" in out
    assert "облачно" in out
    assert "влажность" in out


def test_today_next_hours():
    s = _service()
    now = datetime.now(timezone.utc)
    series = [_ts((now + timedelta(hours=h)).isoformat(), 10 + h)
              for h in (0, 6, 12)]
    out = s._format_metno(series, "Москва", "today")
    assert "Сейчас" in out
    assert "Через 6 ч" in out
    assert "Через 12 ч" in out


def test_week_picks_days():
    s = _service()
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0,
                                              microsecond=0)
    series = [_ts((base + timedelta(days=d)).isoformat(), 5 + d)
              for d in range(7)]
    out = s._format_metno(series, "Москва", "week")
    assert out.count("\n") >= 6
