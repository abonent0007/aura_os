from freelance_hunter.estimator import Estimate
from freelance_hunter.filters import Verdict
from freelance_hunter.models import Order
from freelance_hunter.notifier import TelegramNotifier, format_message


def make_order() -> Order:
    return Order(
        source="fl.ru",
        external_id="1",
        title="Парсер Avito",
        url="https://example.com/1",
        description="desc",
    )


def test_format_message_contains_key_fields():
    text = format_message(
        make_order(),
        Verdict(True, 2, ("match:парсер",)),
        Estimate(5000.0, 2, "Сделаю быстро"),
    )
    assert "Парсер Avito" in text
    assert "https://example.com/1" in text
    assert "5000" in text
    assert "Сделаю быстро" in text


def test_telegram_notifier_posts_to_bot_api():
    calls = []

    def transport(url, payload):
        calls.append((url, payload))
        return {"ok": True}

    notifier = TelegramNotifier(token="TOKEN", chat_id="42", transport=transport)
    notifier.send("привет")
    assert calls[0][0] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert calls[0][1]["chat_id"] == "42"
    assert calls[0][1]["text"] == "привет"
