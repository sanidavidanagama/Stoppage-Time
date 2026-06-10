"""
tests/test_weather.py

Tests for data/weather.py
Run with: pytest tests/test_weather.py -v
"""

import pytest
from data.weather import get_match_weather, VENUE_COORDS, _condition


# --- get_match_weather -------------------------------------------------------

def test_known_venue_returns_data():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    assert result["available"] is True
    assert result["venue"] == "Estadio Azteca"
    assert result["city"] == "Mexico City"


def test_known_venue_has_all_fields():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    for key in ["venue", "city", "date", "temp_c", "temp_f",
                "condition", "wind_kph", "precip_mm", "summary"]:
        assert key in result


def test_known_venue_temp_in_range():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    assert -10 <= result["temp_c"] <= 50


def test_known_venue_temp_f_conversion():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    expected_f = round(result["temp_c"] * 9 / 5 + 32, 1)
    assert result["temp_f"] == expected_f


def test_unknown_venue_id_returns_unavailable():
    result = get_match_weather(venue_id=99999, kickoff_date="2026-06-11")
    assert result["available"] is False
    assert result["temp_c"] is None


def test_none_venue_id_returns_unavailable():
    result = get_match_weather(venue_id=None, kickoff_date="2026-06-11")
    assert result["available"] is False


def test_summary_is_string():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0


def test_unavailable_summary_is_informative():
    result = get_match_weather(venue_id=99999, kickoff_date="2026-06-11")
    assert "not available" in result["summary"].lower()


def test_all_16_venues_in_coords():
    assert len(VENUE_COORDS) == 16


def test_date_preserved_in_result():
    result = get_match_weather(venue_id=1599, kickoff_date="2026-06-11")
    assert result["date"] == "2026-06-11"


# --- _condition --------------------------------------------------------------

def test_condition_hot_dry():
    assert "hot" in _condition(32, 0, 10)
    assert "dry" in _condition(32, 0, 10)


def test_condition_rainy():
    assert "rainy" in _condition(20, 10, 10)


def test_condition_light_rain():
    assert "light rain" in _condition(20, 2, 10)


def test_condition_windy():
    assert "windy" in _condition(20, 0, 25)


def test_condition_cold():
    assert "cold" in _condition(5, 0, 10)