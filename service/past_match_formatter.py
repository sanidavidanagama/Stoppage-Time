"""
Formatter service — transforms raw Sportmonks fixture detail into
text formats consumed by the Tactics agent prompt.

Long format:   Full match detail (goals, pressing bands, stat table).
               Used for the most recent match only.

Short format:  Per-match condensed entry with opponent, result, key stats.
               Used for each older match individually.

Form summary:  Aggregated averages across all previous matches.
               Appended at the end.

Team section:  Orchestrator that combines long + shorts + summary.
"""

from __future__ import annotations

from config.stat_types import TACTICS_STATS, get_stat_value


# ─── Score helpers ────────────────────────────────────────────────────────────

def _extract_score(scores: list[dict], participant_id: int, description: str) -> int:
    for s in scores:
        if s["participant_id"] == participant_id and s["description"] == description:
            return s["score"]["goals"]
    return 0


def _get_result_line(fixture: dict, home_id: int, away_id: int) -> str:
    scores = fixture.get("scores", [])
    ft_home = _extract_score(scores, home_id, "CURRENT")
    ft_away = _extract_score(scores, away_id, "CURRENT")
    ht_home = _extract_score(scores, home_id, "1ST_HALF")
    ht_away = _extract_score(scores, away_id, "1ST_HALF")
    return f"{ft_home}-{ft_away} (HT: {ht_home}-{ht_away})"


def _get_result_tag(team_goals: int, opp_goals: int) -> str:
    if team_goals > opp_goals:
        return "W"
    elif team_goals < opp_goals:
        return "L"
    return "D"


# ─── Goal helpers ─────────────────────────────────────────────────────────────

def _format_goals(events: list[dict], home_id: int, away_id: int, home_name: str, away_name: str) -> str:
    goals = [e for e in events if e["type_id"] == 14]
    goals.sort(key=lambda g: (g["minute"], g.get("extra_minute") or 0))

    if not goals:
        return "  No goals"

    lines = []
    for g in goals:
        minute = g["minute"]
        extra = g.get("extra_minute")
        minute_str = f"{minute}+{extra}'" if extra else f"{minute}'"

        team = home_name if g["participant_id"] == home_id else away_name
        scorer = g.get("player_name", "Unknown")
        assister = g.get("related_player_name")
        body_part = g.get("info", "")

        assist_str = f" (assist: {assister})" if assister else ""
        body_str = f" [{body_part}]" if body_part else ""

        lines.append(f"  {minute_str} {team} — {scorer}{assist_str}{body_str}")

    return "\n".join(lines)


# ─── Pressure helpers ─────────────────────────────────────────────────────────

def _compute_pressure_bands(pressure: list[dict], participant_id: int) -> dict[str, float]:
    team_pressure = [p for p in pressure if p["participant_id"] == participant_id]

    bands = {"1-30": [], "31-60": [], "61-90": []}
    for p in team_pressure:
        minute = p["minute"]
        val = p["pressure"]
        if 1 <= minute <= 30:
            bands["1-30"].append(val)
        elif 31 <= minute <= 60:
            bands["31-60"].append(val)
        elif 61 <= minute <= 90:
            bands["61-90"].append(val)

    result = {}
    all_vals = []
    for band_name, vals in bands.items():
        avg = round(sum(vals) / len(vals), 1) if vals else 0.0
        result[band_name] = avg
        all_vals.extend(vals)

    result["overall"] = round(sum(all_vals) / len(all_vals), 1) if all_vals else 0.0
    return result


def _pressure_narrative(home_bands: dict, away_bands: dict, home_name: str, away_name: str) -> str:
    h_overall = home_bands["overall"]
    a_overall = away_bands["overall"]

    if h_overall > a_overall * 1.5:
        return f"→ {home_name} dominated possession pressure throughout"
    elif a_overall > h_overall * 1.5:
        return f"→ {away_name} dominated possession pressure throughout"
    elif h_overall > a_overall:
        return f"→ {home_name} had slightly more pressure overall"
    elif a_overall > h_overall:
        return f"→ {away_name} had slightly more pressure overall"
    else:
        return "→ Pressure was evenly shared"


def _format_pressing(pressure: list[dict], home_id: int, away_id: int, home_name: str, away_name: str) -> str:
    home_bands = _compute_pressure_bands(pressure, home_id)
    away_bands = _compute_pressure_bands(pressure, away_id)
    narrative = _pressure_narrative(home_bands, away_bands, home_name, away_name)

    max_len = max(len(home_name), len(away_name))

    lines = [
        "**PRESSING (avg pressure 0-100 scale)**",
        f"{'':>14}  1-30min   31-60min  61-90min  overall",
        f"  {home_name:<{max_len}}   {home_bands['1-30']:>6.1f}    {home_bands['31-60']:>6.1f}    {home_bands['61-90']:>6.1f}    {home_bands['overall']:>6.1f}",
        f"  {away_name:<{max_len}}   {away_bands['1-30']:>6.1f}    {away_bands['31-60']:>6.1f}    {away_bands['61-90']:>6.1f}    {away_bands['overall']:>6.1f}",
        f"  {narrative}",
    ]
    return "\n".join(lines)


# ─── Key stats table ──────────────────────────────────────────────────────────

def _format_stats_table(statistics: list[dict], home_id: int, away_id: int, home_name: str, away_name: str) -> str:
    lines = [
        "**KEY STATS**",
        f"{'':>22} {home_name:>8}  {away_name:>8}",
    ]

    for type_id, label in TACTICS_STATS:
        h_val = get_stat_value(statistics, type_id, home_id)
        a_val = get_stat_value(statistics, type_id, away_id)
        h_str = str(h_val) if h_val is not None else "-"
        a_str = str(a_val) if a_val is not None else "-"
        lines.append(f"  {label:<20} {h_str:>8}  {a_str:>8}")

    return "\n".join(lines)


# ─── Formation helper ─────────────────────────────────────────────────────────

def _get_formation(formations: list[dict], participant_id: int) -> str:
    for f in formations:
        if f["participant_id"] == participant_id:
            return f["formation"]
    return "Unknown"


# ─── Participant helpers ──────────────────────────────────────────────────────

def _get_participants(fixture: dict) -> tuple[dict | None, dict | None]:
    participants = fixture.get("participants", [])
    home = next((p for p in participants if p["meta"]["location"] == "home"), None)
    away = next((p for p in participants if p["meta"]["location"] == "away"), None)
    return home, away


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: Long format (most recent match)
# ═══════════════════════════════════════════════════════════════════════════════

def format_match_long(fixture: dict, team_id: int) -> str:
    """
    Full detail format for the most recent previous match.
    Includes goals, pressing bands, and full stat table.
    """
    home, away = _get_participants(fixture)
    if not home or not away:
        return f"Could not parse participants for fixture {fixture.get('id')}"

    home_id = home["id"]
    away_id = away["id"]
    home_name = home["name"]
    away_name = away["name"]

    is_home = team_id == home_id
    opponent = away_name if is_home else home_name
    location = "H" if is_home else "A"

    starting_at = fixture.get("starting_at", "Unknown date")
    details = fixture.get("details", "")

    formation = _get_formation(fixture.get("formations", []), team_id)
    result_line = _get_result_line(fixture, home_id, away_id)
    goals_text = _format_goals(fixture.get("events", []), home_id, away_id, home_name, away_name)
    pressing_text = _format_pressing(fixture.get("pressure", []), home_id, away_id, home_name, away_name)
    stats_text = _format_stats_table(fixture.get("statistics", []), home_id, away_id, home_name, away_name)

    lines = [
        f"#### vs {opponent} ({location}) | {details} | {starting_at}",
        "",
        f"Result: {result_line}",
        f"Formation: {formation}",
        "",
        "**GOALS**",
        goals_text,
        "",
        pressing_text,
        "",
        stats_text,
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: Short format (per-match condensed entry)
# ═══════════════════════════════════════════════════════════════════════════════

def format_match_short(fixture: dict, team_id: int) -> str:
    """
    Condensed per-match entry for older matches.
    Shows opponent, result, formation, and key stats in a compact block.
    """
    home, away = _get_participants(fixture)
    if not home or not away:
        return f"Could not parse participants for fixture {fixture.get('id')}"

    home_id = home["id"]
    away_id = away["id"]
    home_name = home["name"]
    away_name = away["name"]

    is_home = team_id == home_id
    opponent = away_name if is_home else home_name
    opp_id = away_id if is_home else home_id
    location = "H" if is_home else "A"

    scores = fixture.get("scores", [])
    team_goals = _extract_score(scores, team_id, "CURRENT")
    opp_goals = _extract_score(scores, opp_id, "CURRENT")
    ht_team = _extract_score(scores, team_id, "1ST_HALF")
    ht_opp = _extract_score(scores, opp_id, "1ST_HALF")
    result_tag = _get_result_tag(team_goals, opp_goals)

    starting_at = fixture.get("starting_at", "Unknown date")
    details = fixture.get("details", "")
    formation = _get_formation(fixture.get("formations", []), team_id)

    statistics = fixture.get("statistics", [])
    poss = get_stat_value(statistics, 45, team_id)
    shots = get_stat_value(statistics, 42, team_id)
    sot = get_stat_value(statistics, 86, team_id)

    pressure = fixture.get("pressure", [])
    bands = _compute_pressure_bands(pressure, team_id)
    press_val = bands["overall"]

    poss_str = f"{poss}%" if poss is not None else "-"
    shots_str = str(shots) if shots is not None else "-"
    sot_str = str(sot) if sot is not None else "-"

    lines = [
        f"#### vs {opponent} ({location}) | {details} | {starting_at}",
        f"Result: {result_tag} {team_goals}-{opp_goals} (HT: {ht_team}-{ht_opp}) | Formation: {formation}",
        f"Possession: {poss_str} | Shots: {shots_str} (on target: {sot_str}) | Pressing: {press_val}",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: Form summary (aggregated averages)
# ═══════════════════════════════════════════════════════════════════════════════

def format_form_summary(fixtures: list[dict], team_id: int, team_name: str) -> str:
    """
    Aggregated summary across all previous matches.
    Appended after the individual match entries.
    """
    if not fixtures:
        return f"#### {team_name} — WC 2026 FORM SUMMARY (0 matches)\nNo previous matches."

    wins, draws, losses = 0, 0, 0
    goals_for, goals_against = 0, 0
    first_half_goals, second_half_goals = 0, 0
    formations_used: list[str] = []

    possession_vals: list[float] = []
    shots_total_vals: list[float] = []
    shots_on_target_vals: list[float] = []
    pressing_vals: list[float] = []
    sub_minutes: list[int] = []

    for fixture in fixtures:
        home, away = _get_participants(fixture)
        if not home or not away:
            continue

        home_id = home["id"]
        away_id = away["id"]
        is_home = team_id == home_id
        opp_id = away_id if is_home else home_id

        scores = fixture.get("scores", [])
        team_goals = _extract_score(scores, team_id, "CURRENT")
        opp_goals = _extract_score(scores, opp_id, "CURRENT")
        goals_for += team_goals
        goals_against += opp_goals

        if team_goals > opp_goals:
            wins += 1
        elif team_goals == opp_goals:
            draws += 1
        else:
            losses += 1

        first_half_goals += _extract_score(scores, team_id, "1ST_HALF")
        second_half_goals += _extract_score(scores, team_id, "2ND_HALF_ONLY")

        formation = _get_formation(fixture.get("formations", []), team_id)
        if formation != "Unknown" and formation not in formations_used:
            formations_used.append(formation)

        statistics = fixture.get("statistics", [])
        poss = get_stat_value(statistics, 45, team_id)
        if poss is not None:
            possession_vals.append(poss)

        shots = get_stat_value(statistics, 42, team_id)
        if shots is not None:
            shots_total_vals.append(shots)

        sot = get_stat_value(statistics, 86, team_id)
        if sot is not None:
            shots_on_target_vals.append(sot)

        pressure = fixture.get("pressure", [])
        bands = _compute_pressure_bands(pressure, team_id)
        if bands["overall"] > 0:
            pressing_vals.append(bands["overall"])

        events = fixture.get("events", [])
        first_sub = None
        for e in sorted(events, key=lambda x: x["minute"]):
            if e["type_id"] == 18 and e["participant_id"] == team_id:
                first_sub = e["minute"]
                break
        if first_sub is not None:
            sub_minutes.append(first_sub)

    n = len(fixtures)

    def avg(vals: list) -> float:
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    avg_possession = avg(possession_vals)
    avg_shots = avg(shots_total_vals)
    avg_sot = avg(shots_on_target_vals)
    avg_pressing = avg(pressing_vals)

    if avg_pressing >= 40:
        press_label = "HIGH"
    elif avg_pressing >= 20:
        press_label = "MED"
    else:
        press_label = "LOW"

    total_scored = first_half_goals + second_half_goals
    if total_scored > 0:
        fh_pct = round(first_half_goals / total_scored * 100)
        sh_pct = 100 - fh_pct
    else:
        fh_pct, sh_pct = 0, 0

    if sub_minutes:
        avg_first_sub = round(sum(sub_minutes) / len(sub_minutes))
        sub_pattern = f"First sub avg at {avg_first_sub}'"
    else:
        sub_pattern = "No data"

    lines = [
        f"#### {team_name} — WC 2026 FORM SUMMARY ({n} matches)",
        f"Formations used: {', '.join(formations_used) if formations_used else 'Unknown'}",
        f"Record: W{wins} D{draws} L{losses} | GF: {goals_for} | GA: {goals_against}",
        f"Avg possession: {avg_possession}%",
        f"Avg shots total: {avg_shots}",
        f"Avg shots on target: {avg_sot}",
        f"Avg pressing intensity: {avg_pressing} ({press_label})",
        f"Goals scored: {fh_pct}% first half, {sh_pct}% second half",
        f"Substitution pattern: {sub_pattern}",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC: Team section (orchestrator)
# ═══════════════════════════════════════════════════════════════════════════════

def format_team_section(
    fixtures: list[dict],
    team_id: int,
    team_name: str,
) -> str:
    """
    Build the full past-performances block for one team.

    Expects fixtures sorted chronologically (oldest first).
    The LAST fixture gets the long format, all earlier ones get short format.
    The form summary aggregates ALL fixtures.

    Example output for Paraguay at RO16:

        ### Paraguay Past Performances
        #### vs Germany (A) | Match 74 | 2026-06-29 20:30:00    <-- long (most recent)
        ...full detail...

        #### vs Australia (A) | Match 60 | 2026-06-26 02:00:00  <-- short
        Result: D 0-0 (HT: 0-0) | Formation: ...
        Possession: ... | Shots: ... | Pressing: ...

        #### vs Turkiye (A) | Match 31 | 2026-06-20 03:00:00    <-- short
        Result: W 1-0 (HT: 1-0) | Formation: ...
        ...

        #### vs USA (A) | Match 4 | 2026-06-13 01:00:00         <-- short
        Result: L 1-4 (HT: 0-3) | Formation: ...
        ...

        #### Paraguay — WC 2026 FORM SUMMARY (4 matches)        <-- aggregate
        ...
    """
    if not fixtures:
        return f"### {team_name} Past Performances\n\nNo previous matches found."

    # Most recent match = last in chronological order
    most_recent = fixtures[-1]
    older = fixtures[:-1]

    sections = [f"### {team_name} Past Performances\n"]

    # Long format for most recent
    sections.append(format_match_long(most_recent, team_id))

    # Short format for each older match (most recent first)
    for fix in reversed(older):
        sections.append("")
        sections.append(format_match_short(fix, team_id))

    # Aggregate summary across ALL matches
    sections.append("")
    sections.append(format_form_summary(fixtures, team_id, team_name))

    return "\n".join(sections)