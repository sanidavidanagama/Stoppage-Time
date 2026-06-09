"""
tests/test_tool_executor.py

Tests for agent/tool_executor.py
Run with: pytest tests/test_tool_executor.py -v
"""

import pytest
from agent.tool_executor import execute, AVAILABLE_TOOLS
from agent.memory.stssm import new_session


# --- helpers -----------------------------------------------------------------

def _stm():
    stm = new_session("Mexico vs South Africa", "2026-06-11 19:00:00")
    stm.identity_map = {
        "fixture_id":   19609127,
        "fixture_name": "Mexico vs South Africa",
        "kickoff":      "2026-06-11 19:00:00",
        "home": {
            "name": "Mexico", "short_code": "MEX",
            "sm_team_id": 18576, "sm_country_id": 458,
            "sb_priors_id": 147, "sb_dim_id": 458,
            "pm_token_yes": None,
            "has_polymarket": True, "has_supabase": True, "has_sb_priors": True,
        },
        "away": {
            "name": "South Africa", "short_code": "ZAF",
            "sm_team_id": 18555, "sm_country_id": 146,
            "sb_priors_id": 211, "sb_dim_id": None,
            "pm_token_yes": None,
            "has_polymarket": True, "has_supabase": False, "has_sb_priors": True,
        },
        "draw": {"pm_token_yes": None},
        "pm_event_slug": "fifwc-mex-rsa-2026-06-11",
    }
    return stm


# --- AVAILABLE_TOOLS ---------------------------------------------------------

def test_available_tools_has_9_tools():
    assert len(AVAILABLE_TOOLS) == 9


def test_available_tools_has_expected_keys():
    expected = [
        "sportmonks.get_fixture",
        "sportmonks.get_team_form",
        "polymarket.get_market",
        "supabase.get_checkpoint",
        "supabase.get_priors",
        "supabase.get_h2h",
        "news.get_articles",
        "weather.get_match_weather",
        "tactics.analyse",
    ]
    for tool in expected:
        assert tool in AVAILABLE_TOOLS


# --- execute -----------------------------------------------------------------

def test_execute_unknown_tool_returns_error():
    stm    = _stm()
    result = execute("unknown.tool", {}, stm, round_num=1)
    assert result.error is not None
    assert "does not exist" in result.result_summary

def test_execute_returns_tool_call():
    from agent.memory.stssm import ToolCall
    stm    = _stm()
    result = execute("unknown.tool", {}, stm, round_num=1)
    assert isinstance(result, ToolCall)


def test_execute_sets_round():
    stm    = _stm()
    result = execute("unknown.tool", {}, stm, round_num=3)
    assert result.round == 3


def test_execute_sets_tool_name():
    stm    = _stm()
    result = execute("unknown.tool", {}, stm, round_num=1)
    assert result.tool == "unknown.tool"


def test_execute_result_summary_is_string():
    stm    = _stm()
    result = execute("unknown.tool", {}, stm, round_num=1)
    assert isinstance(result.result_summary, str)


def test_execute_h2h_no_data():
    """H2H for MEX vs ZAF returns no data gracefully."""
    stm    = _stm()
    result = execute(
        "supabase.get_h2h",
        {"home": "Mexico", "away": "South Africa"},
        stm, round_num=1,
    )
    assert result.error is None
    assert isinstance(result.result_summary, str)
    assert len(result.result_summary) > 0