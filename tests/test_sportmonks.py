"""
tests/test_sportmonks.py

Tests for data/sportmonks.py
Run with: pytest tests/test_sportmonks.py -v
"""

import pytest
from data.identity import resolve_identity
from data.sportmonks import (
    get_predictions,
    get_odds,
    get_xg,
    get_lineups,
    get_fixture_meta,
    get_all,
)


# --- Fixture -----------------------------------------------------------------

@pytest.fixture(scope="module")
def identity_map():
    """Resolve identity once for all tests in this module."""
    return resolve_identity("Mexico", "South Africa")


# --- get_predictions ---------------------------------------------------------

def test_predictions_returns_required_keys(identity_map):
    result = get_predictions(identity_map)
    assert "one_x_two" in result
    assert "consensus" in result
    assert "binary" in result
    assert "available" in result


def test_predictions_has_1x2_models(identity_map):
    result = get_predictions(identity_map)
    assert result["available"] is True
    assert len(result["one_x_two"]) >= 1


def test_predictions_consensus_sums_to_100(identity_map):
    result = get_predictions(identity_map)
    c = result["consensus"]
    assert c is not None
    total = c["home"] + c["draw"] + c["away"]
    assert 99.0 <= total <= 101.0


def test_predictions_probabilities_in_range(identity_map):
    result = get_predictions(identity_map)
    for model in result["one_x_two"]:
        assert 0 <= model["home"] <= 100
        assert 0 <= model["draw"] <= 100
        assert 0 <= model["away"] <= 100


# --- get_odds ----------------------------------------------------------------

def test_odds_returns_required_keys(identity_map):
    result = get_odds(identity_map)
    assert "consensus" in result
    assert "bookmaker_count" in result
    assert "stale_count" in result
    assert "available" in result


def test_odds_has_bookmakers(identity_map):
    result = get_odds(identity_map)
    assert result["available"] is True
    assert result["bookmaker_count"] >= 1


def test_odds_consensus_in_range(identity_map):
    result = get_odds(identity_map)
    c = result["consensus"]
    assert c is not None
    assert 0 < c["home"] < 1
    assert 0 < c["draw"] < 1
    assert 0 < c["away"] < 1


def test_odds_mexico_is_favourite(identity_map):
    """Market should price Mexico as favourite."""
    result = get_odds(identity_map)
    c = result["consensus"]
    assert c["home"] > c["away"]


# --- get_xg ------------------------------------------------------------------

def test_xg_returns_required_keys(identity_map):
    result = get_xg(identity_map)
    assert "home_xg" in result
    assert "away_xg" in result
    assert "available" in result


def test_xg_unavailable_on_staging(identity_map):
    """xG is not seeded on staging — should return available=False."""
    result = get_xg(identity_map)
    assert result["available"] is False
    assert result["home_xg"] is None
    assert result["away_xg"] is None


# --- get_lineups -------------------------------------------------------------

def test_lineups_returns_required_keys(identity_map):
    result = get_lineups(identity_map)
    assert "home" in result
    assert "away" in result
    assert "available" in result


def test_lineups_structure_when_available(identity_map):
    """If lineups are available they must have formation and players."""
    result = get_lineups(identity_map)
    if result["available"]:
        for side in ["home", "away"]:
            if result[side]:
                assert "formation" in result[side]
                assert "players" in result[side]


# --- get_fixture_meta --------------------------------------------------------

def test_meta_returns_required_keys(identity_map):
    result = get_fixture_meta(identity_map)
    assert "venue_id" in result
    assert "round" in result
    assert "stage" in result
    assert "length" in result


def test_meta_length_is_90(identity_map):
    result = get_fixture_meta(identity_map)
    assert result["length"] == 90


def test_meta_stage_is_group(identity_map):
    result = get_fixture_meta(identity_map)
    assert result["stage"] == "Group Stage"


# --- get_all -----------------------------------------------------------------

def test_get_all_returns_all_sections(identity_map):
    result = get_all(identity_map)
    assert "predictions" in result
    assert "odds" in result
    assert "xg" in result
    assert "lineups" in result
    assert "meta" in result


def test_get_all_predictions_available(identity_map):
    result = get_all(identity_map)
    assert result["predictions"]["available"] is True


def test_get_all_odds_available(identity_map):
    result = get_all(identity_map)
    assert result["odds"]["available"] is True