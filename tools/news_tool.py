# tools/news_tool.py
from langchain_core.tools import tool
from agents.news_agent import get_news


@tool
def get_fixture_news(home_team: str, away_team: str, angle: str) -> dict:
    """
    Get fixture-specific, date-anchored news. angle must be one of:
    "injuries" (fitness/suspensions), "atmosphere" (crowd/conditions),
    "pundits" (expert predictions), "sentiment" (fan mood/controversy),
    or "wildcard" (offbeat storylines — for color, not serious signal).
    Choose a different angle each call rather than repeating one.
    """
    return get_news(home_team, away_team, angle)