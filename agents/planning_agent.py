# agents/planning_agent.py
"""
agents/planning_agent.py

Deterministic pre-match context gathering. No LLM — the set of general
tools worth calling for any fixture barely varies, so this just runs a
fixed plan every time. Crucially, this means it can never generate a
focus_question for Tactics (a real risk if an LLM were writing one
speculatively, before any real data exists to ground it in).
"""

from agents.tactics import tactics_analyse
from agents.news_agent import get_news
from service.h2h import get_h2h
from service.stair_ledger import planning as ledger_planning, tool_calling as ledger_tool_calling, submit_records
from service.db import log_step


def run_planning(
    home_team: str,
    away_team: str,
    round_info: str,
    session_id: str,
    bet_id: str | None = None,
) -> str:
    """
    Gather general pre-match context. Returns a single text block ready to
    inject into the Reasoning Agent's prompt as pre-loaded context.
    """
    goal = f"Gather general pre-match context for {home_team} vs {away_team}"
    steps = [
        "Get general tactical analysis (no focus question — nothing specific to ask yet)",
        "Get current injury/squad news",
        "Get continent-level historical trend",
    ]

    try:
        log_step(session_id=session_id, step_type="Planning", tool="planning", bet_id=bet_id, response=f"{goal}: {steps}")
    except Exception as e:
        print(f"[planning] Supabase log failed (non-fatal): {e}")
    try:
        submit_records(ledger_planning(session_id, goal, steps))
    except Exception as e:
        print(f"[planning] Ledger submit failed (non-fatal): {e}")

    # Step 1: general tactics (no focus_question — deliberately)
    tactics_result = tactics_analyse(
        home_team=home_team, away_team=away_team, round_info=round_info,
        session_id=session_id, bet_id=bet_id,
    )
    _log_tool_call(session_id, bet_id, "consult_tactics",
                    {"home_team": home_team, "away_team": away_team}, tactics_result)

    # Step 2: injury news
    news_result = get_news(
        home_team=home_team, away_team=away_team, angle="injuries",
        session_id=session_id, bet_id=bet_id,
    )
    _log_tool_call(session_id, bet_id, "get_fixture_news",
                    {"angle": "injuries"}, news_result)

    # Step 3: continent trend (no LLM involved, so log the call directly)
    h2h_text = get_h2h(home_team, away_team)
    _log_tool_call(session_id, bet_id, "get_h2h", {}, {"answer": h2h_text})

    # Assemble into one context block for Reasoning's prompt
    parts = ["## Pre-gathered context (from Planning Agent)\n"]

    if tactics_result.get("available"):
        parts.append(f"**General tactical read:**\n{tactics_result.get('summary', tactics_result)}")
    else:
        parts.append(f"**Tactical analysis unavailable:** {tactics_result.get('error')}")

    if news_result.get("available"):
        parts.append(f"\n**Injury/squad news:**\n{news_result.get('answer')}")
    else:
        parts.append(f"\n**News unavailable:** {news_result.get('error')}")

    parts.append(f"\n**Continent trend:**\n{h2h_text}")

    return "\n".join(parts)


def _log_tool_call(session_id: str, bet_id: str | None, tool_name: str, params: dict, result: dict) -> None:
    summary = result.get("answer") or result.get("summary") or str(result)[:200]
    try:
        log_step(session_id=session_id, step_type="ToolCalling", tool=tool_name, bet_id=bet_id, prompt=str(params), response=summary)
    except Exception as e:
        print(f"[planning] Supabase ToolCalling log failed (non-fatal): {e}")
    try:
        submit_records(ledger_tool_calling(session_id, None, tool_name, params, summary, success=result.get("available", True)))
    except Exception as e:
        print(f"[planning] Ledger ToolCalling submit failed (non-fatal): {e}")