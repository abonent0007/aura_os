"""
Авто-органайзер для ВАЗ 21093 (и других авто).
Хранит историю обслуживания, напоминает о предстоящих ТО.
Учитывает и километраж, и время (месяцы).
"""

import json
from pathlib import Path
from datetime import datetime, date
from autogen.beta import tools

SKILL_DIR = Path(__file__).parent
DATA_FILE = SKILL_DIR / "data.json"


def _load():
    if not DATA_FILE.exists():
        return {
            "car": {"brand": "?", "model": "?", "year": "?", "nickname": "?"},
            "mileage_km": 0,
            "service_history": [],
            "schedule": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _months_ago(iso_str: str) -> int:
    """Сколько месяцев прошло с даты. 0 если дата в будущем."""
    try:
        d = datetime.fromisoformat(iso_str)
        now = datetime.now()
        diff = (now.year - d.year) * 12 + (now.month - d.month)
        return max(0, diff)
    except Exception:
        return 0


# === ИНСТРУМЕНТЫ ===

@tools.tool
def car_info() -> str:
    """Информация об автомобиле: марка, модель, год, пробег."""
    data = _load()
    c = data["car"]
    mileage = data.get("mileage_km")
    m_str = f"{mileage:,} км".replace(",", " ") if mileage else "неизвестен"

    return (
        f"🚗 {c['brand']} {c['model']} ({c['year']})\n"
        f"Прозвище: «{c['nickname']}»\n"
        f"Пробег: {m_str}\n"
        f"Записей обслуживания: {len(data['service_history'])}"
    )


@tools.tool
def car_set_mileage(km: int) -> str:
    """Установить текущий пробег автомобиля.

    Args:
        km: пробег в километрах
    """
    data = _load()
    old = data.get("mileage_km")
    data["mileage_km"] = km
    _save(data)

    if old:
        return f"✅ Пробег обновлён: {old:,} → {km:,} км".replace(",", " ")
    return f"✅ Пробег установлен: {km:,} км".replace(",", " ")


@tools.tool
def car_add_service(item_key: str, date_str: str = "", km: int = 0, note: str = "") -> str:
    """Записать проведённое обслуживание.

    Args:
        item_key: ключ позиции из регламента (engine_oil_filter, air_filter, timing_belt...)
        date_str: дата обслуживания в формате YYYY-MM-DD (если пусто — сегодня)
        km: пробег на момент обслуживания
        note: заметка (например «купил масло Лукойл»)
    """
    data = _load()
    schedule = data["schedule"]

    if item_key not in schedule:
        keys = "\n".join(f"  • {k} — {v['name']}" for k, v in schedule.items())
        return f"❌ Неизвестный ключ: {item_key}\nДоступные:\n{keys}"

    if not date_str:
        date_str = date.today().isoformat()

    entry = {
        "item": item_key,
        "name": schedule[item_key]["name"],
        "date": date_str,
        "km": km,
        "note": note,
    }
    data["service_history"].append(entry)
    if km:
        data["mileage_km"] = km
    _save(data)

    return f"✅ Записано: {entry['name']}\n📅 {date_str}{' • ' + f'{km:,} км'.replace(',', ' ') if km else ''}{' • ' + note if note else ''}"


@tools.tool
def car_upcoming() -> str:
    """Предстоящее обслуживание: что пора сделать (срочное) и что скоро (плановое)."""
    data = _load()
    schedule = data["schedule"]
    history = data["service_history"]
    mileage = data.get("mileage_km")

    if not mileage:
        return "⚠️ Пробег не установлен. Используй car_set_mileage."

    # Последнее обслуживание по каждому ключу
    last_service = {}
    for h in history:
        key = h["item"]
        if key not in last_service or h["date"] > last_service[key]["date"]:
            last_service[key] = h

    urgent = []
    soon = []

    for key, spec in schedule.items():
        last = last_service.get(key)
        if last:
            months_passed = _months_ago(last["date"])
            km_passed = mileage - last.get("km", 0) if last.get("km") else 0
        else:
            months_passed = 999  # никогда не делали
            km_passed = 999999

        if km_passed >= spec["km"] or months_passed >= spec["months"]:
            urgent.append(f"  🔴 {spec['name']} — просрочено! ({spec['km']} км / {spec['months']} мес)")
        elif km_passed >= spec["km"] * 0.8 or months_passed >= spec["months"] * 0.8:
            soon.append(f"  🟡 {spec['name']} — скоро ({spec['km']} км / {spec['months']} мес)")

    if not urgent and not soon:
        return "✅ Всё по регламенту — срочного обслуживания нет."

    out = ""
    if urgent:
        out += "🔴 СРОЧНО:\n" + "\n".join(urgent)
    if soon:
        if out:
            out += "\n\n"
        out += "🟡 СКОРО:\n" + "\n".join(soon)
    return out


@tools.tool
def car_status() -> str:
    """Полная сводка: авто + история + предстоящее."""
    info = car_info()
    upcoming = car_upcoming()

    data = _load()
    history = data["service_history"]

    out = info + "\n\n"
    out += "━" * 30 + "\n"
    out += upcoming + "\n\n"

    if history:
        out += "━" * 30 + "\n"
        out += "📋 История обслуживания:\n"
        for h in reversed(history[-5:]):
            km_str = f"{h['km']:,} км".replace(",", " ") if h.get("km") else "—"
            out += f"  • {h['date']} — {h['name']} ({km_str})"
            if h.get("note"):
                out += f" — {h['note']}"
            out += "\n"
        if len(history) > 5:
            out += f"  ... и ещё {len(history) - 5} записей\n"

    return out


@tools.tool
def car_schedule() -> str:
    """Показать полный регламент обслуживания."""
    data = _load()
    schedule = data["schedule"]

    out = "📅 РЕГЛАМЕНТ ОБСЛУЖИВАНИЯ:\n" + "━" * 35 + "\n"
    for key, spec in schedule.items():
        out += f"  • {spec['name']}: каждые {spec['km']:,} км / {spec['months']} мес\n".replace(",", " ")

    return out
