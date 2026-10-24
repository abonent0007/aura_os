import pytest

from freelance_hunter.config import load_config

SAMPLE = """
sources:
  - name: fl.ru
    url: https://www.fl.ru/rss/all.xml
  - name: kwork
    url: https://kwork.ru/rss/projects
  - name: habr-career
    url: https://career.habr.com/vacancies/rss
    min_score: 2
accept_keywords: [парсер, бот]
reject_keywords: [интеграция]
min_score: 2
db_path: custom.db
"""


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_sources_and_keywords(tmp_path):
    cfg = load_config(write(tmp_path, SAMPLE))
    assert [s.name for s in cfg.sources] == ["fl.ru", "kwork", "habr-career"]
    assert cfg.sources[0].url == "https://www.fl.ru/rss/all.xml"
    assert cfg.accept_keywords == ("парсер", "бот")
    assert cfg.reject_keywords == ("интеграция",)
    assert cfg.min_score == 2
    assert cfg.db_path == "custom.db"


def test_per_source_min_score(tmp_path):
    """У источника может быть свой порог; без него — None (берётся общий)."""
    cfg = load_config(write(tmp_path, SAMPLE))
    assert cfg.sources[0].min_score is None
    assert cfg.sources[1].min_score is None
    assert cfg.sources[2].min_score == 2


def test_applies_defaults_for_missing_keys(tmp_path):
    cfg = load_config(write(tmp_path, SAMPLE))
    assert cfg.min_length == 30
    assert cfg.max_length == 1200
    assert cfg.fallback_price == 3000
    assert cfg.fallback_days == 3
    assert cfg.llm_timeout == 15
    assert cfg.telegram_timeout == 10
    assert cfg.fetch_timeout == 20
    assert cfg.max_workers == 6
    assert cfg.llm_model


def test_raises_without_sources(tmp_path):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, "accept_keywords: [парсер]\n"))
