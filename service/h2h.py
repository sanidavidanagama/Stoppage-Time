# service/h2h.py
"""
service/h2h.py

Continent-level head-to-head trend from Supabase StatsBomb priors.

Country-level H2H (ads_a_h2h_country) was evaluated and dropped — spot
checks (e.g. Argentina vs Germany) showed it missing known major-tournament
meetings (1990, 2006, 2010, 2014), making it unreliable enough to risk
misleading the Reasoning Agent rather than just being a small sample.
"""

import requests
from config.settings import settings
from config.teams import TEAM_CONTINENT


def get_h2h(home_name: str, away_name: str) -> str:
    """
    Get continent-level head-to-head trend for two countries.
    """
    home_cont = TEAM_CONTINENT.get(home_name)
    away_cont = TEAM_CONTINENT.get(away_name)

    if not home_cont or not away_cont:
        return f"No continent data available — unknown continent for {home_name if not home_cont else away_name}."

    if home_cont == away_cont:
        return f"No continent-level H2H applicable — both {home_name} and {away_name} are from {home_cont}."

    home_row = _fetch_continent_h2h(home_cont, away_cont)
    away_row = _fetch_continent_h2h(away_cont, home_cont)

    if not (home_row or away_row):
        return f"No continent-level H2H data found for {home_cont} vs {away_cont}."

    return _summarize_continent(home_row, away_row, home_cont, away_cont)


def _fetch_continent_h2h(cont_a: str, cont_b: str) -> dict | None:
    r = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/ads_a_h2h_continent",
        params={"continent_a": f"eq.{cont_a}", "continent_b": f"eq.{cont_b}", "select": "*"},
        headers=settings.H_WCA,
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _summarize_continent(home_row: dict | None, away_row: dict | None, cont_a: str, cont_b: str) -> str:
    row = home_row or away_row

    if home_row:
        a_wins, b_wins, draws = home_row["wins_a"], home_row["losses_a"], home_row["draws"]
    else:
        b_wins, a_wins, draws = away_row["wins_a"], away_row["losses_a"], away_row["draws"]

    total = row["total_matches"]

    return (
        f"Continent trend - {cont_a} vs {cont_b} ({total} World Cup matches):\n"
        f"{cont_a} wins - {a_wins}, {cont_b} wins - {b_wins}, Draws - {draws}"
    )