"""
tests/test_stm.py

Tests for agent/memory/stm.py
Run with: pytest tests/test_stm.py -v
"""

import pytest
from agent.memory.stssm import STSSM, ToolCall, new_session


# --- new_session -------------------------------------------------------------

def test_new_session_creates_stm():
    stm = new_session("Mexico vs South Africa", "2026-06-11 19:00:00")
    assert isinstance(stm, STSSM)
    assert stm.fixture_name == "Mexico vs South Africa"
    assert stm.kickoff == "2026-06-11 19:00:00"
    assert stm.status == "created"


def test_new_session_has_unique_id():
    stm1 = new_session()
    stm2 = new_session()
    assert stm1.session_id != stm2.session_id


def test_new_session_empty_data():
    stm = new_session()
    assert stm.sportmonks == {}
    assert stm.polymarket == {}
    assert stm.supabase == {}
    assert stm.news == []
    assert stm.tool_history == []
    assert stm.prediction is None
    assert stm.strategy is None


# --- tool calls --------------------------------------------------------------

def test_add_tool_call():
    stm = new_session()
    tc  = ToolCall(
        round=1,
        tool="sportmonks.get_fixture",
        params={"home": "Spain", "away": "Germany"},
        reason="Want to check Spain's xG",
        result_summary="Spain xG: 1.8, Germany xG: 1.2",
    )
    stm.add_tool_call(tc)
    assert len(stm.tool_history) == 1
    assert stm.tool_history[0].tool == "sportmonks.get_fixture"


def test_tool_history_summary_empty():
    stm = new_session()
    summary = stm.tool_history_summary()
    assert "No tool calls" in summary


def test_tool_history_summary_with_calls():
    stm = new_session()
    stm.add_tool_call(ToolCall(
        round=1,
        tool="supabase.get_priors",
        params={"team": "Brazil"},
        reason="Need Brazil priors",
        result_summary="Group win rate: 72%",
    ))
    summary = stm.tool_history_summary()
    assert "supabase.get_priors" in summary
    assert "Brazil priors" in summary
    assert "Group win rate" in summary


# --- gemini messages ---------------------------------------------------------

def test_add_gemini_message():
    stm = new_session()
    stm.add_gemini_message("user", "Analyse this match.")
    stm.add_gemini_message("assistant", "I need more data.")
    assert len(stm.gemini_messages) == 2
    assert stm.gemini_messages[0]["role"] == "user"
    assert stm.gemini_messages[1]["role"] == "assistant"


# --- data availability summary -----------------------------------------------

def test_data_availability_summary():
    stm = new_session("Mexico vs South Africa")
    stm.sportmonks = {
        "predictions": {"available": True},
        "odds":        {"available": True},
        "xg":          {"available": False},
        "lineups":     {"available": False},
    }
    stm.polymarket = {
        "live_prices": {"available": True},
    }
    stm.supabase = {
        "checkpoint_stats": {"available": True},
        "country_style":    {"available": True},
    }
    stm.identity_map = {
        "home": {"has_supabase": True},
        "away": {"has_supabase": False},
    }
    stm.news = [{"title": "test"}]

    summary = stm.data_availability_summary()
    assert "Mexico vs South Africa" in summary
    assert "yes" in summary
    assert "1 articles" in summary


# --- to_dict -----------------------------------------------------------------

def test_to_dict_has_required_keys():
    stm = new_session("Mexico vs South Africa")
    d   = stm.to_dict()
    for key in ["session_id", "created_at", "fixture_name",
                "status", "tool_history", "prediction", "strategy"]:
        assert key in d


def test_to_dict_tool_history_serializable():
    stm = new_session()
    stm.add_tool_call(ToolCall(
        round=1, tool="test", params={},
        reason="test", result_summary="ok"
    ))
    d = stm.to_dict()
    assert isinstance(d["tool_history"], list)
    assert isinstance(d["tool_history"][0], dict)


# --- status transitions ------------------------------------------------------

def test_status_transitions():
    stm = new_session()
    assert stm.status == "created"
    stm.status = "fetching"
    assert stm.status == "fetching"
    stm.status = "reasoning"
    assert stm.status == "reasoning"
    stm.status = "done"
    assert stm.status == "done"