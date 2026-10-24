from freelance_hunter.estimator import Estimate
from freelance_hunter.filters import FilterConfig
from freelance_hunter.models import Order
from freelance_hunter.notifier import NullNotifier
from freelance_hunter.pipeline import Pipeline
from freelance_hunter.storage import Storage


class FakeCollector:
    def __init__(self, orders=None, error=None):
        self.orders = orders or []
        self.error = error

    def collect(self):
        if self.error:
            raise self.error
        return self.orders


class FakeEstimator:
    def __init__(self):
        self.calls = 0

    def estimate(self, order):
        self.calls += 1
        return Estimate(price=5000.0, days=2, proposal=f"Берусь: {order.title}")


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, text):
        self.messages.append(text)


class FlakyNotifier:
    def __init__(self, fail_times=1):
        self.fail_times = fail_times
        self.messages = []

    def send(self, text):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("telegram down")
        self.messages.append(text)


FILTER = FilterConfig(
    accept_keywords=("парсер", "бот"),
    reject_keywords=("интеграция",),
    min_score=1,
    min_length=10,
    max_length=500,
)


def make_pipeline(tmp_path, collectors):
    storage = Storage(tmp_path / "orders.db")
    notifier = FakeNotifier()
    estimator = FakeEstimator()
    pipeline = Pipeline(collectors, FILTER, estimator, storage, notifier)
    return pipeline, storage, notifier, estimator


def order(external_id, title="Нужен парсер", description="Собрать данные"):
    return Order(source="fl.ru", external_id=external_id, title=title, description=description)


def test_happy_path_stores_and_notifies_only_accepted(tmp_path):
    good = order("1")
    bad = order("2", title="Интеграция с CRM", description="Сложный проект надолго")
    pipeline, storage, notifier, estimator = make_pipeline(tmp_path, [FakeCollector([good, bad])])
    stats = pipeline.run_once()
    assert stats.fetched == 2
    assert stats.accepted == 1
    assert stats.stored == 1
    assert stats.notified == 1
    assert storage.count() == 1
    assert estimator.calls == 1
    assert len(notifier.messages) == 1
    assert "Нужен парсер" in notifier.messages[0]


def test_duplicates_are_not_notified_twice(tmp_path):
    pipeline, storage, notifier, estimator = make_pipeline(tmp_path, [FakeCollector([order("1")])])
    first = pipeline.run_once()
    second = pipeline.run_once()
    assert first.stored == 1
    assert second.duplicates == 1
    assert second.stored == 0
    assert estimator.calls == 1
    assert len(notifier.messages) == 1


def test_collector_error_does_not_break_other_collectors(tmp_path):
    pipeline, storage, notifier, estimator = make_pipeline(
        tmp_path,
        [FakeCollector(error=RuntimeError("feed down")), FakeCollector([order("1")])],
    )
    stats = pipeline.run_once()
    assert stats.errors == 1
    assert stats.stored == 1


def test_accepted_orders_get_sent_status(tmp_path):
    pipeline, storage, notifier, estimator = make_pipeline(tmp_path, [FakeCollector([order("1")])])
    pipeline.run_once()
    assert storage.get_by_status("sent")[0]["external_id"] == "1"


def test_notify_failure_still_stores_order(tmp_path):
    """Сбой уведомления (например, Telegram заблокирован) не теряет заказ."""
    storage = Storage(tmp_path / "orders.db")
    notifier = FlakyNotifier()
    estimator = FakeEstimator()
    pipeline = Pipeline([FakeCollector([order("1")])], FILTER, estimator, storage, notifier)
    first = pipeline.run_once()
    assert first.errors == 1
    assert first.stored == 1
    assert first.notified == 0
    assert storage.count() == 1
    # статус остался new — заказ ждёт доставки (Аура покажет его пользователю)
    assert storage.get_by_status("new")[0]["external_id"] == "1"


def test_null_notifier_keeps_status_new(tmp_path):
    """Telegram выключен: заказ сохраняется со статусом new и ждёт Ауру."""
    storage = Storage(tmp_path / "orders.db")
    estimator = FakeEstimator()
    pipeline = Pipeline([FakeCollector([order("1")])], FILTER, estimator, storage, NullNotifier())
    stats = pipeline.run_once()
    assert stats.stored == 1
    assert stats.notified == 1
    assert stats.errors == 0
    assert storage.get_by_status("new")[0]["external_id"] == "1"


class CollectorWithFilter(FakeCollector):
    """Коллектор со своим фильтром (как доски вакансий)."""

    def __init__(self, orders, filter_config):
        super().__init__(orders)
        self.filter_config = filter_config


def test_per_source_filter_is_used(tmp_path):
    """Свой фильтр источника перекрывает общий (строгий min_score режет заказ)."""
    strict = FilterConfig(
        accept_keywords=("парсер", "бот"),
        reject_keywords=(),
        min_score=2,
        min_length=10,
        max_length=500,
    )
    pipeline, storage, notifier, estimator = make_pipeline(
        tmp_path, [CollectorWithFilter([order("1")], strict)]
    )
    stats = pipeline.run_once()
    # «Нужен парсер Собрать данные» — только одно совпадение, порог 2 не пройден
    assert stats.accepted == 0
    assert stats.stored == 0
    assert estimator.calls == 0
