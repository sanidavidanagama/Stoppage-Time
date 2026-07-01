"""
Prompt builder for the Tactics agent.

Assembles the full prompt by combining:
- Target fixture data (formations, lineups from Sportmonks)
- Past performance sections (from schedule service)
- The prompt template
"""

from __future__ import annotations

from pathlib import Path

from config.stat_types import get_stat_value
from service.schedule import build_team_form, fetch_fixture_detail


# ─── Position mapping ─────────────────────────────────────────────────────────

POSITION_LABELS = {
    24: "GK",
    25: "DEF",
    26: "MID",
    27: "FWD",
}


# ─── Formation extraction ────────────────────────────────────────────────────

def _get_formation(fixture: dict, team_id: int) -> str:
    """Get formation string for a team from fixture data."""
    for f in fixture.get("formations", []):
        if f["participant_id"] == team_id:
            return f["formation"]
    return "Not available"


# ─── Lineup formatting ───────────────────────────────────────────────────────

def _format_lineup(fixture: dict, team_id: int) -> str:
    """
    Format starting XI from fixture lineup data.

    Groups players by position (GK, DEF, MID, FWD) and lists them
    with jersey numbers.

    Returns something like:
        GK: Beach (18)
        DEF: Italiano (4), Circati (3), Souttar (19), Burgess (21), Bos (5)
        MID: Metcalfe (8), O'Neill (13), Okon-Engstler (24), Irankunda (17)
        FWD: Touré (9)
    """
    lineups = fixture.get("lineups", [])

    # type_id 11 = starting XI
    starters = [
        p for p in lineups
        if p.get("team_id") == team_id and p.get("type_id") == 11
    ]

    if not starters:
        return "Lineup not available"

    # Group by position
    grouped: dict[str, list[str]] = {"GK": [], "DEF": [], "MID": [], "FWD": []}

    # Sort by formation_position to get correct order
    starters.sort(key=lambda p: p.get("formation_position") or 99)

    for player in starters:
        pos_id = player.get("position_id", 0)
        pos_label = POSITION_LABELS.get(pos_id, "UNK")
        name = player.get("player_name", "Unknown")
        number = player.get("jersey_number", "?")
        grouped[pos_label].append(f"{name} ({number})")

    lines = []
    for pos in ["GK", "DEF", "MID", "FWD"]:
        if grouped[pos]:
            lines.append(f"{pos}: {', '.join(grouped[pos])}")

    return "\n".join(lines)


# ─── Participant helpers ──────────────────────────────────────────────────────

def _get_participants(fixture: dict) -> tuple[dict | None, dict | None]:
    """Returns (home, away) participant dicts."""
    participants = fixture.get("participants", [])
    home = next((p for p in participants if p["meta"]["location"] == "home"), None)
    away = next((p for p in participants if p["meta"]["location"] == "away"), None)
    return home, away


# ─── Prompt template ──────────────────────────────────────────────────────────

TACTICS_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "tactics_prompt.md"


def _load_tactics_prompt_template() -> str:
    return TACTICS_PROMPT_PATH.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: Build the full tactics prompt
# ═══════════════════════════════════════════════════════════════════════════════

def build_tactics_prompt(
    fixture_id: int,
    round_info: str = "",
    stadium: str = "",
    weather: str = "",
    h2h: str = "No head-to-head data available.",
) -> str:
    """
    Build the complete Tactics agent prompt for a given fixture.

    Steps:
        1. Fetch the target fixture detail (formations, lineups)
        2. Fetch past performances for both teams
        3. Assemble everything into the prompt template

    Args:
        fixture_id: Sportmonks fixture ID for the match to analyze.
        round_info: e.g. "Round of 16", "Group Stage MD3"
        stadium: Stadium name.
        weather: Weather description.
        h2h: Pre-formatted head-to-head text (from Supabase later).

    Returns:
        Complete prompt string ready to send to the Tactics LLM.
    """
    # Step 1: fetch current fixture
    print(f"\nFetching fixture detail for {fixture_id}...")
    fixture = fetch_fixture_detail(fixture_id)

    home, away = _get_participants(fixture)
    if not home or not away:
        return f"Error: Could not parse participants for fixture {fixture_id}"

    home_id = home["id"]
    away_id = away["id"]
    home_name = home["name"]
    away_name = away["name"]

    kick_off_time = fixture.get("starting_at", "Unknown")
    match_timestamp = fixture.get("starting_at_timestamp", 0)

    if not round_info:
        round_info = fixture.get("details", "Unknown round")

    # Step 2: formations and lineups from current fixture
    home_formation = _get_formation(fixture, home_id)
    away_formation = _get_formation(fixture, away_id)
    home_lineup = _format_lineup(fixture, home_id)
    away_lineup = _format_lineup(fixture, away_id)

    # Step 3: past performances
    print(f"\nBuilding past form for {home_name}...")
    home_form = build_team_form(home_id, home_name, match_timestamp)

    print(f"\nBuilding past form for {away_name}...")
    away_form = build_team_form(away_id, away_name, match_timestamp)

    # Step 4: assemble prompt
    prompt = _load_tactics_prompt_template().format(
        home_name=home_name,
        away_name=away_name,
        round_info=round_info,
        kick_off_time=kick_off_time,
        stadium=stadium,
        weather=weather,
        home_formation=home_formation,
        away_formation=away_formation,
        home_lineup=home_lineup,
        away_lineup=away_lineup,
        h2h=h2h,
        home_form_section=home_form,
        away_form_section=away_form,
    )

    return prompt