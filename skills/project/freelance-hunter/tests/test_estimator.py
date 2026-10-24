from freelance_hunter.estimator import Estimate, Estimator
from freelance_hunter.models import Order


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


class BrokenLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise RuntimeError("network down")


def make_order(title: str = "Нужен парсер Avito", description: str = "Выгрузить объявления в Excel") -> Order:
    return Order(source="fl.ru", external_id="1", title=title, description=description)


def test_estimates_from_valid_json():
    client = FakeLLM('{"price": 5000, "days": 2, "proposal": "Сделаю за два дня"}')
    estimate = Estimator(client).estimate(make_order())
    assert estimate == Estimate(price=5000.0, days=2, proposal="Сделаю за два дня")


def test_parses_json_inside_code_fence():
    client = FakeLLM('```json\n{"price": 7000, "days": 3, "proposal": "Берусь"}\n```')
    estimate = Estimator(client).estimate(make_order())
    assert estimate.price == 7000.0
    assert estimate.days == 3
    assert estimate.proposal == "Берусь"


def test_falls_back_on_garbage():
    client = FakeLLM("не могу оценить")
    estimate = Estimator(client, fallback_price=3000, fallback_days=4).estimate(make_order())
    assert estimate.price == 3000.0
    assert estimate.days == 4
    assert "Нужен парсер Avito" in estimate.proposal


def test_falls_back_when_client_raises():
    estimate = Estimator(BrokenLLM(), fallback_price=2500, fallback_days=5).estimate(make_order())
    assert estimate.price == 2500.0
    assert estimate.days == 5


def test_stops_calling_client_after_repeated_failures():
    client = BrokenLLM()
    estimator = Estimator(client, fallback_price=1000, fallback_days=1)
    for _ in range(5):
        estimate = estimator.estimate(make_order())
        assert estimate.price == 1000.0
    assert client.calls == 3


def test_fills_missing_fields_from_fallback():
    client = FakeLLM('{"price": 5000}')
    estimate = Estimator(client, fallback_price=1000, fallback_days=7).estimate(make_order())
    assert estimate.price == 5000.0
    assert estimate.days == 7
    assert estimate.proposal


def test_rejects_non_positive_price():
    client = FakeLLM('{"price": -100, "days": 2, "proposal": "ок"}')
    estimate = Estimator(client, fallback_price=3000, fallback_days=2).estimate(make_order())
    assert estimate.price == 3000.0


def test_prompt_contains_order_text():
    client = FakeLLM('{"price": 1, "days": 1, "proposal": "ок"}')
    Estimator(client).estimate(make_order())
    assert "Нужен парсер Avito" in client.prompts[0]
    assert "Выгрузить объявления в Excel" in client.prompts[0]


def test_valid_estimate_is_not_fallback():
    client = FakeLLM('{"price": 5000, "days": 2, "proposal": "Сделаю"}')
    estimate = Estimator(client).estimate(make_order())
    assert estimate.is_fallback is False


def test_fallback_is_flagged():
    estimate = Estimator(BrokenLLM(), fallback_price=2500, fallback_days=5).estimate(make_order())
    assert estimate.is_fallback is True


def test_partial_fallback_is_flagged():
    """Цена есть, срок и отклик — из заглушки: помечаем."""
    client = FakeLLM('{"price": 5000}')
    estimate = Estimator(client, fallback_price=1000, fallback_days=7).estimate(make_order())
    assert estimate.price == 5000.0
    assert estimate.is_fallback is True
