# test_weather_keys.py — Проверка ключей OpenWeatherMap через One Call API 4.0
"""
Usage:
    python test_weather_keys.py              # test all keys
    python test_weather_keys.py --key KEY    # test single key
    python test_weather_keys.py --city Moscow # test city resolution

API: One Call 4.0 — https://api.openweathermap.org/data/4.0/onecall/current
Requires "One Call by Call" subscription (1,000 calls/day free).
"""

import sys, asyncio, httpx, argparse

KEYS = [
    "9ccb619f869de07c7adbb75cc47c6faf",
    "fecd18c530815576fd093eb555fef275",
    "bd5e378503939ddaee76f12ad7a97608",
    "51e154b61c72032ef18f3b7eea32a959",
    "b1b15e88fa797225412429c1c50c122a1",
]

# ── Geocoding: city → lat/lon ──
async def geocode(city: str, key: str) -> tuple:
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get("https://api.openweathermap.org/geo/1.0/direct",
                params={"q": city, "limit": 1, "appid": key})
            if r.status_code == 200:
                data = r.json()
                if data:
                    return data[0]["lat"], data[0]["lon"]
    except Exception:
        pass
    return None, None

# ── One Call 4.0: current weather ──
async def current_weather(lat: float, lon: float, key: str) -> dict:
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get("https://api.openweathermap.org/data/4.0/onecall/current",
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric", "lang": "ru"})
        if r.status_code == 200:
            d = r.json()
            items = d.get("data", [])
            if items:
                return items[0]
        return {"error": r.status_code, "msg": r.text[:200]}

# ── One Call 4.0: daily forecast ──
async def daily_forecast(lat: float, lon: float, key: str, days: int = 3) -> list:
    async with httpx.AsyncClient(timeout=8.0) as c:
        r = await c.get("https://api.openweathermap.org/data/4.0/onecall/timeline/1day",
            params={"lat": lat, "lon": lon, "appid": key, "cnt": days, "units": "metric", "lang": "ru"})
        if r.status_code == 200:
            return r.json().get("data", [])
        return []

# ── Test single key ──
async def test_key(key: str, city: str = "Moscow") -> dict:
    result = {"key": key, "city": city, "ok": False, "current": None, "forecast": None, "error": None, "api": None}

    lat, lon = await geocode(city, key)
    if lat is None:
        # Try 2.5 without geocoding
        return await test_key_v25(key, city)

    # Try One Call 4.0 first
    current = await current_weather(lat, lon, key)
    if "error" not in current:
        result["ok"] = True
        result["api"] = "4.0"
        result["current"] = current
        forecast = await daily_forecast(lat, lon, key, days=3)
        if forecast:
            result["forecast"] = forecast
        return result

    # Fallback: 2.5
    return await test_key_v25(key, city)


async def test_key_v25(key: str, city: str) -> dict:
    """Test with free Current Weather API 2.5."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get("https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": key, "units": "metric", "lang": "ru"})
            if r.status_code == 200:
                d = r.json()
                return {
                    "key": key, "city": city, "ok": True, "api": "2.5",
                    "current": d, "error": None,
                    "forecast": None
                }
            return {"key": key, "city": city, "ok": False, "error": f"HTTP {r.status_code}", "api": "2.5"}
    except Exception as e:
        return {"key": key, "city": city, "ok": False, "error": str(e), "api": "2.5"}


def fmt_current(c: dict) -> str:
    # 4.0 format: data[0].temp
    if "temp" in c:
        return f"{c.get('temp','?'):.0f}C (feels {c.get('feels_like','?'):.0f}) | {c.get('humidity','?')}% | {c.get('pressure','?')}hPa | wind {c.get('wind_speed',0)}m/s | {c.get('weather',[{}])[0].get('description','?')}"
    # 2.5 format: main.temp
    m = c.get("main", {})
    w = c.get("weather", [{}])[0]
    wind = c.get("wind", {}).get("speed", 0)
    return f"{m.get('temp','?'):.0f}C (feels {m.get('feels_like','?'):.0f}) | {m.get('humidity','?')}% | {m.get('pressure','?')}hPa | wind {wind}m/s | {w.get('description','?')}"

def fmt_forecast(f: list) -> str:
    from datetime import datetime
    lines = []
    for d in f[:3]:
        dt = datetime.fromtimestamp(d["dt"]).strftime("%d.%m")
        t = d.get("temp", {})
        w = d.get("weather", [{}])[0]
        lines.append(f"  {dt}: {t.get('min','?'):.0f}..{t.get('max','?'):.0f}C {w.get('description','?')}")
    return "\n".join(lines)

# ── Main ──
async def main():
    p = argparse.ArgumentParser(description="OpenWeatherMap Key Tester (One Call 4.0)")
    p.add_argument("--key", "-k", help="Test single key")
    p.add_argument("--city", "-c", default="Moscow", help="City (default: Moscow)")
    args = p.parse_args()

    keys_to_test = [args.key] if args.key else KEYS

    print(f"\n{'='*60}")
    print(f"OpenWeatherMap One Call API 4.0 — Key Tester")
    print(f"City: {args.city}")
    print(f"Keys: {len(keys_to_test)}")
    print(f"{'='*60}\n")

    working = []
    for i, key in enumerate(keys_to_test, 1):
        masked = f"{key[:4]}...{key[-4:]}"
        print(f"[{i}/{len(keys_to_test)}] {masked}...", end=" ", flush=True)
        r = await test_key(key, args.city)

        if r["ok"]:
            cur = fmt_current(r["current"])
            print(f"OK: {cur}")
            if r["forecast"]:
                print(fmt_forecast(r["forecast"]))
            working.append((key, r))
        else:
            err = r.get("error", {})
            msg = err if isinstance(err, str) else f"HTTP {err.get('error','?')}"
            print(f"FAIL: {msg}")
        print()

    print(f"{'='*60}")
    if working:
        print(f"Working: {len(working)}/{len(keys_to_test)}")
        for key, r in working:
            print(f"  {key} — {fmt_current(r['current'])}")
        best = working[0][0]
        print(f"\nBest key: {best}")
        print(f"Set in .env: OPENWEATHERMAP_API_KEY={best}")
    else:
        print("No working keys. All failed.")
        print("Keys require 'One Call by Call' subscription.")
        print("Free tier: https://openweathermap.org/price")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(main())
