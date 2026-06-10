"""
tests/test_reasoning.py

Tests for agent/reasoning.py
Run with: pytest tests/test_reasoning.py -v -m "not live"
"""

import pytest
from agent.reasoning import (
    _parse_response,
    _format_sportmonks,
    _format_polymarket,
    _format_supabase,
    _format_news,
    get_assembled_prompt,
)
from agent.memory.stssm import new_session


# --- helpers -----------------------------------------------------------------

def _full_stm():
    stm = new_session("Mexico vs South Africa", "2026-06-11 19:00:00")
    stm.identity_map = {
        "fixture_id":   19609127,
        "fixture_name": "Mexico vs South Africa",
        "kickoff":      "2026-06-11 19:00:00",
        "stage":        "Group Stage",
        "round":        "1",
        "home": {
            "name":          "Mexico",
            "short_code":    "MEX",
            "sm_team_id":    18576,
            "sm_country_id": 458,
            "sb_priors_id":  147,
            "sb_dim_id":     458,
            "has_polymarket": True,
            "has_supabase":   True,
            "has_sb_priors":  True,
        },
        "away": {
            "name":          "South Africa",
            "short_code":    "ZAF",
            "sm_team_id":    18555,
            "sm_country_id": 146,
            "sb_priors_id":  211,
            "sb_dim_id":     None,
            "has_polymarket": True,
            "has_supabase":   False,
            "has_sb_priors":  True,
        },
        "pm_event_slug": "fifwc-mex-rsa-2026-06-11",
    }
    stm.sportmonks = {
        "predictions": {
            "available": True,
            "one_x_two": [
                {"type_id": 233, "home": 28.4, "draw": 46.1, "away": 25.5},
                {"type_id": 237, "home": 40.8, "draw": 27.8, "away": 31.4},
                {"type_id": 238, "home": 50.4, "draw": 9.5,  "away": 40.1},
            ],
            "consensus": {"home": 39.9, "draw": 27.8, "away": 32.3},
        },
        "odds": {
            "available":       True,
            "bookmaker_count": 16,
            "stale_count":     1,
            "consensus":       {"home": 0.70, "draw": 0.23, "away": 0.13},
        },
        "xg":      {"available": False},
        "lineups": {"available": False, "home": None, "away": None},
    }
    stm.polymarket = {
        "live_prices": {
            "available": True,
            "home": 0.685, "draw": 0.205, "away": 0.105, "sum": 0.995,
        },
        "meta": {
            "available":    True,
            "liquidity":    654627,
            "volume":       320255,
            "volume_24hr":  89257,
            "competitive":  0.967,
        },
        "price_history": {
            "available": True,
            "home": {"last_price": 0.69, "change_24hr": -0.01,
                     "change_1wk": 0.02, "spread": 0.01},
            "draw": {"last_price": 0.20, "change_24hr": -0.005,
                     "change_1wk": -0.01, "spread": 0.01},
            "away": {"last_price": 0.10, "change_24hr": 0.005,
                     "change_1wk": -0.02, "spread": 0.01},
        },
    }
    stm.supabase = {
        "checkpoint_stats": {
            "available": True,
            "home_matches": [
                {
                    "opponent": "vs Poland",
                    "is_home": True,
                    "cum_goals": 0,
                    "cum_shots_total": 11,
                    "cum_shots_on_target": 4,
                    "cum_possession_pct": 61.0,
                    "cum_pass_accuracy_pct": 0.836,
                    "cum_yellow_cards": 2,
                },
            ],
        },
        "stage_record": {
            "available": True,
            "home": {"group": {"matches": 9, "wins": 4,
                               "draws": 2, "losses": 3, "win_rate": 0.444}},
            "away": {"group": {"matches": 6, "wins": 1,
                               "draws": 1, "losses": 4, "win_rate": 0.167}},
        },
        "country_style":    {"available": True, "home": {}, "away": {}},
        "ko_pattern":       {"available": False},
        "h2h":              {"available": False},
    }
    stm.news = [
        {
            "title":     "Mexico injury update",
            "summary":   "Lozano doubtful for opener",
            "source":    "ESPN FC",
            "published": "2026-06-09T10:00:00+00:00",
            "teams":     ["Mexico"],
        }
    ]
    return stm


# --- _parse_response ---------------------------------------------------------

def test_parse_final_decision():
    raw = '''```json
{
  "type": "final_decision",
  "outcome": "home",
  "probability": 0.72,
  "should_bet": true,
  "bet_direction": "long",
  "size_usdc": 3.0,
  "edge_pp": 3.5,
  "confidence_level": "high",
  "signals_used": ["polymarket", "bookmakers"],
  "signals_ignored": [],
  "rationale": "Mexico is strong favourite.",
  "data_gaps": []
}
````'''
    result = _parse_response(raw)
    assert result is not None
    assert result["type"] == "final_decision"
    assert result["outcome"] == "home"
    assert result["should_bet"] is True


def test_parse_tool_request():
    raw = '''```json
{
  "type": "tool_request",
  "tool": "supabase.get_h2h",
  "params": {"home": "Mexico", "away": "South Africa"},
  "reason": "Need head to head record"
}
```'''
    result = _parse_response(raw)
    assert result is not None
    assert result["type"] == "tool_request"
    assert result["tool"] == "supabase.get_h2h"


def test_parse_invalid_returns_none():
    assert _parse_response("not json at all") is None


def test_parse_empty_returns_none():
    assert _parse_response("") is None


def test_parse_truncated_returns_none():
    assert _parse_response('{"type": "final_decision", "outcome":') is None


# --- formatters --------------------------------------------------------------

def test_format_sportmonks_available():
    stm    = _full_stm()
    result = _format_sportmonks(stm)
    assert "ML model consensus" in result
    assert "Bookmaker consensus" in result
    assert "16 bookmakers" in result


def test_format_sportmonks_empty():
    stm = new_session()
    stm.sportmonks = {}
    assert "No Sportmonks data" in _format_sportmonks(stm)


def test_format_polymarket_available():
    stm    = _full_stm()
    result = _format_polymarket(stm)
    assert "0.685" in result
    assert "654,627" in result


def test_format_polymarket_empty():
    stm = new_session()
    stm.polymarket = {}
    assert "No Polymarket data" in _format_polymarket(stm)


def test_format_supabase_available():
    stm    = _full_stm()
    result = _format_supabase(stm)
    assert "vs Poland" in result
    assert "Mexico" in result


def test_format_supabase_empty():
    stm = new_session()
    stm.supabase   = {}
    stm.identity_map = {}
    assert "No Supabase data" in _format_supabase(stm)


def test_format_news_available():
    stm    = _full_stm()
    result = _format_news(stm)
    assert "Mexico injury update" in result
    assert "ESPN FC" in result


def test_format_news_empty():
    stm      = new_session()
    stm.news = []
    assert "No recent news" in _format_news(stm)


# --- get_assembled_prompt ----------------------------------------------------

def test_assembled_prompt_has_fixture_name():
    stm    = _full_stm()
    prompt = get_assembled_prompt(stm)
    assert "Mexico" in prompt
    assert "South Africa" in prompt


def test_assembled_prompt_has_tools_section():
    stm    = _full_stm()
    prompt = get_assembled_prompt(stm)
    assert "Available tools" in prompt


def test_assembled_prompt_has_ltm_section():
    stm    = _full_stm()
    prompt = get_assembled_prompt(stm)
    assert "Long Term Memory" in prompt


def test_assembled_prompt_has_data_availability():
    stm    = _full_stm()
    prompt = get_assembled_prompt(stm)
    assert "Data availability" in prompt


def test_assembled_prompt_no_unfilled_placeholders():
    stm    = _full_stm()
    prompt = get_assembled_prompt(stm)
    import re
    unfilled = re.findall(r"\{[a-z_]+\}", prompt)
    assert unfilled == [], f"Unfilled placeholders: {unfilled}"

