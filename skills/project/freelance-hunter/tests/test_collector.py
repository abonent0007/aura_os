from freelance_hunter.collector import FeedCollector, parse_feed, strip_html

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Проекты</title>
    <item>
      <title>Нужен парсер Avito</title>
      <link>https://example.com/orders/1</link>
      <guid>https://example.com/orders/1</guid>
      <description>&lt;p&gt;Собрать &lt;b&gt;данные&lt;/b&gt; и выгрузить в Excel&lt;/p&gt;</description>
      <pubDate>Mon, 08 Sep 2026 10:00:00 +0300</pubDate>
    </item>
    <item>
      <title>Настроить бота</title>
      <link>https://example.com/orders/2</link>
      <guid>https://example.com/orders/2</guid>
      <description>Простой бот для уведомлений</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Проекты</title>
  <entry>
    <title>Написать скрипт</title>
    <id>tag:example.com,2026:3</id>
    <link href="https://example.com/orders/3"/>
    <summary>Скрипт для обработки таблиц</summary>
    <updated>2026-09-08T10:00:00Z</updated>
  </entry>
</feed>
"""


def test_strip_html_removes_tags_and_entities():
    assert strip_html("<p>Нужен <b>парсер</b> &amp; бот</p>") == "Нужен парсер & бот"


def test_strip_html_collapses_whitespace():
    assert strip_html("a\n\n   b") == "a b"


def test_parse_rss_returns_orders():
    orders = parse_feed(RSS, "fl.ru")
    assert len(orders) == 2
    first = orders[0]
    assert first.source == "fl.ru"
    assert first.title == "Нужен парсер Avito"
    assert first.external_id == "https://example.com/orders/1"
    assert first.url == "https://example.com/orders/1"
    assert first.description == "Собрать данные и выгрузить в Excel"
    assert first.published_at == "Mon, 08 Sep 2026 10:00:00 +0300"


def test_parse_atom_returns_orders():
    orders = parse_feed(ATOM, "kwork")
    assert len(orders) == 1
    assert orders[0].external_id == "tag:example.com,2026:3"
    assert orders[0].url == "https://example.com/orders/3"
    assert orders[0].description == "Скрипт для обработки таблиц"


def test_parse_feed_returns_empty_list_for_malformed_xml():
    assert parse_feed("<rss><channel>", "fl.ru") == []


def test_feed_collector_uses_fetcher():
    calls = []

    def fetcher(url):
        calls.append(url)
        return RSS

    collector = FeedCollector(name="fl.ru", url="https://feed.example/rss", fetcher=fetcher)
    orders = collector.collect()
    assert calls == ["https://feed.example/rss"]
    assert len(orders) == 2
