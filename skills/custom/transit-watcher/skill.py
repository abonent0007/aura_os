# transit-watcher/skill.py v2.0
# Транзиты планет — отслеживание текущих влияний на натальную карту
# Использует Kerykeion + Swiss Ephemeris
import json
from pathlib import Path
from datetime import datetime, timedelta
from autogen.beta import tools

_DATA = Path(__file__).parent / "data.json"
SIGN_EMOJI = {
    "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
    "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
    "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
}

def _load_store():
    if _DATA.exists():
        try: return json.loads(_DATA.read_text(encoding="utf-8"))
        except: pass
    return {"profiles": {}}

def _save_store(s):
    _DATA.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


@tools.tool
def transit_today(name: str = "", year: int = 1990, month: int = 1, day: int = 1, hour: int = 12, minute: int = 0) -> str:
    """
    Транзиты планет на сегодня для человека (или по умолчанию).
    Показывает какие планеты сейчас аспектируют натальную карту.
    
    Args:
        name: имя (или оставь пустым)
        year, month, day: дата рождения
        hour, minute: время рождения
    """
    try:
        from kerykeion import (
            AstrologicalSubjectFactory, TransitsTimeRangeFactory,
            ChartDataFactory, ReportGenerator
        )
        from kerykeion.ephemeris_data_factory import EphemerisDataFactory
    except ImportError:
        return "❌ Kerykeion не установлен. pip install kerykeion"

    try:
        natal = AstrologicalSubjectFactory.from_birth_data(
            name=name or "Субъект", year=year, month=month, day=day,
            hour=hour, minute=minute, city="Moscow", nation="RU",
            lng=37.6173, lat=55.7558, tz_str="Europe/Moscow", online=False
        )
    except Exception as e:
        return f"❌ Ошибка построения карты: {e}"

    now = datetime.now()
    tomorrow = now + timedelta(days=1)

    try:
        eph = EphemerisDataFactory(
            start_datetime=now, end_datetime=tomorrow,
            step_type="hours", step=24,
            lat=55.7558, lng=37.6173, tz_str="Europe/Moscow",
        ).get_ephemeris_data_as_astrological_subjects()
        transit_result = TransitsTimeRangeFactory(natal, eph).get_transit_moments()
    except Exception as e:
        return f"❌ Ошибка расчёта транзитов: {e}"

    lines = [f"🪐 ТРАНЗИТЫ НА СЕГОДНЯ: {now.strftime('%d.%m.%Y')}", "━" * 35]
    if name:
        lines.append(f"Для: {name} (☀{natal.sun.sign})")

    if not transit_result.transits:
        lines.append("Сегодня спокойный день — значимых транзитов нет 🌙")
        return "\n".join(lines)

    for tm in transit_result.transits[:8]:
        for asp in tm.aspects:
            p1 = getattr(asp, 'p1_name', '?')
            p2 = getattr(asp, 'p2_name', '?')
            atype = getattr(asp, 'aspect', '?')
            orb = getattr(asp, 'orb', 0)
            lines.append(f"  ▸ {p1} △ {p2}: {atype} (орб {orb:.1f}°)")

    return "\n".join(lines)


@tools.tool
def transit_week(name: str = "", year: int = 1990, month: int = 1, day: int = 1, hour: int = 12, minute: int = 0) -> str:
    """
    Транзиты на предстоящую неделю.
    """
    try:
        from kerykeion import (
            AstrologicalSubjectFactory, TransitsTimeRangeFactory
        )
        from kerykeion.ephemeris_data_factory import EphemerisDataFactory
    except ImportError:
        return "❌ Kerykeion не установлен. pip install kerykeion"

    try:
        natal = AstrologicalSubjectFactory.from_birth_data(
            name=name or "Субъект", year=year, month=month, day=day,
            hour=hour, minute=minute, city="Moscow", nation="RU",
            lng=37.6173, lat=55.7558, tz_str="Europe/Moscow", online=False
        )
    except Exception as e:
        return f"❌ Ошибка: {e}"

    now = datetime.now()
    week_end = now + timedelta(days=7)
    try:
        eph = EphemerisDataFactory(
            start_datetime=now, end_datetime=week_end,
            step_type="days", step=1,
            lat=55.7558, lng=37.6173, tz_str="Europe/Moscow",
        ).get_ephemeris_data_as_astrological_subjects()
        transit_result = TransitsTimeRangeFactory(natal, eph).get_transit_moments()
    except Exception as e:
        return f"❌ Ошибка: {e}"

    lines = [f"🪐 ТРАНЗИТЫ НА НЕДЕЛЮ: {now.strftime('%d.%m')}–{week_end.strftime('%d.%m')}", "━" * 35]
    if not transit_result.transits:
        lines.append("Спокойная неделя — наслаждайся 🌙")
        return "\n".join(lines)

    for tm in transit_result.transits:
        dt = tm.date.strftime('%d.%m')
        for asp in tm.aspects[:3]:
            p1 = getattr(asp, 'p1_name', '?')
            p2 = getattr(asp, 'p2_name', '?')
            atype = getattr(asp, 'aspect', '?')
            lines.append(f"  {dt}: {p1} △ {p2} — {atype}")
    return "\n".join(lines)


@tools.tool
def transit_birthdays(name: str = "") -> str:
    """
    Показать сохранённых людей для проверки транзитов.
    """
    store = _load_store()
    profiles = store.get("profiles", {})
    if not profiles:
        return "Нет сохранённых профилей. Добавь через natal_chart в astrologer."
    lines = ["📁 ДОСТУПНЫЕ ПРОФИЛИ", "━" * 20]
    for k, p in profiles.items():
        lines.append(f"  ▸ {p.get('name', k)} ({p.get('sun_sign', '?')})")
    return "\n".join(lines)
