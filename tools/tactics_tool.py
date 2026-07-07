# tools/tactics_tool.py
from langchain_core.tools import tool
from agents.tactics_agent import tactics_analyse
from service.telemetry import record_tool_call


def make_consult_tactics_tool(session_id: str, bet_id: str | None = None):
    """
    Factory — returns a consult_tactics tool with session_id/bet_id baked
    in via closure, so the LLM never sees or has to supply them.
    """

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
        result = tactics_analyse(
            home_team=home_team,
            away_team=away_team,
            round_info=round_info,
            focus_question=focus_question or None,
            session_id=session_id,
            bet_id=bet_id,
        )

        record_tool_call(
            session_id=session_id,
            bet_id=bet_id,
            tool_name="consult_tactics",
            params={"home_team": home_team, "away_team": away_team, "focus_question": focus_question},
            result_summary=result.get("summary") or result.get("error") or str(result)[:200],
            success=result.get("available", False),
        )

        return result

    return consult_tactics