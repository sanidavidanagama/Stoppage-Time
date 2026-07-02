# agents/tactics_agent.py
import json
import re
from langchain_anthropic import ChatAnthropic

from config.settings import settings
from service.schedule import find_fixture_by_teams
from service.prompt_builder import build_tactics_prompt

_model = ChatAnthropic(
    model=settings.ANTHROPIC_MODEL,
    max_tokens=settings.ANTHROPIC_MAX_TOKENS,
    thinking={"type": "enabled", "budget_tokens": settings.ANTHROPIC_THINKING_BUDGET},
)


def _extract(response) -> tuple[str, str]:
    """Split a LangChain AIMessage into (thinking_text, final_text)."""
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
) -> dict:
    """
    Run tactical analysis for a fixture, resolved by team names.

    round_info is required (not auto-detected from Sportmonks yet — the
    caller, e.g. the Planning Agent, already knows what round it's asking
    about, so pass it in explicitly for now).
    """
    fixture = find_fixture_by_teams(home_team, away_team)
    if fixture is None:
        return {
            "available": False,
            "error": f"No fixture found for {home_team} vs {away_team} in {round_info}",
        }

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