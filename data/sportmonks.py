"""
data/sportmonks.py

Fetches all Sportmonks data for a given fixture.
All functions take the identity_map from data/identity.py.
No LLM calls here — pure data fetching and cleaning.

Functions:
    get_predictions(identity_map)   -> ML model probabilities
    get_odds(identity_map)          -> bookmaker consensus (1X2 only)
    get_xg(identity_map)            -> expected goals (if available)
    get_lineups(identity_map)       -> formations and starting XI
    get_fixture_meta(identity_map)  -> venue, referee, kickoff
    get_all(identity_map)           -> runs all of the above
"""

import requests
from config import settings


# --- Predictions --------------------------------------------------------------

def get_predictions(identity_map: dict) -> dict:
    """
    Fetch Sportmonks ML predictions for the fixture.
    Separates 1X2 models from binary (yes/no) models.

    Returns:
        {
            "one_x_two": [{"type_id", "home", "draw", "away"}, ...],
            "consensus": {"home", "draw", "away"} | None,
            "binary":    [{"type_id", "yes", "no"}, ...],
            "available": bool
        }
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{identity_map['fixture_id']}",
        params={"include": "predictions"},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    raw = r.json()["body"]["data"].get("predictions") or []

    one_x_two = []
    binary    = []

    for p in raw:
        probs = p.get("predictions") or {}
        if "home" in probs and "draw" in probs:
            one_x_two.append({
                "type_id": p["type_id"],
                "home":    round(float(probs["home"]), 2),
                "draw":    round(float(probs["draw"]), 2),
                "away":    round(float(probs["away"]), 2),
            })
        elif "yes" in probs and "no" in probs:
            binary.append({
                "type_id": p["type_id"],
                "yes":     round(float(probs["yes"]), 2),
                "no":      round(float(probs["no"]), 2),
            })

    # consensus = simple average across 1X2 models
    consensus = None
    if one_x_two:
        consensus = {
            "home": round(sum(m["home"] for m in one_x_two) / len(one_x_two), 2),
            "draw": round(sum(m["draw"] for m in one_x_two) / len(one_x_two), 2),
            "away": round(sum(m["away"] for m in one_x_two) / len(one_x_two), 2),
        }

    return {
        "one_x_two": one_x_two,
        "consensus": consensus,
        "binary":    binary,
        "available": len(one_x_two) > 0,
    }


# --- Bookmaker odds -----------------------------------------------------------

def get_odds(identity_map: dict) -> dict:
    """
    Fetch bookmaker odds and compute consensus implied probabilities.
    Filters to market_id == 1 (Fulltime Result / 1X2) only.
    Excludes stale bookmakers (not updated today).

    Returns:
        {
            "consensus":        {"home", "draw", "away"} | None,
            "bookmaker_count":  int,
            "stale_count":      int,
            "available":        bool
        }
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{identity_map['fixture_id']}",
        params={"include": "odds"},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    raw  = r.json()["body"]["data"].get("odds") or []
    ftrs = [o for o in raw if o.get("market_id") == 1]

    if not ftrs:
        return {"consensus": None, "bookmaker_count": 0,
                "stale_count": 0, "available": False}

    # find most recent update date
    dates = [o.get("latest_bookmaker_update", "") for o in ftrs if o.get("latest_bookmaker_update")]
    latest_date = max(dates)[:10] if dates else ""

    fresh  = [o for o in ftrs if (o.get("latest_bookmaker_update") or "").startswith(latest_date)]
    stale  = len(ftrs) - len(fresh)

    def _avg(label: str) -> float | None:
        rows = [o for o in fresh if (o.get("label") or "").lower() == label.lower()]
        if not rows:
            return None
        probs = []
        for o in rows:
            raw_p = (o.get("probability") or "0").replace("%", "").strip()
            try:
                probs.append(float(raw_p) / 100)
            except ValueError:
                pass
        return round(sum(probs) / len(probs), 4) if probs else None

    home = _avg("Home")
    draw = _avg("Draw")
    away = _avg("Away")

    consensus = {"home": home, "draw": draw, "away": away} if all(
        v is not None for v in [home, draw, away]
    ) else None

    return {
        "consensus":       consensus,
        "bookmaker_count": len(set(o["bookmaker_id"] for o in fresh)),
        "stale_count":     stale,
        "available":       consensus is not None,
    }


# --- Expected goals -----------------------------------------------------------

def get_xg(identity_map: dict) -> dict:
    """
    Fetch expected goals (xG) per team.
    Returns None values if xG not available (common on staging).

    Returns:
        {
            "home_xg":   float | None,
            "away_xg":   float | None,
            "available": bool
        }
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{identity_map['fixture_id']}",
        params={"include": "xgfixture"},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    xg_rows = r.json()["body"]["data"].get("xgfixture") or []

    home_xg = None
    away_xg = None

    for row in xg_rows:
        pid = row.get("participant_id")
        val = row.get("value")
        if pid == identity_map["home"]["sm_team_id"]:
            home_xg = val
        elif pid == identity_map["away"]["sm_team_id"]:
            away_xg = val

    return {
        "home_xg":   home_xg,
        "away_xg":   away_xg,
        "available": home_xg is not None or away_xg is not None,
    }


# --- Lineups ------------------------------------------------------------------

def get_lineups(identity_map: dict) -> dict:
    """
    Fetch lineups and formations for both teams.
    Returns empty if lineups not yet published (normal pre-match).

    Returns:
        {
            "home": {"formation", "players"} | None,
            "away": {"formation", "players"} | None,
            "available": bool
        }
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{identity_map['fixture_id']}",
        params={"include": "lineups"},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    lineups = r.json()["body"]["data"].get("lineups") or []

    home_lineup = None
    away_lineup = None

    for lineup in lineups:
        tid = lineup.get("team_id")
        entry = {
            "formation": lineup.get("formation"),
            "players":   lineup.get("players") or [],
        }
        if tid == identity_map["home"]["sm_team_id"]:
            home_lineup = entry
        elif tid == identity_map["away"]["sm_team_id"]:
            away_lineup = entry

    return {
        "home":      home_lineup,
        "away":      away_lineup,
        "available": home_lineup is not None or away_lineup is not None,
    }


# --- Fixture metadata ---------------------------------------------------------

def get_fixture_meta(identity_map: dict) -> dict:
    """
    Fetch fixture metadata: venue, referee, round, stage.

    Returns:
        {
            "venue_id":   int | None,
            "referee_id": int | None,
            "round":      str,
            "stage":      str,
            "length":     int,
        }
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{identity_map['fixture_id']}",
        params={"include": ""},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    data = r.json()["body"]["data"]

    return {
        "venue_id":   data.get("venue_id"),
        "referee_id": data.get("referee_id"),
        "round":      identity_map["round"],
        "stage":      identity_map["stage"],
        "length":     data.get("length", 90),
    }


# --- Fetch all ----------------------------------------------------------------

def get_all(identity_map: dict) -> dict:
    """
    Runs all Sportmonks fetchers and returns a single clean dict.
    This is what the orchestrator calls.

    Returns:
        {
            "predictions": {...},
            "odds":        {...},
            "xg":          {...},
            "lineups":     {...},
            "meta":        {...},
        }
    """
    return {
        "predictions": get_predictions(identity_map),
        "odds":        get_odds(identity_map),
        "xg":          get_xg(identity_map),
        "lineups":     get_lineups(identity_map),
        "meta":        get_fixture_meta(identity_map),
    }