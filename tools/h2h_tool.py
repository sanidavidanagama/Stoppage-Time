# tools/h2h_tool.py
from langchain_core.tools import tool
from service.h2h import get_h2h
from service.telemetry import record_tool_call
from service.context import get_session_id, get_bet_id


@tool
def get_head_to_head(home_team: str, away_team: str) -> str:
    """Continent-level historical World Cup trend between two teams' regions."""
    session_id, bet_id = get_session_id(), get_bet_id()
    result = get_h2h(home_team, away_team)
    if session_id:
        record_tool_call(session_id, bet_id, "get_head_to_head", {"home_team": home_team, "away_team": away_team}, result[:200])
    return result