from stockapp import collector, db

GOOGLE_RSS = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>台積電營收創新高 法人看好 - 經濟日報</title>
    <link>https://news.example/a</link>
    <pubDate>Mon, 26 Oct 2026 02:00:00 GMT</pubDate>
    <description>&lt;a href="x"&gt;台積電營收創新高 法人看好&lt;/a&gt;</description>
    <source url="https://money.udn.com">經濟日報</source>
  </item>
  <item>
    <title>Tesla stock falls on weak deliveries</title>
    <link>https://news.example/b</link>
    <pubDate>Sun, 25 Oct 2026 10:00:00 +0000</pubDate>
  </item>
  <item><title></title><link>https://news.example/c</link></item>
</channel></rss>"""


def test_parse_rss_strips_publisher_and_scores():
    items = collector.parse_rss(GOOGLE_RSS, "Google 新聞")
    assert len(items) == 2
    first, second = items
    assert first["title"] == "台積電營收創新高 法人看好"
    assert first["publisher"] == "經濟日報"
    assert first["summary"] == ""
    assert first["published"] == "2026-10-26 02:00:00"
    assert first["sentiment"] > 0
    assert second["sentiment"] < 0


def test_parse_rss_invalid_xml():
    assert collector.parse_rss("not xml", "x") == []


def test_news_sources_tw_vs_us():
    tw = collector.news_sources("2330.TW", "台積電")
    assert "hl=zh-TW" in tw[0][1]
    us = collector.news_sources("AAPL")
    assert "hl=en-US" in us[0][1]


def test_collect_all_is_idempotent():
    db.init_db()
    first = collector.collect_all(["2330.TW"])
    assert first["prices_added"] > 0 and first["news_added"] > 0
    second = collector.collect_all(["2330.TW"])
    assert second["prices_added"] == 0
    assert second["news_added"] == 0
    assert db.last_run()["symbols"] == 1
