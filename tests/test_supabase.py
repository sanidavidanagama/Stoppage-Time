"""
tests/test_supabase.py

Tests for data/supabase.py
Run with: pytest tests/test_supabase.py -v
"""

import pytest
from data.identity import resolve_identity
from data.supabase import (
    get_country_style,
    get_stage_record,
    get_ko_pattern,
    get_h2h,
    get_checkpoint_stats,
    get_all,
)


# --- Fixture -----------------------------------------------------------------

@pytest.fixture(scope="module")
def identity_map():
    return resolve_identity("Mexico", "South Africa")


# --- get_country_style -------------------------------------------------------

def test_country_style_returns_required_keys(identity_map):
    result = get_country_style(identity_map)
    assert "home" in result
    assert "away" in result
    assert "available" in result


def test_country_style_available(identity_map):
    result = get_country_style(identity_map)
    assert result["available"] is True


def test_country_style_home_has_fields(identity_map):
    result = get_country_style(identity_map)
    home = result["home"]
    assert home is not None
    assert "set_piece_shots" in home
    assert "group_gpg" in home
    assert "conversion_rate" in home


def test_country_style_away_has_fields(identity_map):
    result = get_country_style(identity_map)
    away = result["away"]
    assert away is not None
    assert "set_piece_shots" in away
    assert "group_gpg" in away


# --- get_stage_record --------------------------------------------------------

def test_stage_record_returns_required_keys(identity_map):
    result = get_stage_record(identity_map)
    assert "home" in result
    assert "away" in result
    assert "available" in result


def test_stage_record_available(identity_map):
    result = get_stage_record(identity_map)
    assert result["available"] is True


def test_stage_record_home_has_group(identity_map):
    result = get_stage_record(identity_map)
    assert "group" in result["home"]
    group = result["home"]["group"]
    assert "matches" in group
    assert "wins" in group
    assert "win_rate" in group


def test_stage_record_win_rate_in_range(identity_map):
    result = get_stage_record(identity_map)
    for side in ["home", "away"]:
        if result[side] and "group" in result[side]:
            assert 0 <= result[side]["group"]["win_rate"] <= 1


# --- get_ko_pattern ----------------------------------------------------------

def test_ko_pattern_returns_required_keys(identity_map):
    result = get_ko_pattern(identity_map)
    assert "home" in result
    assert "away" in result
    assert "available" in result


def test_ko_pattern_available(identity_map):
    result = get_ko_pattern(identity_map)
    assert result["available"] is True


def test_ko_pattern_has_exit_stage(identity_map):
    result = get_ko_pattern(identity_map)
    for side in ["home", "away"]:
        if result[side]:
            assert "modal_exit_stage" in result[side]


# --- get_h2h -----------------------------------------------------------------

def test_h2h_returns_required_keys(identity_map):
    result = get_h2h(identity_map)
    assert "matches" in result
    assert "home_win_rate" in result
    assert "last_meeting" in result
    assert "available" in result


def test_h2h_mex_zaf_no_data(identity_map):
    """MEX vs ZAF have no h2h record in this dataset."""
    result = get_h2h(identity_map)
    assert result["available"] is False


# --- get_checkpoint_stats ----------------------------------------------------

def test_checkpoint_stats_returns_required_keys(identity_map):
    result = get_checkpoint_stats(identity_map)
    assert "home_matches" in result
    assert "available" in result


def test_checkpoint_stats_has_mexico_matches(identity_map):
    result = get_checkpoint_stats(identity_map)
    assert result["available"] is True
    assert len(result["home_matches"]) == 3


def test_checkpoint_stats_match_fields(identity_map):
    result = get_checkpoint_stats(identity_map)
    for match in result["home_matches"]:
        assert "opponent" in match
        assert "cum_goals" in match
        assert "cum_shots_total" in match
        assert "cum_possession_pct" in match


# --- get_all -----------------------------------------------------------------

def test_get_all_returns_all_sections(identity_map):
    result = get_all(identity_map)
    for key in ["country_style", "stage_record",
                "ko_pattern", "h2h", "checkpoint_stats"]:
        assert key in result


def test_get_all_country_style_available(identity_map):
    result = get_all(identity_map)
    assert result["country_style"]["available"] is True


def test_get_all_checkpoint_available(identity_map):
    result = get_all(identity_map)
    assert result["checkpoint_stats"]["available"] is True