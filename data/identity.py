"""
data/identity.py

Resolves team identities across all data systems before any query.
Always called first by the orchestrator.

Four ID systems:
    Sportmonks  -> team_id, country_id
    StatsBomb   -> priors country_id (looked up by name via h2h table)
    Polymarket  -> event slug, condition ids, token ids
    Supabase    -> dim_match country_id (for checkpoint queries)
"""

import requests
from datetime import datetime, timezone, timedelta
from config import settings


# --- Upcoming fixture discovery -----------------------------------------------

def get_upcoming_fixture(hours_ahead: int = 1) -> dict | None:
    try:
        r = requests.get(
            f"{settings.SPORTMONKS_PROXY}/schedules/seasons/{settings.SEASON_ID}",
            headers=settings.H_ARENA,
            timeout=15,
        )
        r.raise_for_status()

        now      = datetime.now(timezone.utc)
        cutoff   = now + timedelta(hours=hours_ahead)
        upcoming = []

        for stage in r.json()["body"]["data"]:
            for round_ in (stage.get("rounds") or []):
                for fixture in (round_.get("fixtures") or []):
                    kickoff_str = fixture.get("starting_at")
                    if not kickoff_str:
                        continue
                    try:
                        kickoff = datetime.fromisoformat(
                            kickoff_str.replace(" ", "T") + "+00:00"
                        )
                    except ValueError:
                        continue
                    if now <= kickoff <= cutoff:
                        name  = fixture.get("name", "")
                        parts = [p.strip() for p in name.split("vs")]
                        upcoming.append({
                            "fixture_id":   fixture["id"],
                            "fixture_name": name,
                            "home":         parts[0] if len(parts) == 2 else name,
                            "away":         parts[1] if len(parts) == 2 else name,
                            "kickoff":      kickoff_str,
                            "_kickoff_dt":  kickoff,
                        })

        if not upcoming:
            return None

        # return the earliest upcoming fixture
        earliest = min(upcoming, key=lambda x: x["_kickoff_dt"])
        earliest.pop("_kickoff_dt")
        return earliest

    except Exception:
        return None


# --- Fixture discovery --------------------------------------------------------

def find_fixture(home_name: str, away_name: str) -> dict | None:
    """
    Search the WC2026 schedule for a fixture matching home/away team names.
    Returns the fixture row dict or None if not found.
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/schedules/seasons/{settings.SEASON_ID}",
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    schedule = r.json()["body"]["data"]

    for stage in schedule:
        for round_ in (stage.get("rounds") or []):
            for fixture in (round_.get("fixtures") or []):
                name = fixture.get("name", "")
                if (
                    home_name.lower() in name.lower()
                    and away_name.lower() in name.lower()
                ):
                    return {
                        "fixture_id": fixture["id"],
                        "name":       name,
                        "kickoff":    fixture.get("starting_at"),
                        "stage":      stage["name"],
                        "round":      round_["name"],
                    }
    return None


# --- Sportmonks identities ----------------------------------------------------

def _get_sportmonks_identities(fixture_id: int) -> dict:
    """
    Fetch fixture participants and extract Sportmonks team_id + country_id
    for home and away teams.
    """
    r = requests.get(
        f"{settings.SPORTMONKS_PROXY}/fixtures/{fixture_id}",
        params={"include": "participants"},
        headers=settings.H_ARENA,
        timeout=15,
    )
    r.raise_for_status()

    participants = r.json()["body"]["data"]["participants"]
    home = next(p for p in participants if p["meta"]["location"] == "home")
    away = next(p for p in participants if p["meta"]["location"] == "away")

    return {
        "home": {
            "name":           home["name"],
            "short_code":     home["short_code"],
            "sm_team_id":     home["id"],
            "sm_country_id":  home["country_id"],
        },
        "away": {
            "name":           away["name"],
            "short_code":     away["short_code"],
            "sm_team_id":     away["id"],
            "sm_country_id":  away["country_id"],
        },
    }


# --- Polymarket identities ----------------------------------------------------

def _get_polymarket_identity(fixture_id: int) -> dict | None:
    """
    Call Arena mapping endpoint to get Polymarket slug + condition/token IDs.
    Returns None if no Polymarket market exists for this fixture.
    """
    r = requests.get(
        f"{settings.ARENA}/api/v1/web/mapping",
        params={"fixture_id": fixture_id},
        headers=settings.H_ARENA,
        timeout=10,
    )
    r.raise_for_status()

    mappings = r.json().get("mappings") or []
    if not mappings:
        return None

    m = mappings[0]
    return {
        "event_slug":          m["polymarket_event_slug"],
        "match_confidence":    m["match_confidence"],
        "home_condition_id":   m["polymarket_home_condition_id"],
        "home_token_yes":      m["polymarket_home_token_yes"],
        "draw_condition_id":   m["polymarket_draw_condition_id"],
        "draw_token_yes":      m["polymarket_draw_token_yes"],
        "away_condition_id":   m["polymarket_away_condition_id"],
        "away_token_yes":      m["polymarket_away_token_yes"],
    }


# --- StatsBomb priors ID ------------------------------------------------------

def _get_statsbomb_ids(home_name: str, away_name: str) -> dict:
    """
    Look up StatsBomb country_id for each team via the h2h name lookup table.
    This ID differs from Sportmonks and must be used for all ads_a_* tables.
    Returns home_sb_id and away_sb_id (None if not found).
    """
    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_h2h_country",
        params={"select": "country_id_a,country_name_a,country_id_b,country_name_b"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    name_to_id: dict = {}
    for row in r.json():
        name_to_id[row["country_name_a"]] = row["country_id_a"]
        name_to_id[row["country_name_b"]] = row["country_id_b"]

    return {
        "home_sb_id": name_to_id.get(home_name),
        "away_sb_id": name_to_id.get(away_name),
    }


# --- Supabase dim_match ID ----------------------------------------------------

def _get_supabase_dim_ids(home_name: str, away_name: str) -> dict:
    """
    Look up country_id from dim_match by team name.
    Used for checkpoint queries (d_checkpoint_snapshot, d_match_scores).
    Returns home_sb_dim_id and away_sb_dim_id (None if not found).
    """
    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/dim_match",
        params={"select": "team_name_a,country_id_a,team_name_b,country_id_b"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()

    name_to_id: dict = {}
    for row in r.json():
        name_to_id[row["team_name_a"]] = row["country_id_a"]
        name_to_id[row["team_name_b"]] = row["country_id_b"]

    return {
        "home_sb_dim_id": name_to_id.get(home_name),
        "away_sb_dim_id": name_to_id.get(away_name),
    }


# --- Master resolver ----------------------------------------------------------

def resolve_identity(home_name: str, away_name: str) -> dict:
    """
    Master identity resolver. Call this once at the start of every session.

    Args:
        home_name: Home team name e.g. "Mexico"
        away_name: Away team name e.g. "South Africa"

    Returns:
        identity_map dict with all IDs resolved across all systems.

    Raises:
        ValueError if fixture not found in WC2026 schedule.
    """
    # 1. Find fixture
    fixture = find_fixture(home_name, away_name)
    if not fixture:
        raise ValueError(
            f"No WC2026 fixture found for '{home_name}' vs '{away_name}'. "
            f"Check spelling or try swapping home/away."
        )

    fixture_id = fixture["fixture_id"]

    # 2. Sportmonks identities
    sm = _get_sportmonks_identities(fixture_id)

    # 3. Polymarket identities
    pm = _get_polymarket_identity(fixture_id)

    # 4. StatsBomb priors IDs
    sb = _get_statsbomb_ids(sm["home"]["name"], sm["away"]["name"])

    # 5. Supabase dim_match IDs
    dim = _get_supabase_dim_ids(sm["home"]["name"], sm["away"]["name"])

    # 6. Assemble master identity map
    return {
        "fixture_id":   fixture_id,
        "fixture_name": fixture["name"],
        "kickoff":      fixture["kickoff"],
        "stage":        fixture["stage"],
        "round":        fixture["round"],

        "home": {
            "name":            sm["home"]["name"],
            "short_code":      sm["home"]["short_code"],
            "sm_team_id":      sm["home"]["sm_team_id"],
            "sm_country_id":   sm["home"]["sm_country_id"],
            "sb_priors_id":    sb["home_sb_id"],
            "sb_dim_id":       dim["home_sb_dim_id"],
            "pm_condition_id": pm["home_condition_id"] if pm else None,
            "pm_token_yes":    pm["home_token_yes"] if pm else None,
            "has_polymarket":  pm is not None,
            "has_supabase":    dim["home_sb_dim_id"] is not None,
            "has_sb_priors":   sb["home_sb_id"] is not None,
        },
        "away": {
            "name":            sm["away"]["name"],
            "short_code":      sm["away"]["short_code"],
            "sm_team_id":      sm["away"]["sm_team_id"],
            "sm_country_id":   sm["away"]["sm_country_id"],
            "sb_priors_id":    sb["away_sb_id"],
            "sb_dim_id":       dim["away_sb_dim_id"],
            "pm_condition_id": pm["away_condition_id"] if pm else None,
            "pm_token_yes":    pm["away_token_yes"] if pm else None,
            "has_polymarket":  pm is not None,
            "has_supabase":    dim["away_sb_dim_id"] is not None,
            "has_sb_priors":   sb["away_sb_id"] is not None,
        },
        "draw": {
            "pm_condition_id": pm["draw_condition_id"] if pm else None,
            "pm_token_yes":    pm["draw_token_yes"] if pm else None,
        },

        "pm_event_slug":       pm["event_slug"] if pm else None,
        "pm_match_confidence": pm["match_confidence"] if pm else None,
    }


# --- Pretty print -------------------------------------------------------------

def print_identity_map(im: dict) -> None:
    """Print a clean summary of the resolved identity map."""
    print(f"{'='*55}")
    print(f"IDENTITY MAP  {im['fixture_name']}")
    print(f"{'='*55}")
    print(f"Kickoff   : {im['kickoff']}")
    print(f"Stage     : {im['stage']} -- Round {im['round']}")
    print(f"Fixture ID: {im['fixture_id']}")
    print()
    print(f"{'System':<25} {'Home':>12} {'Away':>15}")
    print(f"{'---'*18}")
    print(f"{'Name':<25} {im['home']['name']:>12} {im['away']['name']:>15}")
    print(f"{'Short code':<25} {im['home']['short_code']:>12} {im['away']['short_code']:>15}")
    print(f"{'SM team_id':<25} {str(im['home']['sm_team_id']):>12} {str(im['away']['sm_team_id']):>15}")
    print(f"{'SM country_id':<25} {str(im['home']['sm_country_id']):>12} {str(im['away']['sm_country_id']):>15}")
    print(f"{'SB priors_id':<25} {str(im['home']['sb_priors_id']):>12} {str(im['away']['sb_priors_id']):>15}")
    print(f"{'SB dim_id':<25} {str(im['home']['sb_dim_id']):>12} {str(im['away']['sb_dim_id']):>15}")
    print()
    print("Data availability:")
    for side in ["home", "away"]:
        t = im[side]
        print(
            f"  {t['name']:<20}"
            f"  polymarket={'yes' if t['has_polymarket'] else 'no '}"
            f"  supabase={'yes' if t['has_supabase'] else 'no '}"
            f"  sb_priors={'yes' if t['has_sb_priors'] else 'no '}"
        )
    print(f"{'='*55}")