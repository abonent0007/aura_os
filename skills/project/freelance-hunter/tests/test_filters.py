from freelance_hunter.filters import FilterConfig, evaluate
from freelance_hunter.models import Order


def make_order(title: str, description: str = "") -> Order:
    return Order(source="test", external_id="1", title=title, description=description)


CFG = FilterConfig(
    accept_keywords=("парсер", "бот", "скрипт", "excel"),
    reject_keywords=("интеграция", "crm", "срочно"),
    min_score=1,
    min_length=30,
    max_length=300,
)


def test_accepts_simple_parser_order():
    order = make_order("Нужен парсер Avito", "Собрать данные по объявлениям в таблицу.")
    verdict = evaluate(order, CFG)
    assert verdict.accepted is True
    assert verdict.score >= 1
    assert "match:парсер" in verdict.reasons


def test_rejects_order_with_forbidden_keyword():
    order = make_order("Интеграция с CRM", "Настроить обмен данными между системами.")
    verdict = evaluate(order, CFG)
    assert verdict.accepted is False
    assert verdict.reasons == ("reject:интеграция",)


def test_reject_keyword_wins_over_accept_keyword():
    order = make_order("Срочно нужен парсер", "Очень срочно, заказ горит.")
    verdict = evaluate(order, CFG)
    assert verdict.accepted is False
    assert any(r.startswith("reject:") for r in verdict.reasons)


def test_rejects_too_short_brief():
    order = make_order("Скрипт", "Напиши")
    verdict = evaluate(order, CFG)
    assert verdict.accepted is False
    assert "too_short" in verdict.reasons


def test_rejects_too_long_brief():
    order = make_order("Нужен бот", "раз " * 200)
    verdict = evaluate(order, CFG)
    assert verdict.accepted is False
    assert "too_long" in verdict.reasons


def test_matching_is_case_insensitive():
    order = make_order("Нужен ПАРСЕР", "И скрипт для выгрузки данных в файл.")
    verdict = evaluate(order, CFG)
    assert verdict.accepted is True
    assert verdict.score == 2


def test_reject_keyword_respects_word_boundaries():
    """«1с» отклоняет «доработать 1С», но не ловит «t1сный» внутри слова."""
    cfg = FilterConfig(
        accept_keywords=("скрипт",),
        reject_keywords=("1с",),
        min_score=1,
        min_length=10,
        max_length=500,
    )
    # отдельное слово — отклоняем
    rejected = evaluate(make_order("Доработать 1С", "Нужен скрипт для выгрузки"), cfg)
    assert rejected.accepted is False
    assert rejected.reasons == ("reject:1с",)

    # внутри слова — не отклоняем
    accepted = evaluate(make_order("Скрипт для t1сного файла", "Сделать выгрузку данных"), cfg)
    assert accepted.accepted is True
