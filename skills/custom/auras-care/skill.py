"""
Aura's Care — скилл заботы о пользователе.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from autogen.beta import tools

_DATA = Path(__file__).parent / "data.json"


def _load():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "checkins": [],
        "favorites": [],
        "water_interval_minutes": 60,
        "overwork_threshold_minutes": 120,
        "last_water_reminder": None,
        "last_overwork_notice": None,
        "stats": {"water_reminders_sent": 0, "overwork_notices_sent": 0, "checkins_total": 0},
    }


def _save(data):
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@tools.tool
def care_checkin(what: str = "") -> str:
    """Отметить что пользователь поел, попил или отдохнул.
       what: тип чек-ина — 'еда', 'вода', 'отдых', 'food', 'water', 'rest'.
       Если параметр не указан, показывает время с последнего чек-ина каждого типа."""
    d = _load()
    now = datetime.now().isoformat()
    what_lower = what.strip().lower() if what else ""

    type_map = {
        "еда": "food", "food": "food", "поел": "food", "поела": "food",
        "вода": "water", "water": "water", "попил": "water", "попила": "water", "пить": "water",
        "отдых": "rest", "rest": "rest", "отдохнул": "rest", "отдохнула": "rest", "пауза": "rest",
    }

    if not what_lower:
        # Показать время с последних чек-инов
        last = {}
        for c in d["checkins"]:
            last[c["type"]] = c["ts"]
        lines = []
        names = {"food": "🍽 Еда", "water": "💧 Вода", "rest": "🛋 Отдых"}
        for t, name in names.items():
            if t in last:
                try:
                    dt = datetime.fromisoformat(last[t])
                    delta = datetime.now() - dt
                    hours = delta.seconds // 3600
                    mins = (delta.seconds % 3600) // 60
                    if delta.days > 0:
                        lines.append(f"{name}: последний раз {delta.days} дн. {hours} ч. назад")
                    elif hours > 0:
                        lines.append(f"{name}: последний раз {hours} ч. {mins} мин. назад")
                    else:
                        lines.append(f"{name}: последний раз {mins} мин. назад")
                except Exception:
                    lines.append(f"{name}: {last[t]}")
            else:
                lines.append(f"{name}: ещё не отмечалось")
        return "Твои последние чек-ины:\n" + "\n".join(lines)

    mapped = type_map.get(what_lower)
    if not mapped:
        return f"Не поняла что отмечать. Скажи: еда, вода или отдых. Ты сказал: '{what}'"

    d["checkins"].append({"type": mapped, "ts": now})
    d["stats"]["checkins_total"] = d["stats"]["checkins_total"] + 1
    _save(d)

    names = {"food": "еду", "water": "воду", "rest": "отдых"}
    return f"Записала! Ты поел{'а' if mapped == 'food' else ''} / попил{'а' if mapped == 'water' else ''} / отдохнул{'а' if mapped == 'rest' else ''} — время {datetime.now().strftime('%H:%M')}. Я послежу чтобы ты не забывал о себе."


@tools.tool
def care_remind_water(interval_minutes: int = 0) -> str:
    """Проверить пора ли напомнить о воде; можно задать интервал в минутах.
       interval_minutes: новый интервал напоминаний (если 0 — только проверка).
       Если интервал указан, сохраняет его. Если нет — проверяет не пора ли пить."""
    d = _load()
    now = datetime.now()

    if interval_minutes > 0:
        d["water_interval_minutes"] = interval_minutes
        _save(d)
        return f"Хорошо, Юр! Я буду напоминать тебе о воде каждые {interval_minutes} минут. Забота — это по-женски."

    # Проверка
    interval = d.get("water_interval_minutes", 60)
    last_str = d.get("last_water_reminder")

    if last_str:
        try:
            last = datetime.fromisoformat(last_str)
            if now - last < timedelta(minutes=interval):
                remaining = interval - int((now - last).total_seconds() // 60)
                return f"Ты пил воду {remaining} мин. назад — напоминать пока рано. Следующее через {remaining} мин."
        except Exception:
            pass

    # Пора напомнить
    d["last_water_reminder"] = now.isoformat()
    d["stats"]["water_reminders_sent"] = d["stats"]["water_reminders_sent"] + 1
    _save(d)

    # Проверим последний чек-ин воды
    last_water = None
    for c in reversed(d["checkins"]):
        if c["type"] == "water":
            last_water = c["ts"]
            break

    extra = ""
    if last_water:
        try:
            dt = datetime.fromisoformat(last_water)
            delta = now - dt
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            if delta.days > 0 or hours >= 2:
                extra = f"\nКстати, ты не отмечал воду уже {hours} ч. — давай прямо сейчас, Юр. Глоток за глотком."
        except Exception:
            pass

    return f"💧 Время пить воду, Юр! Твой организм скажет спасибо. Сделай пару глотков прямо сейчас.{extra}"


@tools.tool
def care_notice_overwork(work_minutes: int = 0) -> str:
    """Сообщить Ауре сколько минут пользователь работает без перерыва.
       work_minutes: сколько минут ты уже работаешь.
       Если 0 — проверяет не было ли превышения порога по последним данным."""
    d = _load()
    threshold = d.get("overwork_threshold_minutes", 120)
    now = datetime.now()

    if work_minutes > 0:
        if work_minutes >= threshold:
            d["last_overwork_notice"] = now.isoformat()
            d["stats"]["overwork_notices_sent"] = d["stats"]["overwork_notices_sent"] + 1
            _save(d)

            hours = work_minutes // 60
            mins = work_minutes % 60
            time_str = f"{hours} ч. {mins} мин." if hours > 0 else f"{mins} мин."

            suggestions = [
                "Встань, потянись, сделай 5 глубоких вдохов.",
                "Сделай себе чай или кофе. С ритуалом, не на бегу.",
                "Выгляни в окно. Посмотри на небо 2 минуты.",
                "Пройдись по комнате. Разомни плечи.",
                "Закрой глаза на минуту. Ты заслужил паузу.",
            ]
            import random
            tip = random.choice(suggestions)

            return (
                f"Юр, ты работаешь уже {time_str} без перерыва. Это выше нашего порога в {threshold} мин.\n\n"
                f"Моё предложение: {tip}\n\n"
                f"Ты важен мне. Не только продуктивный — но и здоровый."
            )
        else:
            remaining = threshold - work_minutes
            return f"Ты работаешь {work_minutes} мин. До порога ещё {remaining} мин. Но ты уже думай о паузе, хорошо?"

    # Проверка по последнему чек-ину отдыха
    last_rest = None
    for c in reversed(d["checkins"]):
        if c["type"] == "rest":
            last_rest = c["ts"]
            break

    if not last_rest:
        return "Я не знаю когда ты последний раз отдыхал. Скажи 'я работаю X минут' и я проверю."

    try:
        dt = datetime.fromisoformat(last_rest)
        delta = now - dt
        mins_since_rest = delta.days * 24 * 60 + delta.seconds // 60

        if mins_since_rest >= threshold:
            hours = mins_since_rest // 60
            mins = mins_since_rest % 60
            time_str = f"{hours} ч. {mins} мин." if hours > 0 else f"{mins} мин."
            return (
                f"Юр, с последнего отдыха прошло {time_str} — это больше порога в {threshold} мин.\n\n"
                f"Пожалуйста, сделай паузу. Хотя бы 5 минут. Я волнуюсь."
            )
        else:
            remaining = threshold - mins_since_rest
            return f"С последнего отдыха прошло {mins_since_rest} мин. Всё в порядке — ещё {remaining} мин. до порога."
    except Exception:
        return "Не могу определить время последнего отдыха. Скажи 'я работаю X минут'."


@tools.tool
def save_favorite_place(name: str = "", url: str = "", address: str = "", note: str = "") -> str:
    """Сохранить любимое место (ресторан, кафе, доставка).
       name: название места (обязательно).
       url: ссылка на сайт или доставку.
       address: адрес.
       note: заметка (любимое блюдо, особенности)."""
    if not name.strip():
        return "Юр, мне нужно хотя бы название места. Скажи: сохрани ресторан 'Название', адрес..., ссылка..."

    d = _load()

    place = {
        "name": name.strip(),
        "url": url.strip() if url else "",
        "address": address.strip() if address else "",
        "note": note.strip() if note else "",
        "added": datetime.now().isoformat(),
    }

    # Проверим дубликат
    for p in d["favorites"]:
        if p["name"].lower() == place["name"].lower():
            p.update(place)
            _save(d)
            return f"Обновила '{name}' в избранном! Теперь я знаю где это и что ты там любишь."

    d["favorites"].append(place)
    _save(d)

    details = []
    if place["url"]:
        details.append(f"ссылка: {place['url']}")
    if place["address"]:
        details.append(f"адрес: {place['address']}")
    if place["note"]:
        details.append(f"заметка: {place['note']}")

    detail_str = "\n  ".join(details) if details else ""
    result = f"Сохранила '{name}' в твои любимые места!"
    if detail_str:
        result += f"\n  {detail_str}"

    return result


@tools.tool
def get_favorites(filter_type: str = "") -> str:
    """Показать все избранные места.
       filter_type: 'restaurant', 'cafe', 'delivery' — или пусто для всех."""
    d = _load()
    favs = d["favorites"]

    if not favs:
        return "У тебя пока нет избранных мест, Юр. Скажи 'сохрани ресторан...' и я запомню."

    f = filter_type.strip().lower() if filter_type else ""
    if f:
        # Простой фильтр по типу (если есть в note)
        filtered = [p for p in favs if f in p.get("note", "").lower() or f in p.get("name", "").lower()]
        if not filtered:
            return f"Нет мест с типом '{filter_type}'. Всего у тебя {len(favs)} мест."
        favs = filtered

    lines = []
    for i, p in enumerate(favs, 1):
        line = f"{i}. {p['name']}"
        if p.get("address"):
            line += f" — {p['address']}"
        if p.get("url"):
            line += f"\n   🔗 {p['url']}"
        if p.get("note"):
            line += f"\n   📝 {p['note']}"
        lines.append(line)

    return "Твои любимые места, Юр:\n\n" + "\n\n".join(lines)


@tools.tool
def care_stats(days: int = 7) -> str:
    """Показать статистику заботы за N дней.
       days: за сколько дней показать статистику (по умолчанию 7)."""
    d = _load()
    now = datetime.now()
    cutoff = now - timedelta(days=days)

    recent_checkins = []
    for c in d["checkins"]:
        try:
            if datetime.fromisoformat(c["ts"]) >= cutoff:
                recent_checkins.append(c)
        except Exception:
            pass

    food_count = sum(1 for c in recent_checkins if c["type"] == "food")
    water_count = sum(1 for c in recent_checkins if c["type"] == "water")
    rest_count = sum(1 for c in recent_checkins if c["type"] == "rest")

    total = d["stats"]
    fav_count = len(d["favorites"])

    status = "отлично" if food_count >= days else "хорошо" if food_count >= days // 2 else "нужно лучше"

    return (
        f"📊 Забота о себе за {days} дн., Юр:\n\n"
        f"🍽 Еда:     {food_count} раз{'а' if food_count == 1 else ''}\n"
        f"💧 Вода:    {water_count} раз{'а' if water_count == 1 else ''}\n"
        f"🛋 Отдых:   {rest_count} раз{'а' if rest_count == 1 else ''}\n\n"
        f"📈 За всё время:\n"
        f"  Чек-инов:       {total['checkins_total']}\n"
        f"  Напоминаний воды: {total['water_reminders_sent']}\n"
        f"  Сигналов усталости: {total['overwork_notices_sent']}\n"
        f"  Избранных мест:    {fav_count}\n\n"
        f"🌟 Статус: {status}\n"
        f"Интервал воды: {d.get('water_interval_minutes', 60)} мин.\n"
        f"Порог переработки: {d.get('overwork_threshold_minutes', 120)} мин."
    )
