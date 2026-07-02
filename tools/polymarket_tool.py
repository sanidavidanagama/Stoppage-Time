# tools/polymarket_tool.py
from langchain_core.tools import tool
from service.polymarket import get_polymarket_prices


@tool
def get_market_odds(home_team: str, away_team: str) -> str:
    """
    Get current Polymarket implied win probabilities for a World Cup fixture —
    the live market's view of home/draw/away chances. Use this to compare
    against your own probability estimate to find betting edge.
    """
    return get_polymarket_prices(home_team, away_team)