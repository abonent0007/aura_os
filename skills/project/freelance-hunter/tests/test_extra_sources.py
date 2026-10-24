"""Тесты extra_sources.py — расширенный поиск (HTML-источники, фильтры)."""
import extra_sources as es


def make_cfg(**over):
    cfg = {
        "accept_keywords": ["парсер", "python", "бот"],
        "reject_keywords": ["дизайн", "1с"],
        "min_score": 2,
        "min_length": 10,
        "max_length": 500,
    }
    cfg.update(over)
    return cfg


def order(title, description=""):
    return {"source": "test", "external_id": "1", "title": title,
            "description": description, "url": ""}


# ── HTML-разбор ──

def test_parse_html_extracts_orders():
    html = (
        '<a href="/projects/123">Сделать парсер Avito</a>'
        '<a href="/projects/124">Написать telegram-бота</a>'
    )
    pattern = r'<a[^>]+href="(?P<url>/projects/\d+[^"]*)"[^>]*>(?P<title>[^<]{5,300})</a>'
    orders = es.parse_html(html, "kwork", pattern, "https://kwork.ru")
    assert len(orders) == 2
    assert orders[0]["url"] == "https://kwork.ru/projects/123"
    assert orders[0]["external_id"] == "https://kwork.ru/projects/123"
    assert orders[0]["source"] == "kwork"


def test_parse_html_deduplicates_and_ignores_empty():
    html = '<a href="/p/1">Нужен парсер</a><a href="/p/1">Нужен парсер</a>'
    pattern = r'<a[^>]+href="(?P<url>/p/\d+)"[^>]*>(?P<title>[^<]{5,300})</a>'
    orders = es.parse_html(html, "site", pattern, "")
    assert len(orders) == 1


# ── Фильтры ──

def test_evaluate_accepts_two_matches():
    accepted, score = es.evaluate(order("Нужен парсер на python", "собрать данные"), make_cfg())
    assert accepted is True
    assert score >= 2


def test_evaluate_rejects_below_threshold():
    accepted, score = es.evaluate(order("Нужен парсер", "собрать данные"), make_cfg())
    assert accepted is False  # только одно совпадение при пороге 2
    assert score == 1


def test_evaluate_reject_prefix_catches_word_forms():
    """«дизайн» ловит «дизайнера» — префиксный матчинг словоформ."""
    accepted, _ = es.evaluate(order("Ищу дизайнера интерьера", "нужно нарисовать"), make_cfg())
    assert accepted is False


def test_evaluate_does_not_match_inside_word():
    """«1с» не ловится внутри «t1сный»."""
    accepted, _ = es.evaluate(
        order("Скрипт python для t1сного файла", "написать бота для выгрузки"), make_cfg()
    )
    assert accepted is True


def test_evaluate_min_score_override():
    cfg = make_cfg(min_score=1)
    # с общим порогом 1 заказ проходит
    assert es.evaluate(order("Нужен парсер", "собрать данные"), cfg)[0] is True
    # с override 2 — нет
    assert es.evaluate(order("Нужен парсер", "собрать данные"), cfg, min_score=2)[0] is False
