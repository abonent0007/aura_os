import pytest

from freelance_hunter.estimator import Estimate
from freelance_hunter.filters import Verdict
from freelance_hunter.models import Order
from freelance_hunter.storage import Storage


@pytest.fixture()
def storage(tmp_path):
    store = Storage(tmp_path / "orders.db")
    yield store
    store.close()


def make_order(external_id: str = "1") -> Order:
    return Order(
        source="fl.ru",
        external_id=external_id,
        title="Парсер",
        url="https://x/1",
        description="desc",
    )


def test_add_returns_true_for_new_order(storage):
    added = storage.add(make_order(), Verdict(True, 2, ("match:парсер",)), Estimate(5000.0, 2, "ок"))
    assert added is True
    assert storage.count() == 1


def test_add_returns_false_for_duplicate(storage):
    storage.add(make_order(), Verdict(True, 2, ()), Estimate(5000.0, 2, "ок"))
    added = storage.add(make_order(), Verdict(True, 2, ()), Estimate(9999.0, 5, "другое"))
    assert added is False
    assert storage.count() == 1


def test_same_external_id_from_different_sources_is_not_duplicate(storage):
    first = make_order()
    second = Order(source="kwork", external_id="1", title="Парсер", description="desc")
    assert storage.add(first, Verdict(True, 1, ()), None) is True
    assert storage.add(second, Verdict(True, 1, ()), None) is True
    assert storage.count() == 2


def test_exists_reflects_stored_orders(storage):
    assert storage.exists("fl.ru", "1") is False
    storage.add(make_order(), Verdict(True, 1, ()), None)
    assert storage.exists("fl.ru", "1") is True


def test_get_by_status_returns_only_matching(storage):
    storage.add(make_order("1"), Verdict(True, 1, ()), None, status="new")
    storage.add(make_order("2"), Verdict(True, 1, ()), None, status="sent")
    rows = storage.get_by_status("new")
    assert len(rows) == 1
    assert rows[0]["external_id"] == "1"


def test_set_status_updates_row(storage):
    storage.add(make_order(), Verdict(True, 1, ()), None)
    storage.set_status("fl.ru", "1", "answered")
    assert storage.get_by_status("answered")[0]["external_id"] == "1"


def test_estimate_fields_are_persisted(storage):
    storage.add(make_order(), Verdict(True, 2, ()), Estimate(4500.0, 3, "сделаю"))
    row = storage.get_by_status("new")[0]
    assert row["price"] == 4500.0
    assert row["days"] == 3
    assert row["proposal"] == "сделаю"
