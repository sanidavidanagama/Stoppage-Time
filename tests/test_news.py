"""
tests/test_news.py

Tests for data/news pipeline.
Run with: pytest tests/test_news.py -v
"""

import pytest
from data.news.fetcher  import fetch_news, _article_id, _is_relevant, _is_recent
from data.news.embedder import embed_articles, embed_query
from data.news.store    import store_articles, clear_collection, count
from data.news.query    import retrieve, get_news_context
from datetime import datetime, timezone


# --- fetcher -----------------------------------------------------------------

def test_article_id_is_stable():
    assert _article_id("Hello World") == _article_id("hello world")
    assert _article_id("Hello World") == _article_id("Hello World")


def test_is_relevant_true():
    assert _is_relevant("Mexico injury news", "", ["Mexico", "South Africa"])


def test_is_relevant_false():
    assert not _is_relevant("Arsenal sign striker", "", ["Mexico", "South Africa"])


def test_is_relevant_case_insensitive():
    assert _is_relevant("MEXICO squad update", "", ["Mexico", "South Africa"])


def test_is_recent_true():
    now = datetime.now(timezone.utc)
    assert _is_recent(now)


def test_is_recent_false():
    from datetime import timedelta
    old = datetime.now(timezone.utc) - timedelta(days=10)
    assert not _is_recent(old)


def test_fetch_news_returns_list():
    articles = fetch_news("Mexico", "South Africa")
    assert isinstance(articles, list)


def test_fetch_news_articles_have_required_keys():
    articles = fetch_news("Mexico", "South Africa")
    for a in articles:
        assert "id" in a
        assert "title" in a
        assert "summary" in a
        assert "source" in a
        assert "teams" in a


def test_fetch_news_all_relevant():
    """
    Articles should mention at least one team OR be about the World Cup.
    Some valid articles cover the tournament broadly without naming specific teams.
    """
    articles = fetch_news("Mexico", "South Africa")
    for a in articles:
        text = (a["title"] + " " + a["summary"]).lower()
        is_team_mention = "mexico" in text or "south africa" in text
        is_wc_mention   = "world cup" in text or "fifa" in text or "wc" in text
        assert is_team_mention or is_wc_mention
# --- embedder ----------------------------------------------------------------

def test_embed_query_returns_vector():
    vector = embed_query("Mexico injury news")
    assert isinstance(vector, list)
    assert len(vector) == 384


def test_embed_articles_adds_embedding():
    articles = [{"title": "Test", "summary": "Test summary",
                 "id": "abc", "source": "BBC", "url": "",
                 "published": None, "teams": []}]
    result = embed_articles(articles)
    assert "embedding" in result[0]
    assert len(result[0]["embedding"]) == 384


def test_embed_empty_returns_empty():
    assert embed_articles([]) == []


# --- store + query -----------------------------------------------------------

def test_store_and_retrieve():
    clear_collection()

    articles = [{
        "id":        "test123",
        "title":     "Mexico injury update before World Cup",
        "summary":   "Mexico's key striker ruled out of the match.",
        "source":    "BBC Sport",
        "url":       "http://example.com",
        "published": "2026-06-09T10:00:00+00:00",
        "teams":     ["Mexico"],
    }]
    embedded  = embed_articles(articles)
    stored    = store_articles(embedded)
    assert stored == 1
    assert count() == 1

    results = retrieve("Mexico", "South Africa", top_k=1)
    assert len(results) == 1
    assert "Mexico" in results[0]["title"]


def test_get_news_context_returns_string():
    context = get_news_context("Mexico", "South Africa")
    assert isinstance(context, str)
    assert len(context) > 0


def test_clear_collection():
    clear_collection()
    assert count() == 0