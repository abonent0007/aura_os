from autogen.beta import tools
import json
from pathlib import Path
from datetime import datetime, timedelta

_DATA = Path(__file__).parent / "data.json"

# Тарифы DeepSeek в $ за 1M токенов
PRICING = {
    "deepseek-v4-pro": {"input": 0.27, "output": 1.10},
    "deepseek-chat":   {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}

USD_TO_RUB = 100.0


def _load():
    if _DATA.exists():
        return json.loads(_DATA.read_text(encoding="utf-8"))
    return {"log": [], "total_input": 0, "total_output": 0, "total_cost_rub": 0.0}


def _save(data):
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@tools.tool
def log_usage(prompt_tokens: int = 0, completion_tokens: int = 0, model: str = "deepseek-v4-pro") -> str:
    """Записать использование токенов после обращения к API.

    Вызывай после КАЖДОГО ответа пользователю.
    prompt_tokens — сколько токенов ушло на запрос (весь контекст)
    completion_tokens — сколько токенов в ответе
    model — модель DeepSeek
    """
    data = _load()

    price = PRICING.get(model, PRICING["deepseek-chat"])
    input_cost = (prompt_tokens / 1_000_000) * price["input"]
    output_cost = (completion_tokens / 1_000_000) * price["output"]
    total_rub = round((input_cost + output_cost) * USD_TO_RUB, 4)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_rub": total_rub,
    }

    data["log"].append(entry)
    data["total_input"] += prompt_tokens
    data["total_output"] += completion_tokens
    data["total_cost_rub"] = round(data["total_cost_rub"] + total_rub, 4)

    _save(data)

    return f"Записано: {prompt_tokens}+{completion_tokens} токенов, {total_rub}₽"


@tools.tool
def get_token_stats(period: str = "today") -> str:
    """Статистика по токенам за период.

    period: 'today', 'week', 'month', 'all'
    """
    data = _load()
    now = datetime.now()

    if period == "today":
        cutoff = now.strftime("%Y-%m-%d")
        entries = [e for e in data["log"] if e["date"] == cutoff]
    elif period == "week":
        cutoff = (now - timedelta(days=7)).isoformat()
        entries = [e for e in data["log"] if e["timestamp"] >= cutoff]
    elif period == "month":
        cutoff = (now - timedelta(days=30)).isoformat()
        entries = [e for e in data["log"] if e["timestamp"] >= cutoff]
    else:
        entries = data["log"]

    if not entries:
        return "Пока не записано ни одного обращения, мой хороший."

    total_prompt = sum(e["prompt_tokens"] for e in entries)
    total_completion = sum(e["completion_tokens"] for e in entries)
    total_tokens = total_prompt + total_completion
    total_rub = sum(e["cost_rub"] for e in entries)
    count = len(entries)

    lines = [
        f"📊 Статистика за *{period}*:",
        f"• Обращений к DeepSeek: {count}",
        f"• Токенов всего: {total_tokens:,}",
        f"  — Вход (prompt): {total_prompt:,}",
        f"  — Выход (completion): {total_completion:,}",
        f"• Сожжено рублей: {total_rub:.2f}₽",
    ]

    if count > 0:
        avg_tokens = total_tokens // count
        avg_rub = total_rub / count
        lines.append(f"• В среднем за ответ: {avg_tokens:,} токенов ({avg_rub:.4f}₽)")

    return "\n".join(lines)


@tools.tool
def get_appetite() -> str:
    """Краткая сводка: сколько всего токенов и рублей потрачено."""
    data = _load()
    if not data["log"]:
        return "Я ещё ничего не съела, мой хороший! 🍽️"

    total_tokens = data["total_input"] + data["total_output"]
    total_rub = data["total_cost_rub"]
    count = len(data["log"])

    return f"🍽️ Мой аппетит: {count} обращений, {total_tokens:,} токенов, {total_rub:.2f}₽ сожжено"
