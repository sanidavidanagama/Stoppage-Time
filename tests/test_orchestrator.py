"""
tests/test_orchestrator.py

Tests for agent/orchestrator.py
Run with: pytest tests/test_orchestrator.py -v -m "not live"
"""

import pytest
from agent.orchestrator import _compute_gap, _place_order


# --- _compute_gap ------------------------------------------------------------

def test_compute_gap_positive():
    prediction = {"outcome": "home", "probability": 0.72}
    prices     = {"home": 0.685, "draw": 0.205, "away": 0.105}
    gap = _compute_gap(prediction, prices)
    assert gap == pytest.approx(3.5, abs=0.1)


def test_compute_gap_negative():
    prediction = {"outcome": "home", "probability": 0.40}
    prices     = {"home": 0.685, "draw": 0.205, "away": 0.105}
    gap = _compute_gap(prediction, prices)
    assert gap == pytest.approx(-28.5, abs=0.1)


def test_compute_gap_no_market_price():
    prediction = {"outcome": "home", "probability": 0.72}
    prices     = {"home": None, "draw": 0.205, "away": 0.105}
    assert _compute_gap(prediction, prices) is None


def test_compute_gap_no_outcome():
    prediction = {"outcome": None, "probability": 0.72}
    prices     = {"home": 0.685}
    assert _compute_gap(prediction, prices) is None


# --- _place_order ------------------------------------------------------------

@pytest.mark.live
def test_place_order_returns_dict():
    result = _place_order(
        fixture_id  = 19609127,
        team_code   = "MEX",
        size_usdc   = 1.0,
        limit_price = 0.70,
    )
    assert isinstance(result, dict)


@pytest.mark.live
def test_place_order_404_is_handled():
    result = _place_order(
        fixture_id  = 19609127,
        team_code   = "MEX",
        size_usdc   = 1.0,
        limit_price = 0.70,
    )
    assert "status" in result

# --- run (live) --------------------------------------------------------------

@pytest.mark.live
def test_run_returns_session_id():
    from agent.orchestrator import run
    result = run("Mexico", "South Africa")
    assert "session_id" in result


@pytest.mark.live
def test_run_returns_fixture_name():
    from agent.orchestrator import run
    result = run("Mexico", "South Africa")
    assert result.get("fixture") == "Mexico vs South Africa"


@pytest.mark.live
def test_run_has_decision():
    from agent.orchestrator import run
    result = run("Mexico", "South Africa")
    assert "should_bet" in result
    assert "confidence"  in result