# tools/polymarket_tool.py
from langchain_core.tools import tool
from service.polymarket import get_polymarket_prices
from service.telemetry import record_tool_call
from service.context import get_session_id, get_bet_id


@tool
def get_market_odds(home_team: str, away_team: str) -> str:
    """
    Get current Polymarket implied win probabilities for a World Cup fixture —
    the live market's view of home/draw/away chances. Use this to compare
    against your own probability estimate to find betting edge.
    """
    session_id, bet_id = get_session_id(), get_bet_id()
    result = get_polymarket_prices(home_team, away_team)
    if session_id:
        record_tool_call(
            session_id, bet_id, "get_market_odds",
            {"home_team": home_team, "away_team": away_team},
            result[:200],
        )
    return result