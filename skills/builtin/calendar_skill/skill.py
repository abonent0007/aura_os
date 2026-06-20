# calendar_skill/skill.py — Встроенный скилл календаря v2.0
# Работа с датами, повторяющимися событиями, периодами

from datetime import date, datetime, timedelta
from autogen.beta import tools


@tools.tool
def get_today_date() -> str:
    """Сегодняшняя дата."""
    return date.today().strftime("%d.%m.%Y (%A)")

@tools.tool
def days_until_date(target_date: str) -> str:
    """Сколько дней до даты. Формат: YYYY-MM-DD."""
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        delta = (target - date.today()).days
        if delta < 0: return f"{target_date} прошло ({abs(delta)} дн. назад)"
        if delta == 0: return f"{target_date} — сегодня!"
        return f"До {target_date}: {delta} дн."
    except ValueError:
        return "Формат: YYYY-MM-DD"

@tools.tool
def add_days_to_date(start_date: str, days: int) -> str:
    """Прибавить дни к дате. start_date: YYYY-MM-DD, days: количество дней."""
    try:
        d = datetime.strptime(start_date, "%Y-%m-%d").date() + timedelta(days=days)
        return d.strftime("%Y-%m-%d (%A)")
    except ValueError:
        return "Формат: YYYY-MM-DD"

@tools.tool
def next_occurrence(day_of_month: int, months_ahead: int = 1) -> str:
    """
    Ближайшее вхождение дня месяца. Полезно для ежемесячных повторений.
    day_of_month: число месяца (1-31)
    months_ahead: на сколько месяцев вперёд смотреть
    """
    if day_of_month < 1 or day_of_month > 31:
        return "Число месяца должно быть 1-31"
    today = date.today()
    results = []
    for m in range(months_ahead + 1):
        d = today.replace(day=1) + timedelta(days=32 * m)
        d = d.replace(day=1) + timedelta(days=day_of_month - 1)
        if d > today:
            results.append(d.strftime("%d.%m.%Y (%A)"))
    return "Ближайшие повторения:\n" + "\n".join(f"  {r}" for r in results[:6])

@tools.tool
def days_in_month(year: int, month: int) -> str:
    """Количество дней в месяце."""
    import calendar
    days = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}: {days} дней"

@tools.tool
def week_number(target_date: str = None) -> str:
    """Номер недели для даты. По умолчанию — сегодня."""
    d = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else date.today()
    week = d.isocalendar()[1]
    return f"{d.strftime('%d.%m.%Y')} — неделя {week}"
