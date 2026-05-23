# moex_stock_tracker/skill.py — v3.0 (доработан по рекомендациям Ауры)
# MOEX ISS API: свечи + цена + объём + MACD(12/26/9) с Signal и Histogram

import json, re
from datetime import datetime, timedelta
from autogen.beta import tools

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

MOEX_CANDLES_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/"
    "TQBR/securities/{ticker}/candles.json"
)
MOEX_MARKETDATA_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/"
    "TQBR/securities/{ticker}.json"
)

POPULAR = {
    "сбер": "SBER", "сбербанк": "SBER",
    "газпром": "GAZP", "лукойл": "LKOH",
    "яндекс": "YNDX", "норникель": "GMKN",
    "роснефть": "ROSN", "втб": "VTBR",
    "магнит": "MGNT", "аэрофлот": "AFLT",
    "мтс": "MTSS", "новатэк": "NVTK",
    "татнефть": "TATN", "сургутнефтегаз": "SNGS",
    "полюс": "PLZL", "северсталь": "CHMF",
    "алроса": "ALRS", "интеррао": "IRAO",
    "московская биржа": "MOEX", "мкб": "CBOM",
}

def _sync_fetch(url: str, params: dict = None) -> dict:
    """Синхронный HTTP-запрос через httpx (thread-safe)."""
    if not HAS_HTTPX:
        return {"error": "httpx not installed. pip install httpx"}
    import asyncio, threading
    result = []
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _get():
                async with httpx.AsyncClient(timeout=15) as c:
                    r = await c.get(url, params=params or {})
                    r.raise_for_status()
                    return r.json()
            result.append(loop.run_until_complete(_get()))
        except Exception as e:
            result.append({"error": str(e)})
        finally:
            loop.close()
    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=20)
    return result[0] if result else {"error": "timeout"}

def _resolve_ticker(name: str) -> str:
    n = name.strip().lower()
    if n in POPULAR: return POPULAR[n]
    u = name.strip().upper()
    if u in POPULAR.values(): return u
    return u

def _calc_ema(prices: list, period: int) -> list:
    if len(prices) < period: return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return [None] * (period - 1) + ema

def _calc_macd_full(closes: list) -> dict:
    if len(closes) < 26:
        return {"error": f"Need 26 candles, got {len(closes)}"}
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd_vals = []
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            macd_vals.append(ema12[i] - ema26[i])
        else:
            macd_vals.append(None)
    valid = [v for v in macd_vals if v is not None]
    if len(valid) < 1:
        return {"error": "Not enough MACD values"}
    sig = _calc_ema(valid, min(9, len(valid)))
    last_macd = macd_vals[-1]
    last_sig = sig[-1] if sig else None
    last_hist = (last_macd - last_sig) if last_macd is not None and last_sig is not None else None
    return {
        "macd_line": round(last_macd, 4) if last_macd else None,
        "signal_line": round(last_sig, 4) if last_sig else None,
        "histogram": round(last_hist, 4) if last_hist else None,
        "trend": "bullish" if (last_hist or 0) > 0 else "bearish",
    }

@tools.tool
def get_stock_price(ticker: str) -> str:
    """Текущая цена и объём торгов акции MOEX. ticker: SBER, GAZP, LKOH..."""
    t = _resolve_ticker(ticker)
    data = _sync_fetch(MOEX_MARKETDATA_URL.format(ticker=t))
    if "error" in data:
        return f"Ошибка: {data['error']}"
    rows = data.get("marketdata", {}).get("data", [])
    if not rows:
        return f"Нет рыночных данных для {t}"
    for row in rows:
        if len(row) > 14 and row[12] is not None:
            price = float(row[12])    # LAST
            change = float(row[13]) if row[13] else 0  # LASTCHANGE
            chg_pct = float(row[14]) if row[14] else 0  # LASTCHANGEPRCNT
            vol = int(row[15]) if row[15] else 0  # QTY
            open_p = float(row[9]) if len(row) > 9 and row[9] else price
            high = float(row[11]) if len(row) > 11 and row[11] else price
            low = float(row[10]) if len(row) > 10 and row[10] else price
            return (
                f"{t}: {price:.2f} RUB | "
                f"{change:+.2f} ({chg_pct:+.2f}%) | "
                f"Vol: {vol} | "
                f"H:{high:.0f} L:{low:.0f} O:{open_p:.0f}"
            )
    return f"Цена для {t} не найдена"

@tools.tool
def calculate_macd(ticker: str, days: int = 90) -> str:
    """
    Расчёт MACD(12/26/9) с Signal и Histogram.
    ticker: тикер (SBER, GAZP...)
    days: дней истории (мин. 26)
    """
    t = _resolve_ticker(ticker)
    if days < 30: days = 90

    end = datetime.now()
    start = end - timedelta(days=days)

    data = _sync_fetch(MOEX_CANDLES_URL.format(ticker=t), params={
        "from": start.strftime("%Y-%m-%d"),
        "till": end.strftime("%Y-%m-%d"),
        "interval": "24",
        "iss.meta": "off",
        "iss.only": "candles",
    })

    if "error" in data:
        return f"Ошибка: {data['error']}"

    candles = data.get("candles", {}).get("data", [])
    if not candles:
        return f"Нет свечных данных для {t}"

    # candle: [open, close, high, low, value, volume, begin, end]
    closes = []
    for c in candles:
        try:
            closes.append(float(c[1]))
        except (ValueError, IndexError):
            continue

    if len(closes) < 26:
        return f"Недостаточно данных: {len(closes)} свечей (нужно 26+)"

    macd = _calc_macd_full(closes)
    if "error" in macd:
        return macd["error"]

    hist_sign = "+" if (macd["histogram"] or 0) > 0 else ""
    trend = "бычий (растёт)" if macd["trend"] == "bullish" else "медвежий (падает)"

    return (
        f"MACD {t} (12/26/9):\n"
        f"  MACD Line:  {macd['macd_line']}\n"
        f"  Signal:     {macd['signal_line']}\n"
        f"  Histogram:  {hist_sign}{macd['histogram']}\n"
        f"  Trend:      {trend}"
    )

@tools.tool
def search_ticker_on_moex(company_name: str) -> str:
    """Поиск тикера MOEX по названию компании."""
    t = _resolve_ticker(company_name)
    if t != company_name.strip().upper():
        return t

    # Поиск через MOEX ISS
    data = _sync_fetch("https://iss.moex.com/iss/securities.json", params={
        "q": company_name.strip().upper(),
        "iss.meta": "off",
        "iss.only": "securities",
    })
    if "error" not in data:
        items = data.get("securities", {}).get("data", [])
        results = []
        for item in items[:8]:
            if len(item) > 2 and item[0] not in results:
                results.append(f"  {item[0]} — {item[2]}")
        if results:
            return "Найдено:\n" + "\n".join(results)

    return f"Тикер для '{company_name}' не найден. Попробуй list_popular_tickers."

@tools.tool
def analyze_stock(company_name: str) -> str:
    """Полный анализ: тикер → цена → объём → MACD."""
    t = _resolve_ticker(company_name)

    price_str = get_stock_price(t)
    macd_str = calculate_macd(t)

    lines = [f"Анализ {company_name} ({t}):", "", price_str, "", macd_str]
    return "\n".join(lines)

@tools.tool
def list_popular_tickers() -> str:
    """Список популярных тикеров MOEX."""
    lines = ["Популярные тикеры MOEX:"]
    seen = set()
    for name, ticker in sorted(POPULAR.items()):
        if ticker not in seen:
            seen.add(ticker)
            lines.append(f"  {ticker} — {name}")
    return "\n".join(lines)
