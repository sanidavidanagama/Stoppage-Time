# agents/reflecting_agent.py
"""
agents/reflecting_agent.py

Reviews one settled bet and decides whether to update the shared
personality note that Reasoning and Betting read before future decisions.
"""

import json
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from config.settings import settings
from service.db import (
    get_bet_by_id, get_logs_for_bet,
    get_current_personality, save_personality_update, log_step,
)

_RULES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reflecting_rules.md"


def _load_rules() -> str:
    return _RULES_PATH.read_text(encoding="utf-8")


def _model():
    return ChatAnthropic(
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


def run_reflection(bet_id: str) -> dict:
    """
    Review one settled bet, decide whether to update the personality note.
    Requires the bet to already have actual_outcome/pnl filled in.
    """
    bet = get_bet_by_id(bet_id)
    if bet is None:
        return {"available": False, "error": "bet_not_found"}
    if bet.get("actual_outcome") is None:
        return {"available": False, "error": "bet_not_settled_yet"}

    logs = get_logs_for_bet(bet_id)
    reasoning_trace = "\n\n".join(
        f"[{l['step_type']} / {l['tool']}]\n{l.get('response', '')}"
        for l in logs
    )

    current_personality = get_current_personality()

    result_line = "WON" if (bet.get("pnl") or 0) > 0 else "LOST" if bet.get("decision") != "skip" else "SKIPPED"

    prompt = f"""{_load_rules()}

## Current personality note

{current_personality}

## The bet being reviewed

Fixture: {bet['home_team']} vs {bet['away_team']}
Predicted: home {bet['home_probability']:.0%} / draw {bet['draw_probability']:.0%} / away {bet['away_probability']:.0%} (confidence: {bet['confidence']})
Market at decision time: home {bet['market_home_price']:.0%} / draw {bet['market_draw_price']:.0%} / away {bet['market_away_price']:.0%}
Edge detected: {bet['edge_pp']}pp
Decision: {bet['decision']}, stake ${bet.get('stake_usd') or 0}
Bet reasoning at the time: {bet['bet_reason']}

Actual outcome: {bet['actual_outcome']} — result: {result_line}
P&L: {bet.get('pnl')}

## Reasoning trace from this decision cycle

{reasoning_trace}
"""

    model = _model()
    response = model.invoke([HumanMessage(prompt)])
    thinking, final_text = _extract(response)

    log_step(
        session_id=bet["session_id"],
        step_type="Reflecting",
        tool="reflecting",
        bet_id=bet_id,
        model=settings.ANTHROPIC_MODEL,
        prompt=prompt,
        response=final_text,
    )

    result = _parse_json(final_text)
    if result is None:
        return {"available": False, "error": "unparseable_response", "raw": final_text}

    if result.get("should_update") and result.get("new_personality"):
        save_personality_update(bet_id, bet["session_id"], result["new_personality"])

    return {
        "available": True,
        "should_update": result.get("should_update", False),
        "new_personality": result.get("new_personality"),
        "reasoning": result.get("reasoning"),
    }