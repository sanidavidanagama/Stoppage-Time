# tools/news_tool.py
from langchain_core.tools import tool
from agents.news_agent import get_news
from service.telemetry import record_tool_call
from service.context import get_session_id, get_bet_id


@tool
def get_fixture_news(home_team: str, away_team: str, angle: str) -> dict:
    """
    Get fixture-specific, date-anchored news. angle must be one of:
    "injuries" (fitness/suspensions), "atmosphere" (crowd/conditions),
    "pundits" (expert predictions), "sentiment" (fan mood/controversy),
    or "wildcard" (offbeat storylines — for color, not serious signal).
    Choose a different angle each call rather than repeating one.
    """
    session_id, bet_id = get_session_id(), get_bet_id()
    result = get_news(home_team, away_team, angle, session_id=session_id, bet_id=bet_id)
    if session_id:
        record_tool_call(
            session_id, bet_id, "get_fixture_news", {"angle": angle},
            result.get("answer", "")[:200] or result.get("error", ""),
            result.get("available", False),
        )
    return result