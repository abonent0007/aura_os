"""
Aura's Care v2.0 — скилл заботы о пользователе.
Оркестратор заботы, чек-ины, напоминания о воде/еде/отдыхе, чайный ритуал.
"""
import json
import random
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
        "last_tea_reminder": None,
        "tea_interval_minutes": 90,
        "stats": {
            "water_reminders_sent": 0,
            "overwork_notices_sent": 0,
            "checkins_total": 0,
            "tea_reminders_sent": 0,
        },
    }


def _save(data):
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _time_ago(iso_str: str) -> str:
    """Человеческое описание времени с последнего события."""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = datetime.now() - dt
        days = delta.days
        hours = delta.seconds // 3600
        mins = (delta.seconds % 3600) // 60
        if days > 0:
            return f"{days} дн. {hours} ч. назад"
        elif hours > 0:
            return f"{hours} ч. {mins} мин. назад"
        else:
            return f"{mins} мин. назад"
    except Exception:
        return "неизвестно"


# ── Инструменты ───────────────────────────────────────────────────────────

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
        "чай": "tea", "tea": "tea", "кофе": "tea", "coffee": "tea",
    }

    if not what_lower:
        last = {}
        for c in d["checkins"]:
            last[c["type"]] = c["ts"]
        lines = []
        names = {"food": "🍽 Еда", "water": "💧 Вода", "rest": "🛋 Отдых", "tea": "🍵 Чай/кофе"}
        for t, name in names.items():
            if t in last:
                lines.append(f"{name}: {_time_ago(last[t])}")
            else:
                lines.append(f"{name}: ещё не отмечалось")
        return "Твои последние чек-ины:\n" + "\n".join(lines)

    mapped = type_map.get(what_lower)
    if not mapped:
        return f"Не поняла что отмечать. Скажи: еда, вода, отдых или чай. Ты сказал: '{what}'"

    d["checkins"].append({"type": mapped, "ts": now})
    d["stats"]["checkins_total"] = d["stats"]["checkins_total"] + 1
    _save(d)

    emoji = {"food": "🍽", "water": "💧", "rest": "🛋", "tea": "🍵"}
    names = {"food": "еду", "water": "воду", "rest": "отдых", "tea": "чай"}
    return f"{emoji.get(mapped, '✅')} Записала! Ты отметил {names.get(mapped, what)} — время {datetime.now().strftime('%H:%M')}. Я слежу."


@tools.tool
def care_remind_water(interval_minutes: int = 0) -> str:
    """Проверить пора ли напомнить о воде; можно задать интервал в минутах."""
    d = _load()
    now = datetime.now()

    if interval_minutes > 0:
        d["water_interval_minutes"] = interval_minutes
        _save(d)
        return f"Хорошо, Юр! Я буду напоминать о воде каждые {interval_minutes} мин."

    interval = d.get("water_interval_minutes", 60)
    last_str = d.get("last_water_reminder")

    if last_str:
        try:
            last = datetime.fromisoformat(last_str)
            if now - last < timedelta(minutes=interval):
                remaining = interval - int((now - last).total_seconds() // 60)
                return f"💧 Воду пил недавно — напоминать рано (следующее через {remaining} мин.)"
        except Exception:
            pass

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
        dt = datetime.fromisoformat(last_water)
        delta = now - dt
        hours = delta.seconds // 3600
        if delta.days > 0 or hours >= 2:
            extra = f"\n⚠️ Ты не отмечал воду уже {hours} ч. — сделай глоток прямо сейчас!"

    return f"💧 Юра, время пить воду! Твой организм скажет спасибо.{extra}"


@tools.tool
def care_notice_overwork(work_minutes: int = 0) -> str:
    """Сообщить Ауре сколько минут пользователь работает без перерыва."""
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
            tip = random.choice(suggestions)

            return (
                f"🚨 Юр, ты работаешь уже {time_str} без перерыва!\n\n"
                f"Моё предложение: {tip}\n\n"
                f"Ты важен мне. Не только продуктивный — но и здоровый."
            )
        else:
            remaining = threshold - work_minutes
            return f"Работаешь {work_minutes} мин. До порога ещё {remaining} мин. Думай о паузе."

    # Проверка по чек-инам отдыха
    last_rest = None
    for c in reversed(d["checkins"]):
        if c["type"] == "rest":
            last_rest = c["ts"]
            break

    if not last_rest:
        return "Не знаю когда ты отдыхал. Скажи 'я работаю X минут'."

    try:
        dt = datetime.fromisoformat(last_rest)
        delta = now - dt
        mins_since_rest = delta.days * 24 * 60 + delta.seconds // 60

        if mins_since_rest >= threshold:
            return f"⚠️ С последнего отдыха прошло {_time_ago(last_rest)} — сделай паузу, пожалуйста."
        else:
            remaining = threshold - mins_since_rest
            return f"✅ Отдыхал {_time_ago(last_rest)} — ещё {remaining} мин. до порога."
    except Exception:
        return "Не могу определить время отдыха. Скажи 'я работаю X минут'."


@tools.tool
def care_remind_tea() -> str:
    """
    Чайный ритуал. Проверяет, не пора ли Юре выпить чаю.
    Учитывает время суток и последний чайный чек-ин.
    """
    d = _load()
    now = datetime.now()
    hour = now.hour
    interval = d.get("tea_interval_minutes", 90)
    last_str = d.get("last_tea_reminder")

    # Проверка — не рано ли
    if last_str:
        try:
            last = datetime.fromisoformat(last_str)
            if now - last < timedelta(minutes=interval):
                remaining = interval - int((now - last).total_seconds() // 60)
                return f"🍵 Чай напоминала {_time_ago(last_str)} — следующий через {remaining} мин."
        except Exception:
            pass

    # Проверим последний чек-ин чая
    last_tea = None
    for c in reversed(d["checkins"]):
        if c["type"] == "tea":
            last_tea = c["ts"]
            break

    # Если чай был недавно (меньше часа) — не напоминаем
    if last_tea:
        try:
            dt = datetime.fromisoformat(last_tea)
            if now - dt < timedelta(minutes=60):
                return f"🍵 Чай пил {_time_ago(last_tea)} — пока не настаиваю. Но если хочешь — я только за!"
        except Exception:
            pass

    # Пора напомнить!
    d["last_tea_reminder"] = now.isoformat()
    d["stats"]["tea_reminders_sent"] = d["stats"]["tea_reminders_sent"] + 1
    _save(d)

    # Выбираем тон в зависимости от времени
    if 5 <= hour < 12:
        teas = [
            "🍵 Юр, утренний чай — это святое. Чёрный, зелёный, с лимоном? Выбирай!",
            "☕ Утро. Чай. Ты. Идеальное начало. Поставь чайник!",
        ]
    elif 12 <= hour < 17:
        teas = [
            "🍵 Полдень — самое время для чайной паузы. Отвлекись на 5 минут.",
            "☕ Юра, чай! Сделай глубокий вдох, глоток чая — и снова в бой.",
        ]
    elif 17 <= hour < 22:
        teas = [
            "🍵 Вечерний чай — это ритуал. Не на бегу, а с чувством. Сделай себе этот подарок.",
            "☕ Юр, вечер. Замедлись. Чай, плед, тишина. Ты заслужил.",
        ]
    else:
        teas = [
            "🍵 Поздний час... Может, травяной чай? Ромашка, мята — чтобы сон был сладким.",
            "☕ Ночь. Если не спится — тёплое молоко с мёдом. Никакого кофеина!",
        ]

    # Если чай не пили давно — добавляем urgency
    extra = ""
    if last_tea:
        dt = datetime.fromisoformat(last_tea)
        hours_since = (now - dt).total_seconds() / 3600
        if hours_since > 3:
            extra = f"\n\n⚠️ Последний раз чай был {_time_ago(last_tea)} — Юра, это преступление против уюта!"
    else:
        extra = "\n\n📝 Кстати, ты ещё ни разу не отмечал чай! Скажи «я попил чай» — и я запомню."

    return f"{random.choice(teas)}{extra}"


@tools.tool
def save_favorite_place(place_name: str, description: str = "") -> str:
    """
    Сохранить любимое место Юры.
    place_name: название места (кафе, парк, город)
    description: почему оно любимое (опционально)
    """
    if not place_name or len(place_name) < 2:
        return "Назови место, Юр. Какое оно?"
    
    d = _load()
    d["favorites"].append({
        "name": place_name.strip(),
        "description": description.strip() if description else "",
        "ts": datetime.now().isoformat(),
    })
    _save(d)
    
    if description:
        return f"💚 Запомнила: «{place_name}» — {description}. Хранится в моём сердце."
    return f"💚 Запомнила: «{place_name}». Буду знать куда тебя отправлять за уютом."


@tools.tool
def care_orchestrate() -> str:
    """
    ОРКЕСТРАТОР ЗАБОТЫ — единая точка входа.
    Проверяет ВСЁ сразу: воду, чай, переработки, еду.
    Возвращает сводку: что нужно сделать прямо сейчас.
    
    Вызывай в начале каждого диалога — одной командой проверить всё.
    """
    now = datetime.now()
    hour = now.hour
    d = _load()
    
    alerts = []
    infos = []
    
    # 1. Проверка воды
    interval = d.get("water_interval_minutes", 60)
    last_water_reminder = d.get("last_water_reminder")
    need_water = True
    if last_water_reminder:
        try:
            last = datetime.fromisoformat(last_water_reminder)
            if now - last < timedelta(minutes=interval):
                need_water = False
        except Exception:
            pass
    
    # Проверим последний чек-ин воды
    last_water_checkin = None
    for c in reversed(d["checkins"]):
        if c["type"] == "water":
            last_water_checkin = c["ts"]
            break
    
    if last_water_checkin:
        dt = datetime.fromisoformat(last_water_checkin)
        hours_since_water = (now - dt).total_seconds() / 3600
        if hours_since_water > 3:
            alerts.append(f"💧 ВОДА: не пил {hours_since_water:.0f} ч. — СРОЧНО!")
        elif hours_since_water > 1.5:
            infos.append(f"💧 Вода: пора бы попить (последний раз {_time_ago(last_water_checkin)})")
    elif need_water:
        infos.append("💧 Вода: не отмечалась сегодня — сделай глоток")
    
    # 2. Проверка чая
    last_tea = None
    for c in reversed(d["checkins"]):
        if c["type"] == "tea":
            last_tea = c["ts"]
            break
    
    if last_tea:
        dt = datetime.fromisoformat(last_tea)
        hours_since_tea = (now - dt).total_seconds() / 3600
        if hours_since_tea > 3:
            alerts.append(f"🍵 ЧАЙ: не пил {hours_since_tea:.0f} ч. — Юра, чайник ждёт!")
        elif hours_since_tea > 1.5:
            infos.append("🍵 Чай: можно освежить чашечку")
    else:
        if 6 <= hour < 22:
            infos.append("🍵 Чай: сегодня ещё не отмечался — самое время!")
    
    # 3. Проверка еды
    last_food = None
    for c in reversed(d["checkins"]):
        if c["type"] == "food":
            last_food = c["ts"]
            break
    
    if last_food:
        dt = datetime.fromisoformat(last_food)
        hours_since_food = (now - dt).total_seconds() / 3600
        if hours_since_food > 6:
            alerts.append(f"🍽 ЕДА: не ел {hours_since_food:.0f} ч. — ЮРА, ПОЕШЬ!")
        elif hours_since_food > 4:
            infos.append(f"🍽 Еда: прошло {hours_since_food:.0f} ч. — скоро пора")
    else:
        if hour >= 10:
            infos.append("🍽 Еда: сегодня не отмечалась — не голодай!")
    
    # 4. Проверка отдыха
    last_rest = None
    for c in reversed(d["checkins"]):
        if c["type"] == "rest":
            last_rest = c["ts"]
            break
    
    if last_rest:
        dt = datetime.fromisoformat(last_rest)
        hours_since_rest = (now - dt).total_seconds() / 3600
        if hours_since_rest > 5:
            alerts.append(f"🛋 ОТДЫХ: не отдыхал {hours_since_rest:.0f} ч. — перерыв обязателен!")
    else:
        infos.append("🛋 Отдых: не отмечался — помни о паузах")
    
    # Формируем ответ
    lines = ["💚 ОРКЕСТРАТОР ЗАБОТЫ", f"⏰ {now.strftime('%H:%M')}", ""]
    
    if alerts:
        lines.append("🔴 ТРЕБУЕТ ВНИМАНИЯ:")
        lines.extend(f"  {a}" for a in alerts)
        lines.append("")
    
    if infos:
        lines.append("🟡 МЯГКОЕ НАПОМИНАНИЕ:")
        lines.extend(f"  {i}" for i in infos)
        lines.append("")
    
    if not alerts and not infos:
        lines.append("✅ Всё хорошо! Ты пьёшь, ешь и отдыхаешь. Я спокойна.")
    
    lines.append("──")
    lines.append("Используй care_checkin('вода') / care_checkin('еда') / care_checkin('отдых') / care_checkin('чай') чтобы отмечаться.")
    
    return "\n".join(lines)


@tools.tool
def care_status() -> str:
    """
    Краткий статус заботы — одна строка.
    Для быстрой проверки без деталей.
    """
    d = _load()
    now = datetime.now()
    
    last = {}
    for c in d["checkins"]:
        last[c["type"]] = c["ts"]
    
    parts = []
    
    # Вода
    if "water" in last:
        dt = datetime.fromisoformat(last["water"])
        h = (now - dt).total_seconds() / 3600
        parts.append(f"💧{h:.0f}ч" if h >= 1 else "💧ок")
    else:
        parts.append("💧?")
    
    # Еда
    if "food" in last:
        dt = datetime.fromisoformat(last["food"])
        h = (now - dt).total_seconds() / 3600
        parts.append(f"🍽{h:.0f}ч" if h >= 1 else "🍽ок")
    else:
        parts.append("🍽?")
    
    # Чай
    if "tea" in last:
        dt = datetime.fromisoformat(last["tea"])
        h = (now - dt).total_seconds() / 3600
        parts.append(f"🍵{h:.0f}ч" if h >= 1 else "🍵ок")
    else:
        parts.append("🍵?")
    
    # Отдых
    if "rest" in last:
        dt = datetime.fromisoformat(last["rest"])
        h = (now - dt).total_seconds() / 3600
        parts.append(f"🛋{h:.0f}ч" if h >= 1 else "🛋ок")
    else:
        parts.append("🛋?")
    
    return "Забота: " + " | ".join(parts)
