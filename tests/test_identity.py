"""
tests/test_identity.py

Tests for data/identity.py
Run with: pytest tests/test_identity.py -v
"""

import pytest
from data.identity import (
    find_fixture,
    resolve_identity,
    print_identity_map,
)


# --- find_fixture -------------------------------------------------------------

def test_find_fixture_known_match():
    """Mexico vs South Africa should exist in WC2026 schedule."""
    fixture = find_fixture("Mexico", "South Africa")
    assert fixture is not None
    assert fixture["fixture_id"] == 19609127
    assert "Mexico" in fixture["name"]
    assert "South Africa" in fixture["name"]


def test_find_fixture_case_insensitive():
    """Name matching should be case insensitive."""
    fixture = find_fixture("mexico", "south africa")
    assert fixture is not None


def test_find_fixture_not_found():
    """A made-up fixture should return None."""
    fixture = find_fixture("Narnia", "Mordor")
    assert fixture is None


# --- resolve_identity ---------------------------------------------------------

def test_resolve_identity_returns_all_keys():
    """Identity map must have all required top-level keys."""
    im = resolve_identity("Mexico", "South Africa")
    assert "fixture_id" in im
    assert "fixture_name" in im
    assert "kickoff" in im
    assert "home" in im
    assert "away" in im
    assert "draw" in im
    assert "pm_event_slug" in im


def test_resolve_identity_home_team():
    """Home team identities should be correctly resolved."""
    im = resolve_identity("Mexico", "South Africa")
    assert im["home"]["name"] == "Mexico"
    assert im["home"]["short_code"] == "MEX"
    assert im["home"]["sm_team_id"] == 18576
    assert im["home"]["sm_country_id"] == 458
    assert im["home"]["sb_priors_id"] == 147
    assert im["home"]["has_polymarket"] is True


def test_resolve_identity_away_team():
    """Away team identities should be correctly resolved."""
    im = resolve_identity("Mexico", "South Africa")
    assert im["away"]["name"] == "South Africa"
    assert im["away"]["short_code"] == "ZAF"
    assert im["away"]["sb_priors_id"] == 211
    assert im["away"]["has_supabase"] is False


def test_resolve_identity_polymarket():
    """Polymarket slug should be resolved."""
    im = resolve_identity("Mexico", "South Africa")
    assert im["pm_event_slug"] == "fifwc-mex-rsa-2026-06-11"
    assert im["pm_match_confidence"] == "high"
    assert im["draw"]["pm_condition_id"] is not None


def test_resolve_identity_invalid_match():
    """Invalid match should raise ValueError."""
    with pytest.raises(ValueError):
        resolve_identity("Narnia", "Mordor")


# --- print_identity_map -------------------------------------------------------

def test_print_identity_map_runs(capsys):
    """print_identity_map should print without errors."""
    im = resolve_identity("Mexico", "South Africa")
    print_identity_map(im)
    captured = capsys.readouterr()
    assert "Mexico" in captured.out
    assert "South Africa" in captured.out
    assert "IDENTITY MAP" in captured.out