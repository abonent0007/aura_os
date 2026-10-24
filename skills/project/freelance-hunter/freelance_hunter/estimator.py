import json
import re
from dataclasses import dataclass
from typing import Optional, Protocol

from .models import Order

DEFAULT_PROMPT = (
    "Оцени фриланс-заказ и предложи короткий отклик от первого лица. "
    'Ответь строго JSON без пояснений: {{"price": число, "days": число, "proposal": строка}}.\n'
    "Заказ: {title}\nОписание: {description}"
)


@dataclass(frozen=True)
class Estimate:
    price: float
    days: int
    proposal: str
    is_fallback: bool = False


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        ...


class Estimator:
    def __init__(
        self,
        client: LLMClient,
        prompt_template: str = DEFAULT_PROMPT,
        fallback_price: float = 3000.0,
        fallback_days: int = 3,
        max_consecutive_failures: int = 3,
    ) -> None:
        self.client = client
        self.prompt_template = prompt_template
        self.fallback_price = fallback_price
        self.fallback_days = fallback_days
        self.max_consecutive_failures = max_consecutive_failures
        self._consecutive_failures = 0

    def estimate(self, order: Order) -> Estimate:
        fallback = self._fallback(order)
        if self._consecutive_failures >= self.max_consecutive_failures:
            return fallback
        prompt = self.prompt_template.format(title=order.title, description=order.description)
        try:
            raw = self.client.complete(prompt)
        except Exception:
            self._consecutive_failures += 1
            return fallback
        self._consecutive_failures = 0
        data = _extract_json(raw)
        if not isinstance(data, dict):
            return fallback
        price = _as_price(data.get("price"))
        days = _as_days(data.get("days"))
        proposal = data.get("proposal")
        proposal_text = proposal.strip() if isinstance(proposal, str) else ""
        # Хотя бы одно поле пришлось взять из заглушки — помечаем
        used_fallback = price is None or days is None or not proposal_text
        return Estimate(
            price=price if price is not None else fallback.price,
            days=days if days is not None else fallback.days,
            proposal=proposal_text or fallback.proposal,
            is_fallback=used_fallback,
        )

    def _fallback(self, order: Order) -> Estimate:
        return Estimate(
            price=float(self.fallback_price),
            days=int(self.fallback_days),
            proposal=(
                f"Здравствуйте! Готов взяться за «{order.title}» и сдать в срок. "
                "Уточню пару деталей и сразу приступлю."
            ),
            is_fallback=True,
        )


def _extract_json(raw: Optional[str]):
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _as_price(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    elif isinstance(value, str):
        cleaned = value.replace(" ", "").replace("₽", "").replace("руб.", "").replace("руб", "").strip()
        try:
            price = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    return price if price > 0 else None


def _as_days(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        days = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        days = int(value.strip())
    else:
        return None
    return days if days > 0 else None
