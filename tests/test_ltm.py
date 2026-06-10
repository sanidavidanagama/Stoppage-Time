"""
tests/test_ltm.py

Tests for agent/memory/ltm.py
Run with: pytest tests/test_ltm.py -v
"""

import pytest
import os
from pathlib import Path
import agent.memory.ltm as ltm_module
from agent.memory.ltm import (
    save_bet,
    update_outcome,
    get_recent_bets,
    get_similar_bets,
    get_agent_stats,
    get_ltm_context,
    get_bankroll_summary,
)


# --- Setup/teardown ----------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_db(monkeypatch, tmp_path):
    """Fresh temp database for each test — no Windows file lock issues."""
    test_db = tmp_path / "test_bets.db"
    monkeypatch.setattr(ltm_module, "DB_PATH", test_db)
    yield

# --- helpers -----------------------------------------------------------------

def _make_bet(**kwargs) -> str:
    defaults = dict(
        session_id="s1",
        fixture_name="Mexico vs South Africa",
        home_team="Mexico",
        away_team="South Africa",
        predicted_outcome="home",
        agent_probability=0.68,
        confidence_level="high",
        should_bet=True,
        bet_outcome="home",
        bet_direction="long",
        bet_size_usdc=3.0,
        edge_pp=15.0,
        signals_used=["sportmonks", "polymarket"],
        rationale="Mexico strong favourite",
        ml_market_gap=30.0,
    )
    defaults.update(kwargs)
    return save_bet(**defaults)


# --- save_bet ----------------------------------------------------------------

def test_save_bet_returns_id():
    bet_id = _make_bet()
    assert isinstance(bet_id, str)
    assert len(bet_id) == 36


def test_save_bet_skip():
    bet_id = _make_bet(
        fixture_name="Brazil vs Germany",
        should_bet=False,
        bet_outcome=None,
        bet_direction=None,
        bet_size_usdc=None,
        edge_pp=3.0,
        rationale="Edge too small",
    )
    assert isinstance(bet_id, str)


# --- update_outcome ----------------------------------------------------------

def test_update_outcome_won():
    bet_id = _make_bet(predicted_outcome="home")
    update_outcome(bet_id, "home", pnl=1.5)
    bets = get_recent_bets(limit=1)
    assert bets[0]["won"] == 1
    assert bets[0]["pnl"] == 1.5
    assert bets[0]["actual_outcome"] == "home"


def test_update_outcome_lost():
    bet_id = _make_bet(predicted_outcome="home")
    update_outcome(bet_id, "away", pnl=-2.0)
    bets = get_recent_bets(limit=1)
    assert bets[0]["won"] == 0
    assert bets[0]["pnl"] == -2.0


def test_update_outcome_invalid_id():
    """Should not raise even with unknown id."""
    update_outcome("nonexistent-id", "home", pnl=0.0)


# --- get_recent_bets ---------------------------------------------------------

def test_get_recent_bets_empty():
    assert get_recent_bets() == []


def test_get_recent_bets_returns_correct_count():
    for i in range(3):
        _make_bet(session_id=f"s{i}", fixture_name=f"Match {i}")
    bets = get_recent_bets(limit=2)
    assert len(bets) == 2


def test_get_recent_bets_newest_first():
    _make_bet(session_id="s1", fixture_name="Match 1")
    _make_bet(session_id="s2", fixture_name="Match 2")
    bets = get_recent_bets(limit=2)
    assert bets[0]["fixture_name"] == "Match 2"


# --- get_similar_bets --------------------------------------------------------

def test_get_similar_bets_finds_match():
    bet_id = _make_bet(ml_market_gap=30.0)
    update_outcome(bet_id, "home", pnl=1.5)
    similar = get_similar_bets(ml_market_gap=28.0, gap_tolerance=5.0)
    assert len(similar) >= 1


def test_get_similar_bets_empty_when_no_match():
    similar = get_similar_bets(ml_market_gap=99.0, gap_tolerance=1.0)
    assert similar == []


def test_get_similar_bets_only_resolved():
    """Pending bets (won=NULL) should not appear in similar bets."""
    _make_bet(ml_market_gap=30.0)   # no update_outcome call
    similar = get_similar_bets(ml_market_gap=30.0, gap_tolerance=1.0)
    assert similar == []


# --- get_bankroll_summary ----------------------------------------------------

def test_bankroll_empty():
    summary = get_bankroll_summary()
    assert summary["starting_balance"] == 100.0
    assert summary["current_balance"] == 100.0
    assert summary["total_pnl"] == 0.0
    assert summary["total_wagered"] == 0.0
    assert summary["wins"] == 0
    assert summary["losses"] == 0


def test_bankroll_after_win():
    bet_id = _make_bet(bet_size_usdc=3.0)
    update_outcome(bet_id, "home", pnl=2.10)
    summary = get_bankroll_summary()
    assert summary["current_balance"] == 102.10
    assert summary["total_pnl"] == 2.10
    assert summary["wins"] == 1
    assert summary["losses"] == 0


def test_bankroll_after_loss():
    bet_id = _make_bet(bet_size_usdc=2.0)
    update_outcome(bet_id, "away", pnl=-2.0)
    summary = get_bankroll_summary()
    assert summary["current_balance"] == 98.0
    assert summary["total_pnl"] == -2.0
    assert summary["wins"] == 0
    assert summary["losses"] == 1


def test_bankroll_drawdown():
    bet_id = _make_bet(bet_size_usdc=5.0)
    update_outcome(bet_id, "away", pnl=-5.0)
    summary = get_bankroll_summary()
    assert summary["drawdown_pct"] == 5.0


# --- get_agent_stats ---------------------------------------------------------

def test_get_agent_stats_none_when_empty():
    assert get_agent_stats() is None


def test_get_agent_stats_after_bets():
    bet_id = _make_bet()
    update_outcome(bet_id, "home", pnl=2.0)
    stats = get_agent_stats()
    assert stats is not None
    assert stats["total_bets"] == 1
    assert stats["winning_bets"] == 1
    assert stats["win_rate"] == 1.0


# --- get_ltm_context ---------------------------------------------------------

def test_get_ltm_context_returns_string():
    context = get_ltm_context()
    assert isinstance(context, str)
    assert "Long Term Memory" in context


def test_get_ltm_context_has_bankroll():
    context = get_ltm_context()
    assert "Bankroll" in context
    assert "$100.00" in context


def test_get_ltm_context_with_bets():
    bet_id = _make_bet(fixture_name="Mexico vs South Africa")
    update_outcome(bet_id, "home", pnl=2.10)
    context = get_ltm_context(ml_market_gap=30.0)
    assert "Mexico vs South Africa" in context
    assert "WON" in context


def test_get_ltm_context_similar_bets():
    bet_id = _make_bet(ml_market_gap=30.0)
    update_outcome(bet_id, "home", pnl=2.10)
    context = get_ltm_context(ml_market_gap=28.0)
    assert "similar ML/market gap" in context