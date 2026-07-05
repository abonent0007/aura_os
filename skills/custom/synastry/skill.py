import math, random
from datetime import datetime
from typing import Optional
from autogen.beta import tools

# 21 аспект с орбами
ASPECTS = [
    ("conjunct", 0, 6, "☌"), ("semisextile", 30, 3, "⚺"), ("decile", 36, 1.5, "⊥"),
    ("novile", 40, 1.9, "⩔"), ("semisquare", 45, 3, "∠"), ("septile", 51.417, 2, "∡"),
    ("sextile", 60, 6, "⚹"), ("quintile", 72, 2, "⬠"), ("binovile", 80, 2, "⩕"),
    ("square", 90, 6, "□"), ("biseptile", 102.851, 2, "∢"), ("tredecile", 108, 2, "⬡"),
    ("trine", 120, 6, "△"), ("sesquiquadrate", 135, 3, "⚼"), ("biquintile", 144, 2, "⬟"),
    ("inconjunct", 150, 3, "⚻"), ("treseptile", 154.284, 1.1, "∣"),
    ("opposition", 180, 6, "☍"),
]

PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
PLANET_EMOJI = {"Sun":"☉","Moon":"☽","Mercury":"☿","Venus":"♀","Mars":"♂","Jupiter":"♃","Saturn":"♄","Uranus":"♅","Neptune":"♆","Pluto":"♇"}

SIGN_EMOJI = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}
CITIES = {
    "москва": (55.7558, 37.6173, "Europe/Moscow"),
    "санкт-петербург": (59.9343, 30.3351, "Europe/Moscow"),
    "казань": (55.7961, 49.1064, "Europe/Moscow"),
    "вольск": (52.0500, 47.3800, "Europe/Saratov"),
    "саратов": (51.5336, 46.0343, "Europe/Saratov"),
    "сочи": (43.5855, 39.7231, "Europe/Moscow"),
    "зарайск": (54.7599, 38.8833, "Europe/Moscow"),
}

def _resolve_city(city: str):
    c = city.strip().lower()
    for name, coords in CITIES.items():
        if name in c or c in name:
            return coords[0], coords[1], coords[2], name.title()
    return 55.7558, 37.6173, "Europe/Moscow", "Москва"

def _build_subject(name: str, year: int, month: int, day: int, hour: int, minute: int, city: str):
    from kerykeion import AstrologicalSubjectFactory
    lat, lng, tz, city_name = _resolve_city(city)
    return AstrologicalSubjectFactory.from_birth_data(
        name=name, year=year, month=month, day=day, hour=hour, minute=minute,
        city=city_name, nation="RU", lng=lng, lat=lat, tz_str=tz, online=False
    )


@tools.tool
def synastry_report(
    name1: str = "Первый", year1: int = 1990, month1: int = 1, day1: int = 1, hour1: int = 12, minute1: int = 0, city1: str = "Москва",
    name2: str = "Второй", year2: int = 1990, month2: int = 1, day2: int = 1, hour2: int = 12, minute2: int = 0, city2: str = "Москва",
) -> str:
    """
    Полный синастрический отчёт — совместимость двух людей.
    Профессиональный расчёт: аспекты, скоринг, элементы.
    """
    try:
        from kerykeion import ChartDataFactory, RelationshipScoreFactory, ReportGenerator
    except ImportError:
        return "❌ Установи kerykeion: pip install kerykeion"

    try:
        p1 = _build_subject(name1, year1, month1, day1, hour1, minute1, city1)
        p2 = _build_subject(name2, year2, month2, day2, hour2, minute2, city2)
    except Exception as e:
        return f"❌ Ошибка данных: {e}"

    s1, s2 = p1.sun.sign, p2.sun.sign
    m1, m2 = p1.moon.sign, p2.moon.sign

    lines = [f"💘 СИНАСТРИЯ: {name1} + {name2}", "━" * 40]
    lines.append(f"{name1}: ☀{s1} {SIGN_EMOJI.get(s1,'')} | 🌙{m1} {SIGN_EMOJI.get(m1,'')}")
    lines.append(f"{name2}: ☀{s2} {SIGN_EMOJI.get(s2,'')} | 🌙{m2} {SIGN_EMOJI.get(m2,'')}")
    lines.append("")

    # Скоринг
    try:
        score_factory = RelationshipScoreFactory(p1, p2)
        score_obj = score_factory.get_relationship_score()
        lines.append(f"🔮 СЧЁТ СОВМЕСТИМОСТИ: {score_obj.score_value}")
        lines.append(f"   Уровень: {score_obj.score_description}")
        if hasattr(score_obj, 'is_destiny_sign') and score_obj.is_destiny_sign:
            lines.append("   ⭐ Знак судьбы! Особенная связь.")
    except Exception:
        lines.append("🔮 Счёт: не удалось рассчитать")

    # Аспекты
    try:
        cd = ChartDataFactory.create_synastry_chart_data(p1, p2)
        if hasattr(cd, 'aspects') and cd.aspects:
            lines.append("")
            lines.append("⚡ КЛЮЧЕВЫЕ АСПЕКТЫ:")
            for a in cd.aspects[:8]:
                p1n = getattr(a, 'p1_name', '?')
                p2n = getattr(a, 'p2_name', '?')
                aspect = getattr(a, 'aspect', '?')
                orb = getattr(a, 'orb', 0)
                lines.append(f"  {p1n}–{p2n}: {aspect} (орб {orb:.1f}°)")
    except Exception:
        pass

    return "\n".join(lines)


@tools.tool
def synastry_quick_check(
    name1: str = "Первый", day1: int = 1, month1: int = 1,
    name2: str = "Второй", day2: int = 1, month2: int = 1,
) -> str:
    """
    Быстрая проверка совместимости по солнечным знакам (без полного отчёта).
    """
    # Определение знака по дню и месяцу
    def get_sign(day, month):
        signs = [
            ("Овен", "♈"), ("Телец", "♉"), ("Близнецы", "♊"), ("Рак", "♋"),
            ("Лев", "♌"), ("Дева", "♍"), ("Весы", "♎"), ("Скорпион", "♏"),
            ("Стрелец", "♐"), ("Козерог", "♑"), ("Водолей", "♒"), ("Рыбы", "♓"),
        ]
        boundaries = [20, 19, 21, 20, 21, 21, 23, 23, 23, 22, 21, 19]
        for i, (name, emoji) in enumerate(signs):
            if month == i + 1 and day >= boundaries[i]:
                continue
            return name, emoji
        return "Козерог", "♑"

    s1, e1 = get_sign(day1, month1)
    s2, e2 = get_sign(day2, month2)

    compat = {
        ("Овен","Лев"):92,("Овен","Стрелец"):90,("Телец","Рак"):88,("Телец","Дева"):87,
        ("Близнецы","Весы"):91,("Рак","Скорпион"):93,("Рак","Рыбы"):90,
        ("Лев","Весы"):85,("Дева","Козерог"):86,("Весы","Водолей"):88,
        ("Скорпион","Рыбы"):92,("Стрелец","Овен"):90,("Козерог","Телец"):85,
        ("Водолей","Близнецы"):89,("Рыбы","Рак"):90,
    }
    pair1 = (s1, s2)
    pair2 = (s2, s1)
    score = compat.get(pair1, compat.get(pair2, random.randint(55, 75)))

    lines = [f"⚡ БЫСТРАЯ ПРОВЕРКА: {name1} + {name2}"]
    lines.append(f"{name1}: {e1} {s1}")
    lines.append(f"{name2}: {e2} {s2}")
    lines.append(f"Совместимость: {score}%")

    if score >= 90: lines.append("🔥 Огонь! Редкая пара.")
    elif score >= 80: lines.append("💕 Отлично. Крепкая связь.")
    elif score >= 70: lines.append("👍 Хорошо. Есть над чем работать.")
    else: lines.append("🌱 Интересно. Противоположности притягиваются.")
    return "\n".join(lines)
