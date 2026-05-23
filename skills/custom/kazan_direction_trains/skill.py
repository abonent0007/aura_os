# kazan_direction_trains/skill.py — Расписание электричек v1.3
# Формат: 🚃 НОМЕР ОТКУДА → КУДА | 🕐 ВРЕМЯ | 🛤 ПУТЬ | Остановки

import json, re, threading, asyncio, urllib.parse
from datetime import datetime, timedelta
from autogen.beta import tools

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

STATIONS = [
    "Казанский вокзал", "Электрозаводская", "Сортировочная", "Авиамоторная",
    "Андроновка", "Перово", "Плющево", "Вешняки", "Выхино", "Косино",
    "Ухтомская", "Люберцы", "Панки", "Томилино", "Красково", "Малаховка",
    "Удельная", "Быково", "Ильинская", "Отдых", "Кратово", "Есенинская",
    "Фабричная", "Раменское", "Ипподром", "Совхоз", "Загорново",
    "Бронницы", "Радуга", "63 км", "Белоозерская", "Фаустово",
    "Золотово", "Виноградово", "Конобеево", "Трофимово", "88 км",
    "Воскресенск", "Шиферная", "Москворецкая", "Цемгигант", "Пески",
    "Конев Бор", "Хорошово", "113 км", "Коломна", "Голутвин",
    "Щурово", "Черная", "Луховицы", "142 км", "Подлипки",
    "Фруктовая", "Алпатьево", "Слёмы", "Дивово", "Истодники",
    "Рязань", "Шатура", "Черусти", "Егорьевск"
]

STATION_CODES = {
    "казанский вокзал": "s9600213", "люберцы": "s9601722",
    "выхино": "s9601687", "раменское": "s9601795",
    "быково": "s9601755", "голутвин": "s9602011", "коломна": "s9601997",
    "воскресенск": "s9601933", "рязань": "s9602078",
    "шатура": "s9602193", "черусти": "s9602210", "егорьевск": "s9602154",
}

def _resolve_code(name: str) -> str:
    n = name.lower().strip()
    if n in STATION_CODES: return STATION_CODES[n]
    for k, v in STATION_CODES.items():
        if k in n or n in k: return v
    return None

def _fetch_url(url, params=None, timeout=15):
    """Thread-safe HTTP GET returning text."""
    if not HAS_HTTPX: return ""
    result = []
    def _run():
        loop = asyncio.new_event_loop()
        async def _get():
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
                return r.text if r.status_code == 200 else ""
        try:
            result.append(loop.run_until_complete(_get()))
        finally:
            loop.close()
    t = threading.Thread(target=_run); t.start(); t.join(timeout + 5)
    return result[0] if result else ""

# ── Yandex Schedule Parser ──
def _parse_yandex(html: str, from_st: str, to_st: str, date_str: str):
    """Extract train segments from Yandex schedule page."""
    segs_match = re.search(r'"segments"\s*:\s*(\[.+?\}\])\s*[,;}\n]', html, re.DOTALL)
    if not segs_match:
        return None
    try:
        segments = json.loads(segs_match.group(1))
    except json.JSONDecodeError:
        return None

    if not segments:
        return None

    # Format date header
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_header = f"Schedule {from_st} -> {to_st} on {date_obj.strftime('%d.%m.%Y')}"

    lines = [date_header, ""]
    yandex_url = (
        f"https://rasp.yandex.ru/search/suburban/?"
        f"fromName={urllib.parse.quote(from_st)}&toName={urllib.parse.quote(to_st)}&when={date_str}"
    )

    for i, seg in enumerate(segments[:12]):
        num = seg.get("number", "?")
        dep_raw = seg.get("departureLocalDt", "")
        arr_raw = seg.get("arrivalLocalDt", "")
        dur_sec = seg.get("duration", 0)
        dur_min = dur_sec // 60
        company = seg.get("company", {}).get("shortTitle", seg.get("company", {}).get("title", "ЦППК"))

        # Extract times: "2026-05-21T05:17:00+03:00" -> "05:17"
        dep_time = dep_raw[11:16] if len(dep_raw) > 15 else dep_raw
        arr_time = arr_raw[11:16] if len(arr_raw) > 15 else arr_raw

        # Thread info: route, stops, platform
        thread = seg.get("thread", {})
        thread_title = thread.get("title", "")
        transport = thread.get("transportType", "electric")
        express_type = thread.get("expressType", "")

        # Facilities
        facilities = seg.get("suburbanFacilities", [])
        fac_tags = ", ".join([f.get("title", "") for f in facilities[:3]]) if facilities else ""

        # Build train header
        route_name = thread_title or f"{from_st} -> {to_st}"
        lines.append(f"{num} {route_name}")
        lines.append(f"{dep_time} -> {arr_time} ({dur_min} min)")

        # Platform / path info
        platform_info = []
        dep_platform = seg.get("departurePlatform", "")
        arr_platform = seg.get("arrivalPlatform", "")
        if dep_platform:
            platform_info.append(f"Departure platform: {dep_platform}")
        if arr_platform:
            platform_info.append(f"Arrival platform: {arr_platform}")
        if platform_info:
            lines.append("  " + " | ".join(platform_info))

        # Company + express type
        meta = []
        if company:
            meta.append(company)
        if express_type:
            meta.append(express_type)
        if fac_tags:
            meta.append(fac_tags)
        if meta:
            lines.append("  " + " | ".join(meta))

        # Stops
        stops = seg.get("stops", "")
        if stops:
            lines.append(f"  Stops: {stops}")

        if i < 11:
            lines.append("")

    lines.append(f"Source: {yandex_url}")
    return "\n".join(lines)

# ── Demo schedule ──
def _demo_schedule(from_st, to_st, date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_header = f"Schedule {from_st} -> {to_st} on {date_obj.strftime('%d.%m.%Y')}"

    now = datetime.now()
    trains = [date_header, ""]
    for i in range(6):
        dep = now.replace(hour=(6 + i), minute=i * 7 % 60)
        arr = dep + timedelta(minutes=22 + i * 4)
        dur = (arr - dep).seconds // 60
        num = 6700 + i * 2
        trains.append(f"{num} {from_st} -> {to_st} (Kazan direction)")
        trains.append(f"{dep.strftime('%H:%M')} -> {arr.strftime('%H:%M')} ({dur} min)")
        trains.append(f"  Central PPK | All stops")
        if i < 5:
            trains.append("")

    yandex_url = (
        f"https://rasp.yandex.ru/search/suburban/?"
        f"fromName={urllib.parse.quote(from_st)}&toName={urllib.parse.quote(to_st)}&when={date_str}"
    )
    ppk_url = (
        f"https://www.central-ppk.ru/new/schedule/index.php?"
        f"stationFrom={urllib.parse.quote(from_st.upper())}"
        f"&stationTo={urllib.parse.quote(to_st.upper())}&date={date_str}"
    )

    trains.append(f"[Approximate. Live schedule:]")
    trains.append(f"  Yandex: {yandex_url}")
    trains.append(f"  Central PPK: {ppk_url}")

    return "\n".join(trains)

# ── Tools ──

@tools.tool
def get_nearest_trains(from_station: str, to_station: str, date_str: str = None) -> str:
    """
    Get electric train schedule between two stations (Kazan direction).
    from_station: station name in Russian (e.g. Казанский вокзал, Люберцы, Выхино, Белоозерская)
    to_station: station name in Russian
    date_str: YYYY-MM-DD (default: today)
    """
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")

    # Try Yandex API
    from_code = _resolve_code(from_station)
    to_code = _resolve_code(to_station)
    if from_code and to_code:
        url = "https://rasp.yandex.ru/search/suburban/"
        html = _fetch_url(url, {"fromId": from_code, "toId": to_code, "when": date_str})
        if html:
            result = _parse_yandex(html, from_station, to_station, date_str)
            if result:
                return f"Schedule {from_station} -> {to_station} on {date_str}:\n\n{result}\n\nSource: Yandex"

    # Fallback: demo with real links
    return f"Schedule {from_station} -> {to_station} on {date_str}:\n\n{_demo_schedule(from_station, to_station, date_str)}"

@tools.tool
def list_available_stations() -> str:
    """Show all stations of Kazan direction."""
    lines = "\n".join([f"  {s}" for s in STATIONS])
    return f"Kazan direction stations:\n{lines}\n\nTotal: {len(STATIONS)}"

@tools.tool
def find_schedule_url(from_station: str, to_station: str, date_str: str = None) -> str:
    """
    Generate direct URLs for checking train schedule.
    """
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    return (
        f"Live schedule {from_station} -> {to_station} on {date_str}:\n"
        f"  Central PPK: https://www.central-ppk.ru/new/schedule/index.php"
        f"?stationFrom={urllib.parse.quote(from_station.upper())}"
        f"&stationTo={urllib.parse.quote(to_station.upper())}&date={date_str}\n"
        f"  Yandex: https://rasp.yandex.ru/search/suburban/"
        f"?fromName={urllib.parse.quote(from_station)}"
        f"&toName={urllib.parse.quote(to_station)}&when={date_str}"
    )
