# tools/tactics_tool.py
from langchain_core.tools import tool
from agents.tactics_agent import tactics_analyse
from service.telemetry import record_tool_call
from service.context import get_session_id, get_bet_id


@tool
def consult_tactics(home_team: str, away_team: str, round_info: str, focus_question: str = "") -> dict:
    """Get tactical analysis: formation clashes, key matchups, style dynamics.
    Provide a focus_question for a specific angle, or leave empty for a general overview."""
    session_id, bet_id = get_session_id(), get_bet_id()
    result = tactics_analyse(home_team=home_team, away_team=away_team, round_info=round_info,
                              focus_question=focus_question or None, session_id=session_id, bet_id=bet_id)
    if session_id:
        record_tool_call(session_id, bet_id, "consult_tactics",
                          {"home_team": home_team, "away_team": away_team, "focus_question": focus_question},
                          result.get("summary") or result.get("error") or str(result)[:200],
                          result.get("available", False))
    return result