"""
Sportmonks Football API v3 — Statistics type_id mappings.

Source: https://docs.sportmonks.com/v3/definitions/types/statistics
Last verified: 2026-06-29
"""

STAT_TYPES: dict[int, str] = {
    42: "shots_total",
    41: "shots_off_target",
    86: "shots_on_target",
    49: "shots_inside_box",
    50: "shots_outside_box",
    58: "shots_blocked",
    54: "goal_attempts",
    52: "goals",
    64: "hit_woodwork",
    45: "ball_possession",
    80: "passes",
    81: "successful_passes",
    82: "successful_passes_pct",
    62: "long_passes",
    27264: "successful_long_passes",
    27265: "successful_long_passes_pct",
    117: "key_passes",
    98: "total_crosses",
    99: "accurate_crosses",
    78: "tackles",
    100: "interceptions",
    106: "duels_won",
    65: "successful_headers",
    57: "saves",
    34: "corners",
    55: "free_kicks",
    56: "fouls",
    84: "yellow_cards",
    83: "red_cards",
    51: "offsides",
    47: "penalties",
    43: "attacks",
    44: "dangerous_attacks",
    1527: "counter_attacks",
    46: "ball_safe",
    53: "goal_kicks",
    60: "throw_ins",
    59: "substitutions",
    79: "assists",
    108: "dribble_attempts",
    109: "successful_dribbles",
    1605: "accurate_passes_pct_extended",
    580: "unknown_580",
    581: "unknown_581",
}

STAT_IDS: dict[str, int] = {v: k for k, v in STAT_TYPES.items()}

TACTICS_STATS: list[tuple[int, str]] = [
    (45, "Possession"),
    (42, "Shots total"),
    (86, "Shots on target"),
    (49, "Shots inside box"),
    (58, "Shots blocked"),
    (82, "Pass accuracy %"),
    (98, "Total crosses"),
    (99, "Accurate crosses"),
    (78, "Tackles"),
    (106, "Duels won"),
    (27265, "Long ball acc. %"),
    (34, "Corners"),
    (56, "Fouls"),
]


def get_stat_name(type_id: int) -> str:
    return STAT_TYPES.get(type_id, f"unknown_{type_id}")


def get_stat_value(
    statistics: list[dict],
    type_id: int,
    participant_id: int,
) -> int | float | None:
    for stat in statistics:
        if stat["type_id"] == type_id and stat["participant_id"] == participant_id:
            return stat["data"]["value"]
    return None


def extract_team_stats(
    statistics: list[dict],
    participant_id: int,
) -> dict[str, int | float | None]:
    result = {}
    for type_id, name in STAT_TYPES.items():
        result[name] = get_stat_value(statistics, type_id, participant_id)
    return result