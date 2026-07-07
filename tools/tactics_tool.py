# tools/tactics_tool.py
from langchain_core.tools import tool
from agents.tactics_agent import tactics_analyse


@tool
def consult_tactics(
    home_team: str,
    away_team: str,
    round_info: str,
    focus_question: str = "",
) -> dict:
    """
    Get tactical analysis for a World Cup fixture: formation clashes, key
    matchups, and style dynamics. Provide a focus_question to ask about a
    specific tactical angle (e.g. an injury's effect on scoring chances) —
    leave it empty for a general overview.
    """
    return tactics_analyse(
        home_team=home_team,
        away_team=away_team,
        round_info=round_info,
        focus_question=focus_question or None,
    )