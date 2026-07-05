# radio/skill.py — Unified Radio Browser Skill
# Поиск, топы, случайный выбор, история прослушивания
# API: https://api.radio-browser.info/ (бесплатно, без ключей)

import json, random, sys
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import run_async

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

BASE_URL = "https://de1.api.radio-browser.info/json"
_STORE_FILE = Path(__file__).parent / "history.json"

# ── Русские маппинги жанров ─────────────────────────────────────────────
POPULAR_TAGS = {
    "джаз": "jazz", "джаза": "jazz",
    "рок": "rock", "рока": "rock",
    "классика": "classical", "классику": "classical",
    "поп": "pop", "попса": "pop", "попсу": "pop",
    "электро": "electronic", "электроника": "electronic", "электроники": "electronic",
    "чиллаут": "chillout", "чилл": "chillout",
    "лоуфай": "lo-fi", "lo-fi": "lo-fi", "lofi": "lo-fi",
    "хип-хоп": "hip hop", "хип хоп": "hip hop", "hip hop": "hip hop",
    "регги": "reggae",
    "блюз": "blues", "блюза": "blues",
    "кантри": "country",
    "лаунж": "lounge", "лаунжа": "lounge",
    "транс": "trance",
    "техно": "techno",
    "хаус": "house",
    "дип": "deep house", "deep house": "deep house",
    "метал": "metal", "металл": "metal",
    "инди": "indie",
    "фанк": "funk",
    "соул": "soul",
    "диско": "disco",
    "ретро": "oldies", "олдиз": "oldies",
    "новости": "news",
    "разговорное": "talk",
    "эмбиент": "ambient", "ambient": "ambient",
    "dance": "dance", "танцевальное": "dance",
}

POPULAR_COUNTRIES = {
    "россия": "Russia", "россии": "Russia", "русское": "Russia",
    "сша": "USA", "америка": "USA", "американское": "USA",
    "германия": "Germany", "германии": "Germany", "немецкое": "Germany",
    "франция": "France", "франции": "France", "французское": "France",
    "япония": "Japan", "японии": "Japan", "японское": "Japan",
    "великобритания": "UK", "англия": "UK", "британское": "UK",
    "италия": "Italy", "италии": "Italy", "итальянское": "Italy",
    "испания": "Spain", "испании": "Spain", "испанское": "Spain",
    "украина": "Ukraine", "украины": "Ukraine", "украинское": "Ukraine",
    "бразилия": "Brazil", "бразилии": "Brazil",
    "канада": "Canada", "канады": "Canada",
    "австралия": "Australia", "австралии": "Australia",
    "нидерланды": "Netherlands", "голландия": "Netherlands",
}

# ── Маппинг настроений на жанры ─────────────────────────────────────────
MOOD_MAP = {
    "relax": "chillout", "спокойное": "chillout", "расслабон": "chillout",
    "energy": "rock", "энергия": "rock", "бодрое": "rock",
    "focus": "ambient", "концентрация": "ambient", "работа": "ambient",
    "happy": "pop", "весёлое": "pop", "радость": "pop",
    "sad": "blues", "грустное": "blues", "грусть": "blues",
    "romantic": "jazz", "романтика": "jazz", "свидание": "jazz",
    "party": "dance", "вечеринка": "dance", "танцы": "dance",
    "sleep": "ambient", "сон": "ambient", "засыпаю": "ambient",
}

# ── Хранилище истории ───────────────────────────────────────────────────
class _History:
    def __init__(self):
        self._data = []
        if _STORE_FILE.exists():
            try:
                self._data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            except:
                pass

    def _save(self):
        _STORE_FILE.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add(self, station: dict):
        self._data.append({
            "name": station.get("name", "?"),
            "url": station.get("url_resolved") or station.get("url", ""),
            "genre": station.get("tags", ""),
            "country": station.get("country", ""),
            "ts": datetime.now().isoformat()
        })
        if len(self._data) > 50:
            self._data = self._data[-50:]
        self._save()

    def last(self, n: int = 5) -> list:
        return self._data[-n:]

_history = _History()

# ── HTTP-хелпер ──────────────────────────────────────────────────────────
def _sync_fetch(url: str, params: dict = None) -> dict:
    if not HAS_HTTPX:
        return {"error": "httpx не установлен"}
    async def _get():
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "AURA-OS/1.0"}) as c:
            r = await c.get(url, params=params or {})
            r.raise_for_status()
            return r.json()
    result = run_async(_get(), timeout=20)
    return result if result else {"error": "timeout"}

def _resolve_tag(raw: str) -> str:
    t = raw.strip().lower()
    return POPULAR_TAGS.get(t, t)

def _resolve_country(raw: str) -> str:
    c = raw.strip().lower()
    return POPULAR_COUNTRIES.get(c, raw.strip())

def _format_station(s: dict) -> str:
    name = s.get("name", "?")
    url = s.get("url_resolved", s.get("url", ""))
    tags = s.get("tags", "")
    country = s.get("country", "")
    language = s.get("language", "")
    bitrate = s.get("bitrate", 0)
    codec = s.get("codec", "")
    votes = s.get("votes", 0)
    clicks = s.get("clickcount", 0)
    homepage = s.get("homepage", "")

    line = f"📻 {name}"
    if tags:
        line += f" | {tags}"
    if country:
        line += f" | {country}"
    if bitrate:
        line += f" | {bitrate}kbps {codec.upper()}" if codec else f" | {bitrate}kbps"
    if votes:
        line += f" | ❤{votes}"
    if clicks:
        line += f" | 👆{clicks}"
    if url:
        line += f"\n   🎧 {url}"
    if homepage:
        line += f"\n   🏠 {homepage}"
    return line


# ═══════════════════════════════════════════════════════════════════════════
# ИНСТРУМЕНТЫ
# ═══════════════════════════════════════════════════════════════════════════

@tools.tool
def search_radio(
    name: str = "",
    tag: str = "",
    country: str = "",
    language: str = "",
    limit: int = 10,
) -> str:
    """
    Поиск интернет-радиостанций по названию, жанру, стране, языку.
    Поддерживает русские названия жанров (джаз, рок, классика, поп...).
    name: название станции (частичное совпадение)
    tag: жанр — jazz, rock, pop, classical, electronic, chillout...
    country: страна — Russia, USA, Germany, Japan...
    language: язык — russian, english, german...
    limit: максимум результатов (по умолчанию 10)
    """
    params = {
        "limit": min(limit, 25),
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true"
    }
    if name:
        params["name"] = name.strip()
    if tag:
        params["tag"] = _resolve_tag(tag)
    if country:
        params["country"] = _resolve_country(country)
    if language:
        params["language"] = language.strip().lower()

    data = _sync_fetch(f"{BASE_URL}/stations/search", params)

    if "error" in data:
        return f"Ошибка при поиске радио: {data['error']}"
    if not data or not isinstance(data, list):
        return "Ничего не найдено. Попробуй изменить запрос."

    lines = [f"🎶 Найдено станций: {len(data)}"]
    for s in data[:limit]:
        lines.append(_format_station(s))
        lines.append("")
    return "\n".join(lines)


@tools.tool
def top_radio(limit: int = 10, sort_by: str = "clicks") -> str:
    """
    Топ интернет-радиостанций.
    limit: сколько показать (по умолчанию 10)
    sort_by: 'clicks' (по популярности) или 'votes' (по голосам)
    """
    count = min(limit, 15)
    endpoint = "topclick" if sort_by == "clicks" else "topvote"
    data = _sync_fetch(f"{BASE_URL}/stations/{endpoint}/{count}")

    if "error" in data:
        return f"Ошибка: {data['error']}"
    if not data or not isinstance(data, list):
        return "Не удалось загрузить топ станций."

    label = "по кликам" if sort_by == "clicks" else "по голосам"
    lines = [f"🏆 Топ-{len(data)} радиостанций ({label}):", ""]
    for i, s in enumerate(data, 1):
        name = s.get("name", "?")
        tags = s.get("tags", "")
        bitrate = s.get("bitrate", 0)
        codec = s.get("codec", "")
        url = s.get("url_resolved", s.get("url", ""))
        votes = s.get("votes", 0)
        clicks = s.get("clickcount", 0)

        lines.append(f"{i}. 📻 {name}")
        if tags:
            lines.append(f"   Жанр: {tags}")
        if bitrate:
            lines.append(f"   Качество: {bitrate}kbps {codec.upper()}" if codec else f"   Качество: {bitrate}kbps")
        lines.append(f"   ❤{votes} 👆{clicks}")
        lines.append(f"   🎧 {url}")
        lines.append("")
    return "\n".join(lines)


@tools.tool
def radio_tags(limit: int = 30) -> str:
    """
    Список популярных жанров/тегов радиостанций из API.
    limit: сколько показать (по умолчанию 30)
    """
    data = _sync_fetch(f"{BASE_URL}/tags", {
        "limit": str(limit),
        "order": "stationcount",
        "reverse": "true"
    })
    if "error" in data:
        return f"Ошибка: {data['error']}"
    if not data or not isinstance(data, list):
        return "Не удалось загрузить теги."

    lines = [f"🎵 Популярные жанры радио ({len(data)}):", ""]
    for t in data:
        name = t.get("name", "?")
        count = t.get("stationcount", 0)
        lines.append(f"  {name} ({count} станций)")
    return "\n".join(lines)


@tools.tool
def radio_countries(limit: int = 30) -> str:
    """
    Список стран с интернет-радиостанциями.
    limit: сколько показать (по умолчанию 30)
    """
    data = _sync_fetch(f"{BASE_URL}/countries", {
        "limit": str(limit),
        "order": "stationcount",
        "reverse": "true"
    })
    if "error" in data:
        return f"Ошибка: {data['error']}"
    if not data or not isinstance(data, list):
        return "Не удалось загрузить список стран."

    lines = [f"🌍 Страны с радиостанциями ({len(data)}):", ""]
    for c in data:
        name = c.get("name", "?")
        count = c.get("stationcount", 0)
        lines.append(f"  {name} ({count} станций)")
    return "\n".join(lines)


@tools.tool
def play_random_radio(genre: str = "", mood: str = "") -> str:
    """
    Включить случайную радиостанцию. Возвращает URL потока — открой через open_url.
    
    Параметры:
    - genre: жанр (jazz, rock, chillout, classical, lofi, electronic, ambient...)
    - mood: настроение (relax/спокойное, energy/бодрое, focus/работа, happy/весёлое,
             sad/грустное, romantic/романтика, party/танцы, sleep/сон)
    
    Если оба пустые — случайная из топ-50 по голосам.
    """
    # Сначала пробуем настроение, потом жанр
    tag = _resolve_tag(genre) if genre else ""
    if not tag and mood:
        tag = MOOD_MAP.get(mood.strip().lower(), "")
        if not tag:
            tag = _resolve_tag(mood)

    if tag:
        url = f"{BASE_URL}/stations/bytag/{tag}?limit=50&hidebroken=true"
    else:
        url = f"{BASE_URL}/stations/topvote/50?hidebroken=true"

    data = _sync_fetch(url)
    if "error" in data:
        return f"Ой, не получилось подключиться к Radio Browser: {data['error']}"
    if not data or not isinstance(data, list):
        return f"Не нашла станций{f' для «{tag or mood or genre}»' if (tag or mood or genre) else ''} 😔"

    # Выбираем случайную, предпочитаем с url_resolved
    random.shuffle(data)
    best = None
    for s in data:
        if s.get("url_resolved"):
            best = s
            break
    if not best:
        best = data[0]

    name = best.get("name", "Неизвестная станция")
    stream_url = best.get("url_resolved") or best.get("url", "")
    tags = best.get("tags", "").replace(",", ", ") or "разное"
    country = best.get("country", "мир")

    _history.add(best)

    return (
        f"🎶 Включаю: {name}\n"
        f"   Жанр: {tags}\n"
        f"   Страна: {country}\n"
        f"   🔗 Поток: {stream_url}"
    )


@tools.tool
def list_radio_genres() -> str:
    """
    Быстрый список популярных жанров радио.
    Используй когда пользователь не знает какой жанр выбрать.
    """
    popular = [
        "jazz", "rock", "pop", "classical", "electronic",
        "chillout", "lofi", "ambient", "blues", "country",
        "dance", "hiphop", "rnb", "reggae", "latin",
        "metal", "folk", "world", "news", "talk"
    ]
    return (
        "🎧 Популярные жанры радио:\n"
        "  " + ", ".join(popular) + "\n\n"
        "Можешь также назвать настроение: relax, energy, focus, happy, romantic, party\n"
        "Или по-русски: спокойное, бодрое, работа, весёлое, романтика, танцы"
    )


@tools.tool
def get_last_played(n: int = 5) -> str:
    """
    Показать последние включённые радиостанции.
    Используй когда пользователь спрашивает «что играло» или «история радио».
    """
    last = _history.last(n)
    if not last:
        return "Я ещё ничего не включала. Попроси меня поставить музыку! 🎧"
    lines = [f"🎵 Последние {len(last)} станций:"]
    for i, s in enumerate(reversed(last), 1):
        lines.append(f"  {i}. {s['name']} ({s['genre']}) — {s['ts'][:16]}")
    return "\n".join(lines)
