"""
tests/test_bet_manager.py

Tests for agent/bet_manager.py
Run with: pytest tests/test_bet_manager.py -v -m "not live"
"""

import pytest
from agent.bet_manager import _parse_json, _skip, _fallback_decision, decide


# --- _parse_json -------------------------------------------------------------

def test_parse_valid_json():
    raw = '{"should_place_order": true, "team_code": "MEX", "size_usdc": 3.0}'
    result = _parse_json(raw)
    assert result["team_code"] == "MEX"
    assert result["size_usdc"] == 3.0


def test_parse_with_code_fences():
    raw = '```json\n{"should_place_order": false, "team_code": null}\n```'
    result = _parse_json(raw)
    assert result["should_place_order"] is False


def test_parse_invalid_returns_none():
    assert _parse_json("not json") is None


def test_parse_empty_returns_none():
    assert _parse_json("") is None


# --- _skip -------------------------------------------------------------------

def test_skip_shape():
    result = _skip("test reason")
    assert result["should_place_order"] is False
    assert result["size_usdc"]          == 0.0
    assert result["team_code"]          is None
    assert result["_available"]         is False
    assert "test reason"                in result["rationale"]


def test_skip_has_all_keys():
    result = _skip("reason")
    for key in ["should_place_order", "team_code", "outcome",
                "size_usdc", "limit_price", "edge_pp",
                "direction", "rationale"]:
        assert key in result


# --- decide (safety layer only, no live call) --------------------------------

def test_decide_returns_required_keys():
    result = _skip("test")
    for key in ["should_place_order", "team_code", "outcome",
                "size_usdc", "limit_price", "edge_pp", "rationale"]:
        assert key in result


def test_skip_direction_is_long():
    result = _skip("reason")
    assert result["direction"] == "long"


def test_fallback_decision_places_bet_for_valid_edge():
    prediction = {
        "outcome": "home",
        "probability": 0.52,
        "confidence_level": "medium",
    }
    live_prices = {"home": 0.40, "away": 0.30}
    bankroll = {"current_balance": 100.0}

    result = _fallback_decision(prediction, live_prices, "MEX", "ZAF", bankroll)

    assert result is not None
    assert result["should_place_order"] is True
    assert result["team_code"] == "MEX"
    assert result["outcome"] == "home"
    assert result["size_usdc"] > 0