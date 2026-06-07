"""
data/supabase.py

Fetches historical and live match data from Supabase.
Uses identity_map from data/identity.py for all ID lookups.
No LLM calls here — pure data fetching and cleaning.

Functions:
    get_country_style(identity_map)    -> set piece + goals per game stats
    get_stage_record(identity_map)     -> W/D/L per tournament stage
    get_ko_pattern(identity_map)       -> knockout stage patterns
    get_h2h(identity_map)              -> head to head record
    get_checkpoint_stats(identity_map) -> live match stats (2022 WC)
    get_all(identity_map)              -> runs all of the above
"""

import requests
from config import settings


# --- Country style ------------------------------------------------------------

def get_country_style(identity_map: dict) -> dict:
    """
    Fetch set piece efficiency and goals per game from ads_a_country_style.
    Uses StatsBomb priors IDs (sb_priors_id).

    Returns:
        {
            "home": {set_piece_shots, set_piece_goals, conversion_rate,
                     group_gpg, ko_gpg, group_goals_against} | None,
            "away": same shape | None,
            "available": bool,
        }
    """
    home_id = identity_map["home"].get("sb_priors_id")
    away_id = identity_map["away"].get("sb_priors_id")

    ids = [i for i in [home_id, away_id] if i is not None]
    if not ids:
        return {"home": None, "away": None, "available": False}

    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_country_style",
        params={"select": "*", "country_id": f"in.({','.join(map(str, ids))})"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    rows = {row["country_id"]: row for row in r.json()}

    def _extract(row: dict | None) -> dict | None:
        if row is None:
            return None
        return {
            "set_piece_shots":    row.get("set_piece_shots"),
            "set_piece_goals":    row.get("set_piece_goals"),
            "conversion_rate":    row.get("conversion_rate"),
            "group_matches":      row.get("group_matches"),
            "group_gpg":          row.get("group_gpg"),
            "group_goals_against": row.get("group_goals_against"),
            "ko_matches":         row.get("ko_matches"),
            "ko_gpg":             row.get("ko_gpg"),
        }

    home_data = _extract(rows.get(home_id))
    away_data = _extract(rows.get(away_id))

    return {
        "home":      home_data,
        "away":      away_data,
        "available": home_data is not None or away_data is not None,
    }


# --- Stage record -------------------------------------------------------------

def get_stage_record(identity_map: dict) -> dict:
    """
    Fetch W/D/L record per tournament stage from ads_a_stage_record.
    Uses StatsBomb priors IDs.

    Returns:
        {
            "home": {"group": {matches, wins, draws, losses, win_rate},
                     "r16":   {...}, ...} | None,
            "away": same shape | None,
            "available": bool,
        }
    """
    home_id = identity_map["home"].get("sb_priors_id")
    away_id = identity_map["away"].get("sb_priors_id")

    ids = [i for i in [home_id, away_id] if i is not None]
    if not ids:
        return {"home": None, "away": None, "available": False}

    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_stage_record",
        params={"select": "*", "country_id": f"in.({','.join(map(str, ids))})"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    def _build(country_id: int) -> dict | None:
        country_rows = [row for row in r.json() if row["country_id"] == country_id]
        if not country_rows:
            return None
        return {
            row["stage_canonical"]: {
                "matches":  row["matches"],
                "wins":     row["wins"],
                "draws":    row["draws"],
                "losses":   row["losses"],
                "win_rate": round(row["win_rate"], 3),
            }
            for row in country_rows
        }

    home_data = _build(home_id) if home_id else None
    away_data = _build(away_id) if away_id else None

    return {
        "home":      home_data,
        "away":      away_data,
        "available": home_data is not None or away_data is not None,
    }


# --- Knockout pattern ---------------------------------------------------------

def get_ko_pattern(identity_map: dict) -> dict:
    """
    Fetch knockout stage patterns from ads_a_ko_pattern.
    Shows how far each team typically progresses.

    Returns:
        {
            "home": {tournaments_reached_ko, modal_exit_stage,
                     first_ko_loss_rate} | None,
            "away": same shape | None,
            "available": bool,
        }
    """
    home_id = identity_map["home"].get("sb_priors_id")
    away_id = identity_map["away"].get("sb_priors_id")

    ids = [i for i in [home_id, away_id] if i is not None]
    if not ids:
        return {"home": None, "away": None, "available": False}

    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_ko_pattern",
        params={"select": "*", "country_id": f"in.({','.join(map(str, ids))})"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    rows = {row["country_id"]: row for row in r.json()}

    def _extract(row: dict | None) -> dict | None:
        if row is None:
            return None
        return {
            "tournaments_reached_ko": row.get("tournaments_reached_ko"),
            "modal_exit_stage":       row.get("modal_exit_stage"),
            "first_ko_loss_rate":     row.get("first_ko_loss_rate"),
        }

    home_data = _extract(rows.get(home_id))
    away_data = _extract(rows.get(away_id))

    return {
        "home":      home_data,
        "away":      away_data,
        "available": home_data is not None or away_data is not None,
    }


# --- Head to head -------------------------------------------------------------

def get_h2h(identity_map: dict) -> dict:
    """
    Fetch head to head record between the two teams.
    Uses StatsBomb priors IDs.
    Note: dataset is limited — many matchups will return no rows.

    Returns:
        {
            "matches":          int | None,
            "home_win_rate":    float | None,
            "last_meeting":     str | None,
            "available":        bool,
        }
    """
    home_id = identity_map["home"].get("sb_priors_id")
    away_id = identity_map["away"].get("sb_priors_id")

    if not home_id or not away_id:
        return {"matches": None, "home_win_rate": None,
                "last_meeting": None, "available": False}

    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_h2h_country",
        params={
            "select":       "*",
            "country_id_a": f"eq.{home_id}",
            "country_id_b": f"eq.{away_id}",
            "match_scope":  "eq.all",
        },
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    rows = r.json()
    if not rows:
        return {"matches": None, "home_win_rate": None,
                "last_meeting": None, "available": False}

    row = rows[0]
    return {
        "matches":       row.get("total_matches"),
        "home_win_rate": row.get("win_rate_a_weighted"),
        "last_meeting":  row.get("last_meeting_date"),
        "available":     True,
    }


# --- Checkpoint stats ---------------------------------------------------------

def get_checkpoint_stats(identity_map: dict) -> dict:
    """
    Fetch 2022 WC checkpoint stats for the home team.
    Only home team queried since away team (ZAF) has no 2022 WC data.
    Uses sm_team_id for the snapshot query.

    Returns:
        {
            "home_matches": [
                {
                    "opponent", "is_home", "cum_goals",
                    "cum_shots_total", "cum_shots_on_target",
                    "cum_possession_pct", "cum_pass_accuracy_pct",
                    "cum_yellow_cards"
                }, ...
            ],
            "available": bool,
        }
    """
    if not identity_map["home"].get("has_supabase"):
        return {"home_matches": [], "available": False}

    home_team_id = identity_map["home"]["sm_team_id"]

    # get all match IDs for home team from dim_match
    r_dim = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/dim_match",
        params={"select": "match_id,team_name_a,team_name_b,country_id_a,country_id_b"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r_dim.raise_for_status()

    home_name = identity_map["home"]["name"]
    match_lookup = {}
    match_ids    = []

    for row in r_dim.json():
        if row["team_name_a"] == home_name:
            match_lookup[row["match_id"]] = f"vs {row['team_name_b']}"
            match_ids.append(row["match_id"])
        elif row["team_name_b"] == home_name:
            match_lookup[row["match_id"]] = f"vs {row['team_name_a']}"
            match_ids.append(row["match_id"])

    if not match_ids:
        return {"home_matches": [], "available": False}

    # fetch FT snapshots for those matches
    ids_str = ",".join(map(str, match_ids))
    r_snap = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/d_checkpoint_snapshot",
        params={
            "select":          "*",
            "match_id":        f"in.({ids_str})",
            "team_id":         f"eq.{home_team_id}",
            "checkpoint_code": "eq.FT",
        },
        headers=settings.H_WCA,
        timeout=10,
    )
    r_snap.raise_for_status()

    matches = []
    for row in r_snap.json():
        matches.append({
            "opponent":              match_lookup.get(row["match_id"], "Unknown"),
            "is_home":               row.get("is_home"),
            "cum_goals":             row.get("cum_goals"),
            "cum_shots_total":       row.get("cum_shots_total"),
            "cum_shots_on_target":   row.get("cum_shots_on_target"),
            "cum_possession_pct":    row.get("cum_possession_pct"),
            "cum_pass_accuracy_pct": row.get("cum_pass_accuracy_pct"),
            "cum_yellow_cards":      row.get("cum_yellow_cards"),
            "cum_red_cards":         row.get("cum_red_cards"),
        })

    return {
        "home_matches": matches,
        "available":    len(matches) > 0,
    }


# --- Fetch all ----------------------------------------------------------------

def get_all(identity_map: dict) -> dict:
    """
    Runs all Supabase fetchers and returns a single clean dict.
    This is what the orchestrator calls.

    Returns:
        {
            "country_style":    {...},
            "stage_record":     {...},
            "ko_pattern":       {...},
            "h2h":              {...},
            "checkpoint_stats": {...},
        }
    """
    return {
        "country_style":    get_country_style(identity_map),
        "stage_record":     get_stage_record(identity_map),
        "ko_pattern":       get_ko_pattern(identity_map),
        "h2h":              get_h2h(identity_map),
        "checkpoint_stats": get_checkpoint_stats(identity_map),
    }