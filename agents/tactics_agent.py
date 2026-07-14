# agents/tactics.py
import json
import re
from langchain_anthropic import ChatAnthropic

from config.settings import settings
from service.schedule import find_fixture_by_teams
from service.prompt_builder import build_tactics_prompt
from service.telemetry import record_thinking
from service.db import update_session_status

_model = ChatAnthropic(
    model=settings.ANTHROPIC_MODEL,
    max_tokens=settings.ANTHROPIC_MAX_TOKENS,
    thinking={"type": "enabled", "budget_tokens": settings.ANTHROPIC_THINKING_BUDGET},
)


def _extract(response) -> tuple[str, str]:
    if isinstance(response.content, str):
        return "", response.content
    thinking_parts, text_parts = [], []
    for block in response.content:
        if isinstance(block, dict):
            if block.get("type") == "thinking":
                thinking_parts.append(block.get("thinking", ""))
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))
    return "\n\n".join(thinking_parts), "\n\n".join(text_parts)


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def tactics_analyse(
    home_team: str,
    away_team: str,
    round_info: str,
    stadium: str = "Unknown venue",
    weather: str = "Unknown conditions",
    focus_question: str | None = None,
    session_id: str | None = None,
    bet_id: str | None = None,
    kickoff_hint: int | str | None = None,
) -> dict:
    fixture = find_fixture_by_teams(home_team, away_team, kickoff_hint=kickoff_hint)
    if fixture is None:
        return {
            "available": False,
            "error": f"No fixture found for {home_team} vs {away_team}",
        }

    if session_id:
        update_session_status(session_id, "tactical analysis")

    prompt = build_tactics_prompt(
        fixture_id=fixture["fixture_id"],
        round_info=round_info,
        stadium=stadium,
        weather=weather,
    )

    if focus_question:
        prompt += f"\n\n---\n\nThe Reasoning Agent specifically wants to know: {focus_question}"

    response = _model.invoke(prompt)
    thinking, final_text = _extract(response)

    if session_id:
        record_thinking(
            session_id=session_id,
            bet_id=bet_id,
            tool="tactics",
            model=settings.ANTHROPIC_MODEL,
            prompt=prompt,
            response=final_text,
            internal_reasoning=thinking,
        )

    result = _parse_json(final_text)
    if result is None:
        return {
            "available": False,
            "error": "unparseable_response",
            "raw": final_text,
        }

    result["available"] = True
    result["internal_reasoning"] = thinking
    result["fixture_id"] = fixture["fixture_id"]
    return result