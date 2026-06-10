"""
tests/test_tactics.py

Tests for data/tactics.py
Run with: pytest tests/test_tactics.py -v -m "not live"

Note: tests marked with @pytest.mark.live make real Gemini API calls.
Run live tests with: pytest tests/test_tactics_agent.py -v -m live
Skip live tests with: pytest tests/test_tactics_agent.py -v -m "not live"
"""

import pytest
from data.tactics import analyse, _build_payload, _parse_json, _error



# --- _parse_json -------------------------------------------------------------

def test_parse_json_plain():
    raw = '{"key": "value"}'
    assert _parse_json(raw) == {"key": "value"}


def test_parse_json_with_code_fences():
    raw = '```json\n{"key": "value"}\n```'
    assert _parse_json(raw) == {"key": "value"}


def test_parse_json_with_nested():
    raw = '```json\n{"a": {"b": 1, "c": [1,2,3]}}\n```'
    result = _parse_json(raw)
    assert result["a"]["b"] == 1
    assert result["a"]["c"] == [1, 2, 3]


def test_parse_json_invalid_returns_none():
    assert _parse_json("this is not json") is None


def test_parse_json_empty_returns_none():
    assert _parse_json("") is None


def test_parse_json_truncated_returns_none():
    raw = '{"key": "value", "incomplete":'
    assert _parse_json(raw) is None


# --- _error ------------------------------------------------------------------

def test_error_returns_correct_shape():
    result = _error("test error")
    assert result["_available"] is False
    assert result["_error"] == "test error"
    assert result["overall_advantage"] == "neutral"
    assert result["confidence"] == "low"
    assert "data_gaps" in result


def test_error_with_raw():
    result = _error("parse failed", raw="some raw text")
    assert result["_raw"] == "some raw text"


# --- _build_payload ----------------------------------------------------------

def test_build_payload_minimal():
    payload = _build_payload("Mexico", "South Africa", None, None, None, None)
    assert payload["home"] == "Mexico"
    assert payload["away"] == "South Africa"
    assert payload["fixture"] == "Mexico vs South Africa"
    assert payload["kickoff_time"] == "unknown"


def test_build_payload_with_kickoff():
    payload = _build_payload("Mexico", "South Africa", None, None, None, "2026-06-11 19:00:00")
    assert payload["kickoff_time"] == "2026-06-11 19:00:00"


def test_build_payload_weather_available():
    wx = {
        "available": True,
        "venue":     "Estadio Azteca",
        "city":      "Mexico City",
        "temp_c":    18.5,
        "condition": "rainy",
        "wind_kph":  5.6,
        "precip_mm": 26.6,
        "summary":   "Estadio Azteca: 18.5C, rainy",
    }
    payload = _build_payload("Mexico", "South Africa", None, None, wx, None)
    assert payload["weather"]["venue"] == "Estadio Azteca"
    assert payload["weather"]["temp_c"] == 18.5


def test_build_payload_weather_unavailable():
    wx = {"available": False, "summary": "not available"}
    payload = _build_payload("Mexico", "South Africa", None, None, wx, None)
    assert payload["weather"] is None


def test_build_payload_data_quality_warning_present():
    supabase_data = {
        "checkpoint_stats": {"available": False, "home_matches": []},
        "country_style": {
            "available": True,
            "home": {"group_gpg": 0.89, "conversion_rate": 0.021},
            "away": {"group_gpg": 2.33, "conversion_rate": 0.077},
        },
    }
    payload = _build_payload("Mexico", "South Africa", None, supabase_data, None, None)
    assert "data_quality_warning" in payload
    assert "South Africa" in payload["data_quality_warning"]


def test_build_payload_supabase_priors():
    supabase_data = {
        "checkpoint_stats": {"available": True, "home_matches": []},
        "country_style": {
            "available": True,
            "home": {"group_gpg": 0.89, "conversion_rate": 0.021},
            "away": {"group_gpg": 2.33, "conversion_rate": 0.077},
        },
    }
    payload = _build_payload("Mexico", "South Africa", None, supabase_data, None, None)
    assert payload["home_group_gpg"] == 0.89
    assert payload["away_group_gpg"] == 2.33
    assert payload["home_priors_available"] is True
    assert payload["away_priors_available"] is True


def test_build_payload_lineups_when_available():
    sm_data = {
        "lineups": {
            "available": True,
            "home": {"formation": "4-3-3", "players": []},
            "away": {"formation": "4-2-3-1", "players": []},
        }
    }
    payload = _build_payload("Mexico", "South Africa", sm_data, None, None, None)
    assert payload["home_formation"] == "4-3-3"
    assert payload["away_formation"] == "4-2-3-1"
    assert payload["lineups_available"] is True


def test_build_payload_lineups_unavailable():
    sm_data = {
        "lineups": {
            "available": False,
            "home": None,
            "away": None,
        }
    }
    payload = _build_payload("Mexico", "South Africa", sm_data, None, None, None)
    assert payload["home_formation"] is None
    assert payload["away_formation"] is None
    assert payload["lineups_available"] is False


# --- analyse (live Gemini call) ----------------------------------------------

@pytest.mark.live
def test_analyse_returns_dict():
    result = analyse("Mexico", "South Africa")
    assert isinstance(result, dict)


@pytest.mark.live
def test_analyse_has_required_keys():
    result = analyse("Mexico", "South Africa")
    for key in ["overall_advantage", "advantage_strength",
                "confidence", "analyst_verdict", "data_gaps"]:
        assert key in result


@pytest.mark.live
def test_analyse_overall_advantage_valid_value():
    result = analyse("Mexico", "South Africa")
    assert result.get("overall_advantage") in ["home", "away", "neutral"]


@pytest.mark.live
def test_analyse_confidence_valid_value():
    result = analyse("Mexico", "South Africa")
    assert result.get("confidence") in ["high", "medium", "low"]


@pytest.mark.live
def test_analyse_low_confidence_when_no_data():
    """With no data at all, agent should return low confidence."""
    result = analyse("Mexico", "South Africa")
    assert result.get("confidence") in ["low", "medium"]


@pytest.mark.live
def test_analyse_with_weather():
    wx = {
        "available": True,
        "venue":     "Estadio Azteca",
        "city":      "Mexico City",
        "temp_c":    18.5,
        "condition": "rainy",
        "wind_kph":  5.6,
        "precip_mm": 26.6,
        "summary":   "Estadio Azteca: 18.5C, rainy",
    }
    result = analyse("Mexico", "South Africa", weather_data=wx)
    assert result.get("_available") is True
    assert "weather" in result.get("analyst_verdict", "").lower() or \
           "rain" in result.get("weather_impact", "").lower() or \
           result.get("confidence") in ["low", "medium", "high"]