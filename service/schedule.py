"""
Schedule service — fixture discovery and team form builder.

1. Fetches the full WC 2026 schedule (cached after first call)
2. Finds all finished fixtures for a given team before a cutoff time
3. Fetches detailed stats for each fixture
4. Formats into the team section (long + short + summary)
"""

from __future__ import annotations

import httpx

from config.settings import settings
from service.past_match_formatter import format_match_long, format_match_short, format_form_summary


# ─── Module-level cache ──────────────────────────────────────────────────────
_schedule_cache: dict | None = None


# ─── HTTP client ─────────────────────────────────────────────────────────────

def _client() -> httpx.Client:
    return httpx.Client(headers=settings.H_ARENA, timeout=30)


# ─── Schedule fetching ───────────────────────────────────────────────────────

def fetch_schedule() -> dict:
    """
    Fetch the full tournament schedule from Sportmonks.
    Cached in memory — safe to call repeatedly.
    """
    global _schedule_cache
    if _schedule_cache is not None:
        return _schedule_cache

    url = f"{settings.SPORTMONKS_PROXY}/schedules/seasons/{settings.SEASON_ID}"
    with _client() as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    # Handle proxy wrapper
    if "body" in data and "data" in data["body"]:
        _schedule_cache = data["body"]["data"]
    elif "data" in data:
        _schedule_cache = data["data"]
    else:
        _schedule_cache = data

    return _schedule_cache


def find_fixture_by_teams(
    home_name: str,
    away_name: str,
    schedule: list[dict] | None = None,
) -> dict | None:
    """
    Resolve human-readable team names (e.g. "Paraguay", "France") to a
    Sportmonks fixture_id plus both teams' participant IDs.

    Name matching is case-insensitive substring match against the fixture's
    "name" field (e.g. "Paraguay vs France").

    Args:
        home_name: Home team name.
        away_name: Away team name.
        schedule: Optional pre-fetched schedule. If None, fetches (cached).

    Returns:
        {
            "fixture_id": int,
            "name": str,
            "kickoff": str,
            "kickoff_timestamp": int,
            "home": {"team_id": int, "name": str},
            "away": {"team_id": int, "name": str},
        }
        or None if no match found.
    """
    if schedule is None:
        schedule = fetch_schedule()

    all_fixtures = _flatten_fixtures(schedule)

    for fix in all_fixtures:
        if fix.get("placeholder", False):
            continue

        name = fix.get("name", "")
        if home_name.lower() not in name.lower() or away_name.lower() not in name.lower():
            continue

        participants = fix.get("participants", [])
        home_p = next((p for p in participants if p.get("meta", {}).get("location") == "home"), None)
        away_p = next((p for p in participants if p.get("meta", {}).get("location") == "away"), None)
        if not home_p or not away_p:
            continue

        return {
            "fixture_id":        fix["id"],
            "name":              name,
            "kickoff":           fix.get("starting_at"),
            "kickoff_timestamp": fix.get("starting_at_timestamp"),
            "home": {"team_id": home_p["id"], "name": home_p.get("name", home_name)},
            "away": {"team_id": away_p["id"], "name": away_p.get("name", away_name)},
        }

    return None

def clear_schedule_cache():
    """Clear the cached schedule (useful for testing)."""
    global _schedule_cache
    _schedule_cache = None


# ─── Fixture flattening ─────────────────────────────────────────────────────

def _flatten_fixtures(schedule: list[dict]) -> list[dict]:
    """
    Flatten all fixtures from all stages and rounds into a single list.
    Handles both group stage (fixtures inside rounds) and knockout (fixtures directly on stage).
    """
    all_fixtures = []

    for stage in schedule:
        # Group stage: fixtures nested inside rounds
        rounds = stage.get("rounds", [])
        for rnd in rounds:
            for fix in rnd.get("fixtures", []):
                all_fixtures.append(fix)

        # Knockout stages: fixtures directly on the stage
        for fix in stage.get("fixtures", []):
            all_fixtures.append(fix)

    return all_fixtures


# ─── Team fixture discovery ──────────────────────────────────────────────────

def find_team_fixtures(
    team_id: int,
    before_timestamp: int,
    schedule: list[dict] | None = None,
) -> list[dict]:
    """
    Find all FINISHED fixtures for a team before a given kickoff timestamp.

    Args:
        team_id: Sportmonks participant ID.
        before_timestamp: Unix timestamp — only include fixtures before this.
        schedule: Optional pre-fetched schedule. If None, fetches from API.

    Returns:
        List of fixture dicts sorted chronologically (oldest first).
    """
    if schedule is None:
        schedule = fetch_schedule()

    all_fixtures = _flatten_fixtures(schedule)

    team_fixtures = []
    for fix in all_fixtures:
        # Skip placeholders (future knockout matches with TBD teams)
        if fix.get("placeholder", False):
            continue

        # Only finished matches (FT, AET, or after penalties)
        if fix.get("state_id") not in (5, 7, 8, 9):
            continue

        # Must be before the target match
        if fix.get("starting_at_timestamp", 0) >= before_timestamp:
            continue

        # Check if team is a participant
        participants = fix.get("participants", [])
        team_ids = [p["id"] for p in participants]
        if team_id in team_ids:
            team_fixtures.append(fix)

    # Sort by kickoff time (oldest first)
    team_fixtures.sort(key=lambda f: f.get("starting_at_timestamp", 0))

    return team_fixtures


# ─── Fixture detail fetching ─────────────────────────────────────────────────

FIXTURE_INCLUDES = "participants;formations;scores;statistics;events;lineups;pressure"


def fetch_fixture_detail(fixture_id: int) -> dict:
    """
    Fetch full fixture detail with all includes from Sportmonks.
    """
    url = f"{settings.SPORTMONKS_PROXY}/fixtures/{fixture_id}"
    params = {"include": FIXTURE_INCLUDES}

    with _client() as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    # Handle proxy wrapper
    if "body" in data and "data" in data["body"]:
        return data["body"]["data"]
    elif "data" in data:
        return data["data"]
    return data


# ─── Team form builder (main entry point) ────────────────────────────────────

def build_team_form(
    team_id: int,
    team_name: str,
    before_timestamp: int,
) -> str:
    """
    Build the full past-performances section for one team.

    Steps:
        1. Find all finished fixtures for this team before the cutoff
        2. Fetch detailed stats for each fixture
        3. Format: most recent → long format, rest → short format
        4. Append aggregated form summary

    Args:
        team_id: Sportmonks participant ID.
        team_name: Display name (e.g. "Paraguay").
        before_timestamp: Unix timestamp of the match being analyzed.

    Returns:
        Formatted markdown string for the Tactics prompt.
    """
    # Step 1: discover fixtures
    fixtures_basic = find_team_fixtures(team_id, before_timestamp)

    if not fixtures_basic:
        return f"### {team_name} Past Performances\n\nNo previous matches found."

    # Step 2: fetch detail for each
    fixtures_detail = []
    for fix in fixtures_basic:
        fid = fix["id"]
        print(f"  Fetching detail for {fix.get('name', fid)} (id: {fid})...")
        detail = fetch_fixture_detail(fid)
        fixtures_detail.append(detail)

    # Step 3 + 4: format into team section
    most_recent = fixtures_detail[-1]
    older = fixtures_detail[:-1]

    sections = [f"### {team_name} Past Performances\n"]

    # Long format for most recent
    sections.append(format_match_long(most_recent, team_id))

    # Short format for each older match (most recent first)
    for fix in reversed(older):
        sections.append("")
        sections.append(format_match_short(fix, team_id))

    # Aggregate summary across ALL matches
    sections.append("")
    sections.append(format_form_summary(fixtures_detail, team_id, team_name))

    return "\n".join(sections)


# ─── Match analysis builder (both teams) ─────────────────────────────────────

def build_match_form(
    home_id: int,
    home_name: str,
    away_id: int,
    away_name: str,
    match_timestamp: int,
) -> str:
    """
    Build past-performances sections for BOTH teams in a match.

    Returns a single string with both team sections separated by a blank line.
    """
    print(f"\n--- Building form for {home_name} ---")
    home_section = build_team_form(home_id, home_name, match_timestamp)

    print(f"\n--- Building form for {away_name} ---")
    away_section = build_team_form(away_id, away_name, match_timestamp)

    return home_section + "\n\n" + away_section