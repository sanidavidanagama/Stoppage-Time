"""
tests/test_polymarket.py

Tests for data/polymarket.py
Run with: pytest tests/test_polymarket.py -v
"""

import pytest
from data.identity import resolve_identity
from data.polymarket import (
    get_market_meta,
    get_live_prices,
    get_price_history,
    get_all,
)


# --- Fixture -----------------------------------------------------------------

@pytest.fixture(scope="module")
def identity_map():
    return resolve_identity("Mexico", "South Africa")


@pytest.fixture(scope="module")
def no_market_identity():
    """Minimal identity map with no Polymarket market."""
    return {
        "pm_event_slug": None,
        "home": {"short_code": "MEX", "pm_token_yes": None},
        "draw": {"pm_token_yes": None},
        "away": {"short_code": "ZAF", "pm_token_yes": None},
    }


# --- get_market_meta ---------------------------------------------------------

def test_meta_returns_required_keys(identity_map):
    result = get_market_meta(identity_map)
    for key in ["title", "liquidity", "volume", "volume_24hr",
                "competitive", "neg_risk", "active", "closed", "available"]:
        assert key in result


def test_meta_available(identity_map):
    result = get_market_meta(identity_map)
    assert result["available"] is True
    assert result["active"] is True
    assert result["closed"] is False


def test_meta_has_liquidity(identity_map):
    result = get_market_meta(identity_map)
    assert result["liquidity"] > 0


def test_meta_unavailable_when_no_slug(no_market_identity):
    result = get_market_meta(no_market_identity)
    assert result["available"] is False


# --- get_live_prices ---------------------------------------------------------

def test_prices_returns_required_keys(identity_map):
    result = get_live_prices(identity_map)
    for key in ["home", "draw", "away", "sum", "available"]:
        assert key in result


def test_prices_all_available(identity_map):
    result = get_live_prices(identity_map)
    if not result["available"]:
        pytest.skip("Polymarket prices temporarily unavailable — live API flakiness")
    assert result["available"] is True
    assert result["home"] is not None
    assert result["draw"] is not None
    assert result["away"] is not None


def test_prices_sum_near_one(identity_map):
    result = get_live_prices(identity_map)
    assert result["sum"] is not None
    assert 0.95 <= result["sum"] <= 1.05


def test_prices_mexico_favourite(identity_map):
    result = get_live_prices(identity_map)
    assert result["home"] > result["away"]


def test_prices_in_range(identity_map):
    result = get_live_prices(identity_map)
    for key in ["home", "draw", "away"]:
        assert 0 < result[key] < 1


def test_prices_unavailable_when_no_slug(no_market_identity):
    result = get_live_prices(no_market_identity)
    assert result["available"] is False


# --- get_price_history -------------------------------------------------------

def test_history_returns_required_keys(identity_map):
    result = get_price_history(identity_map)
    for key in ["home", "draw", "away", "available"]:
        assert key in result


def test_history_available(identity_map):
    result = get_price_history(identity_map)
    assert result["available"] is True


def test_history_has_change_fields(identity_map):
    result = get_price_history(identity_map)
    for outcome in ["home", "draw", "away"]:
        if result[outcome]:
            assert "change_24hr" in result[outcome]
            assert "change_1wk" in result[outcome]
            assert "last_price" in result[outcome]
            assert "spread" in result[outcome]


# --- get_all -----------------------------------------------------------------

def test_get_all_returns_all_sections(identity_map):
    result = get_all(identity_map)
    assert "meta" in result
    assert "live_prices" in result
    assert "price_history" in result


def test_get_all_meta_available(identity_map):
    result = get_all(identity_map)
    assert result["meta"]["available"] is True


def test_get_all_prices_available(identity_map):
    result = get_all(identity_map)
    assert result["live_prices"]["available"] is True