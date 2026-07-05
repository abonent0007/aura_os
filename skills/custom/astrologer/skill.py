# astrologer/skill.py v2.0
# Натальные карты, гороскопы, фазы Луны, планетарные возвращения
# Использует Kerykeion — профессиональную астрологическую библиотеку
import json
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

_DATA = Path(__file__).parent / "data.json"

# ── Города ─────────────────────────────────────────────
CITIES = {
    "москва": (55.7558, 37.6173, "Europe/Moscow"),
    "санкт-петербург": (59.9343, 30.3351, "Europe/Moscow"),
    "новосибирск": (55.0084, 82.9357, "Asia/Novosibirsk"),
    "екатеринбург": (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "казань": (55.7961, 49.1064, "Europe/Moscow"),
    "вольск": (52.0500, 47.3800, "Europe/Saratov"),
    "саратов": (51.5336, 46.0343, "Europe/Saratov"),
    "владивосток": (43.1155, 131.8855, "Asia/Vladivostok"),
    "калининград": (54.7104, 20.4522, "Europe/Kaliningrad"),
    "сочи": (43.5855, 39.7231, "Europe/Moscow"),
    "зарайск": (54.7599, 38.8833, "Europe/Moscow"),
}

SIGN_EMOJI = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}
PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
PLANET_EMOJI = {"Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Mars":"♂","Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇"}

# 21 аспект (из astrologyjs + классика)
ASPECTS = [
    ("conjunct", 0, 6, "☌", True, "Соединение"),
    ("semisextile", 30, 3, "⚺", False, "Полусекстиль"),
    ("decile", 36, 1.5, "⊥", False, "Дециль"),
    ("novile", 40, 1.9, "⩔", False, "Новиль"),
    ("semisquare", 45, 3, "∠", False, "Полуквадрат"),
    ("septile", 51.417, 2, "∡", False, "Септиль"),
    ("sextile", 60, 6, "⚹", True, "Секстиль"),
    ("quintile", 72, 2, "⬠", False, "Квинтиль"),
    ("binovile", 80, 2, "⩕", False, "Биновиль"),
    ("square", 90, 6, "□", True, "Квадрат"),
    ("biseptile", 102.851, 2, "∢", False, "Бисептиль"),
    ("tredecile", 108, 2, "⬡", False, "Тредециль"),
    ("trine", 120, 6, "△", True, "Трин"),
    ("sesquiquadrate", 135, 3, "⚼", False, "Полутораквадрат"),
    ("biquintile", 144, 2, "⬟", False, "Биквинтиль"),
    ("inconjunct", 150, 3, "⚻", False, "Квиконс"),
    ("treseptile", 154.284, 1.1, "∣", False, "Трисептиль"),
    ("opposition", 180, 6, "☍", True, "Оппозиция"),
]

FIXED_STARS = {
    "Aldebaran": (69.8, "9°♊", "Успех, смелость, воинский дух"),
    "Regulus": (149.8, "29°♌", "Власть, лидерство, королевская звезда"),
    "Spica": (203.8, "23°♎", "Знания, удача, защита"),
    "Antares": (249.8, "9°♐", "Страсть, интенсивность, трансформация"),
    "Sirius": (104.0, "14°♋", "Слава, богатство, верность"),
    "Vega": (285.0, "15°♑", "Артистизм, харизма, магия"),
    "Betelgeuse": (88.7, "28°♊", "Успех через риск, воинственность"),
    "Capella": (81.7, "21°♊", "Свобода, независимость, богатство"),
}

ARABIC_PARTS = {
    "Колесо Фортуны": lambda s: (s.get("Asc", 0) + s.get("Moon", 0) - s.get("Sun", 0)) % 360,
    "Дух": lambda s: (s.get("Asc", 0) + s.get("Sun", 0) - s.get("Moon", 0)) % 360,
    "Любовь": lambda s: (s.get("Asc", 0) + s.get("Venus", 0) - s.get("Sun", 0)) % 360,
    "Брак": lambda s: (s.get("Asc", 0) + s.get("Desc", 0) - s.get("Venus", 0)) % 360,
}

def _resolve_city(city: str):
    c = city.strip().lower()
    for name, coords in CITIES.items():
        if name in c or c in name:
            return (coords[0], coords[1], coords[2], name.title())
    return (55.7558, 37.6173, "Europe/Moscow", "Москва")

def _load_store():
    if _DATA.exists():
        try: return json.loads(_DATA.read_text(encoding="utf-8"))
        except: pass
    return {"profiles": {}}

def _save_store(s):
    _DATA.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


@tools.tool
def natal_chart(name: str, year: int, month: int, day: int, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Построить натальную карту человека.
    
    Args:
        name: имя
        year, month, day: дата рождения
        hour, minute: время рождения (по умолчанию 12:00)
        city: город (Москва, Вольск, Казань, Сочи...)
    """
    try:
        from kerykeion import AstrologicalSubjectFactory, ReportGenerator, ChartDataFactory
    except ImportError:
        return "❌ Kerykeion не установлен. pip install kerykeion"

    lat, lng, tz, city_name = _resolve_city(city)
    try:
        subject = AstrologicalSubjectFactory.from_birth_data(
            name=name, year=year, month=month, day=day, hour=hour, minute=minute,
            city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
        )
    except Exception as e:
        return f"❌ Ошибка построения карты: {e}"

    s = subject
    lines = [f"🌟 НАТАЛЬНАЯ КАРТА: {name}", f"{'━' * 35}",
             f"📍 {city_name} | {day:02d}.{month:02d}.{year} в {hour:02d}:{minute:02d}",
             f"☀ Восходящий: {s.ascendant.sign} {SIGN_EMOJI.get(s.ascendant.sign, '')}", ""]

    for p in PLANETS:
        pt = getattr(s, p.lower(), None)
        if pt:
            emoji = SIGN_EMOJI.get(pt.sign, "")
            house = f" (дом {pt.house})" if hasattr(pt, 'house') and pt.house else ""
            lines.append(f"  {p}: {pt.sign} {emoji}{house}")

    # Сохраняем
    store = _load_store()
    store["profiles"][name.lower()] = {
        "name": name, "year": year, "month": month, "day": day,
        "hour": hour, "minute": minute, "city": city_name,
        "sun_sign": s.sun.sign, "moon_sign": s.moon.sign,
        "ascendant": s.ascendant.sign, "created": datetime.now().isoformat()
    }
    _save_store(store)
    return "\n".join(lines)


@tools.tool
def natal_profiles() -> str:
    """Показать сохранённые натальные карты."""
    store = _load_store()
    profiles = store.get("profiles", {})
    if not profiles:
        return "Нет сохранённых карт. Создай первую через natal_chart!"
    lines = ["📁 СОХРАНЁННЫЕ КАРТЫ", "━" * 25]
    for k, p in profiles.items():
        lines.append(f"  ▸ {p['name']} — ☀{p.get('sun_sign','?')} 🌙{p.get('moon_sign','?')} ({p.get('city','?')})")
    return "\n".join(lines)


@tools.tool
def moon_phase(date_str: str = "") -> str:
    """
    Фаза Луны на указанную дату (или сегодня).
    date_str: дата в формате YYYY-MM-DD
    """
    try:
        from kerykeion import MoonPhaseDetailsFactory, AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."

    try:
        if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = datetime.now()
    except ValueError:
        return "❌ Неверный формат даты. Используй YYYY-MM-DD."

    try:
        moon = MoonPhaseDetailsFactory(
            year=dt.year, month=dt.month, day=dt.day,
            lat=55.7558, lng=37.6173, tz_str="Europe/Moscow"
        )
    except Exception as e:
        return f"❌ Ошибка: {e}"

    emoji_map = {
        "New Moon": "🌑", "Waxing Crescent": "🌒", "First Quarter": "🌓",
        "Waxing Gibbous": "🌔", "Full Moon": "🌕", "Waning Gibbous": "🌖",
        "Last Quarter": "🌗", "Waning Crescent": "🌘"
    }
    phase_name = getattr(moon, 'phase_name', str(moon))
    emoji = emoji_map.get(phase_name, "🌙")
    return (f"{emoji} ФАЗА ЛУНЫ: {dt.strftime('%d.%m.%Y')}\n"
            f"{'━' * 20}\n"
            f"Фаза: {phase_name}\n"
            f"Освещённость: {getattr(moon, 'illumination', '?')}%")


@tools.tool
def current_sky() -> str:
    """
    Текущее положение планет на небе — «что сейчас над головой».
    """
    try:
        from kerykeion import AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."

    now = datetime.now()
    try:
        sky = AstrologicalSubjectFactory.from_current_time(
            name="Небо", city="Moscow", nation="RU", online=False,
            lng=37.6173, lat=55.7558, tz_str="Europe/Moscow"
        )
    except Exception as e:
        return f"❌ Ошибка: {e}"

    lines = [f"🔭 НЕБО СЕЙЧАС: {now.strftime('%H:%M %d.%m.%Y')}", "━" * 30]
    for p in PLANETS:
        pt = getattr(sky, p.lower(), None)
        if pt:
            emoji = SIGN_EMOJI.get(pt.sign, "")
            house = f" (дом {pt.house})" if hasattr(pt, 'house') and pt.house else ""
            r = " ℞" if hasattr(pt, 'retrograde') and pt.retrograde else ""
            lines.append(f"  {p}: {pt.sign} {emoji}{house}{r}")
    return "\n".join(lines)


@tools.tool
def natal_aspects(name: str, year: int, month: int, day: int, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Показать все аспекты (21 тип) в натальной карте.
    """
    try:
        from kerykeion import AstrologicalSubjectFactory, AspectsFactory
    except ImportError:
        return "❌ Kerykeion не установлен."

    lat, lng, tz, city_name = _resolve_city(city)
    try:
        s = AstrologicalSubjectFactory.from_birth_data(
            name=name, year=year, month=month, day=day, hour=hour, minute=minute,
            city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
        )
    except Exception as e:
        return f"❌ Ошибка: {e}"

    lines = [f"⚡ АСПЕКТЫ: {name}", "━" * 25]
    
    for p1_name in PLANETS:
        for p2_name in PLANETS:
            if p1_name >= p2_name:
                continue
            p1 = getattr(s, p1_name.lower(), None)
            p2 = getattr(s, p2_name.lower(), None)
            if not p1 or not p2:
                continue
            
            a1 = p1.abs_pos
            a2 = p2.abs_pos
            diff = abs(a1 - a2) % 360
            if diff > 180:
                diff = 360 - diff

            for name, angle, orb, symbol, major, label in ASPECTS:
                if abs(diff - angle) <= orb:
                    lines.append(f"  {symbol} {p1_name}–{p2_name}: {label} ({diff:.1f}°)")
                    break

    return "\n".join(lines)


@tools.tool
def arabic_parts(name: str, year: int, month: int, day: int, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Арабские точки (жребии) для натальной карты.
    Колесо Фортуны, Дух, Любовь, Брак.
    """
    try:
        from kerykeion import AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."

    lat, lng, tz, city_name = _resolve_city(city)
    s = AstrologicalSubjectFactory.from_birth_data(
        name=name, year=year, month=month, day=day, hour=hour, minute=minute,
        city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
    )

    positions = {
        "Sun": s.sun.abs_pos, "Moon": s.moon.abs_pos,
        "Venus": s.venus.abs_pos, "Asc": s.ascendant.abs_pos,
        "Desc": (s.ascendant.abs_pos + 180) % 360,
    }

    lines = [f"☪ АРАБСКИЕ ТОЧКИ: {name}", "━" * 25]
    for pname, formula in ARABIC_PARTS.items():
        try:
            pos = formula(positions) % 360
            sign_idx = int(pos // 30)
            sign_names = list(SIGN_EMOJI.keys())
            sn = sign_names[sign_idx]
            deg = pos % 30
            emoji = SIGN_EMOJI.get(sn, "")
            lines.append(f"  {pname}: {deg:.1f}° {sn} {emoji}")
        except Exception:
            pass
    return "\n".join(lines)


@tools.tool
def fixed_stars(name: str = "", year: int = 1990, month: int = 1, day: int = 1, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Показать соединения планет с неподвижными звёздами в натальной карте.
    """
    try:
        from kerykeion import AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."

    lat, lng, tz, city_name = _resolve_city(city)
    s = AstrologicalSubjectFactory.from_birth_data(
        name=name or "Субъект", year=year, month=month, day=day, hour=hour, minute=minute,
        city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
    )

    lines = [f"⭐ НЕПОДВИЖНЫЕ ЗВЁЗДЫ: {name or 'Субъект'}", "━" * 30]
    found = False
    for star_name, (star_pos, zodiac_pos, meaning) in FIXED_STARS.items():
        for p_name in PLANETS:
            pt = getattr(s, p_name.lower(), None)
            if not pt:
                continue
            orb = abs(pt.abs_pos - star_pos) % 360
            if orb > 180: orb = 360 - orb
            if orb <= 2:
                lines.append(f"  ✦ {star_name} ({zodiac_pos}) ☌ {p_name} (орб {orb:.1f}°)")
                lines.append(f"     {meaning}")
                found = True
    if not found:
        lines.append("  Нет точных соединений со звёздами в этой карте")
    return "\n".join(lines)


@tools.tool
def day_night_sect(name: str, year: int, month: int, day: int, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Определить дневную/ночную секту рождения.
    Дневная: Солнце в 7-12 домах → упор на активность и лидерство.
    Ночная: Солнце в 1-6 домах → упор на интуицию и внутренний мир.
    """
    try:
        from kerykeion import AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."
    lat, lng, tz, city_name = _resolve_city(city)
    s = AstrologicalSubjectFactory.from_birth_data(
        name=name, year=year, month=month, day=day, hour=hour, minute=minute,
        city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
    )
    sun_house = getattr(s.sun, 'house', None) or 7
    is_day = 7 <= sun_house <= 12
    sect = "☀ Дневная секта" if is_day else "🌙 Ночная секта"
    return (f"{sect}: {name}\n{'━' * 25}\n"
            f"Солнце в {sun_house}-м доме\n"
            f"{'Акцент: активность, лидерство, внешний мир' if is_day else 'Акцент: интуиция, внутренний мир, эмоции'}\n"
            f"Сектантная планета: {'Юпитер' if is_day else 'Венера'}\n"
            f"Изгнанная: {'Марс' if is_day else 'Сатурн'}")


@tools.tool
def intercepted_signs(name: str, year: int, month: int, day: int, hour: int = 12, minute: int = 0, city: str = "Москва") -> str:
    """
    Перехваченные знаки — знаки без куспида дома.
    Скрытая энергия, требует осознанной работы.
    """
    try:
        from kerykeion import AstrologicalSubjectFactory
    except ImportError:
        return "❌ Kerykeion не установлен."
    lat, lng, tz, city_name = _resolve_city(city)
    s = AstrologicalSubjectFactory.from_birth_data(
        name=name, year=year, month=month, day=day, hour=hour, minute=minute,
        city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
    )
    lines = [f"🔍 ПЕРЕХВАЧЕННЫЕ ЗНАКИ: {name}", "━" * 25]
    signs_on_cusp = set()
    if hasattr(s, 'houses_list'):
        for h in s.houses_list:
            cusp = getattr(h, 'cusp_position', 0) % 360
            signs_on_cusp.add(int(cusp // 30))
    sign_names = list(SIGN_EMOJI.keys())
    found = []
    for i, sn in enumerate(sign_names):
        if i not in signs_on_cusp:
            found.append((sn, SIGN_EMOJI.get(sn, "")))
    if found:
        for sn, emoji in found:
            lines.append(f"  {emoji} {sn} — скрытая энергия, требует осознанной работы")
    else:
        lines.append("Перехватов нет — все 12 знаков управляют домами ✅")
    return "\n".join(lines)
