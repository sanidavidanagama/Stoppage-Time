# tools/search_tool.py
from langchain_core.tools import tool
from agents.search_agent import web_search
from service.telemetry import record_tool_call
from service.context import get_session_id, get_bet_id


@tool
def search_web(query: str) -> dict:
    """
    Search the web for current, factual information — squad news, injuries,
    suspensions, team-selection reports, weather, or any other real-time
    context not available from Sportmonks or historical data. Returns a
    grounded answer with real source URLs, not a guess.
    """
    session_id, bet_id = get_session_id(), get_bet_id()
    result = web_search(query, session_id=session_id, bet_id=bet_id)
    if session_id:
        record_tool_call(
            session_id, bet_id, "search_web", {"query": query},
            result.get("answer", "")[:200] or result.get("error", ""),
            result.get("available", False),
        )
    return result