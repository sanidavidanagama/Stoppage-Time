# tools/h2h_tool.py
from langchain_core.tools import tool
from service.h2h import get_h2h


@tool
def get_head_to_head(home_team: str, away_team: str) -> str:
    """
    Get continent-level historical World Cup trend between two teams' regions
    (e.g. South America vs Europe). Use this for broad historical context on
    how teams from these continents have performed against each other at
    World Cups — not a direct match-up record between these specific teams.
    """
    return get_h2h(home_team, away_team)