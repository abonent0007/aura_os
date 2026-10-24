from typing import Callable, Protocol

from .estimator import Estimate
from .filters import Verdict
from .models import Order

Transport = Callable[[str, dict], dict]


class Notifier(Protocol):
    def send(self, text: str) -> None:
        ...


def format_message(order: Order, verdict: Verdict, estimate: Estimate) -> str:
    lines = [
        f"[{order.source}] {order.title}",
        f"Ссылка: {order.url}" if order.url else "",
        f"Оценка: {estimate.price:.0f} руб., срок {estimate.days} дн., скоринг {verdict.score}",
        f"Отклик: {estimate.proposal}",
    ]
    return "\n".join(line for line in lines if line)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, transport: Transport) -> None:
        self.token = token
        self.chat_id = chat_id
        self.transport = transport

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.transport(url, {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True})


class NullNotifier:
    """Заглушка: уведомления выключены (нет токена/чата или Telegram недоступен).

    Заказы всё равно сохраняются в БД со статусом 'new' — их показывает Аура.
    """

    silent = True

    def send(self, text: str) -> None:
        return None
