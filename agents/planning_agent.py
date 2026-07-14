# agents/planning_agent.py
from agents.tactics_agent import tactics_analyse
from agents.news_agent import get_news
from service.h2h import get_h2h
from service.stair_ai_ledger import planning as ledger_planning, tool_calling as ledger_tool_calling, submit_records
from service.db import log_step, update_session_status


def run_planning(home_team: str, away_team: str, round_info: str, session_id: str, bet_id: str | None = None,
                  kickoff_hint: int | str | None = None) -> str:
    update_session_status(session_id, "planning")

    goal = f"Gather pre-match context and evaluate a betting decision for {home_team} vs {away_team}"

    # Full intended plan, documented for the ledger — reasoning/betting steps
    # execute later, in their own agents, not here.
    steps = [
        "Get general tactical analysis (no focus question)",
        "Get current injury/squad news",
        "Get pundit predictions",
        "Get atmosphere/crowd context",
        "Get continent-level historical trend",
        "Form independent probability estimate (Reasoning Agent)",
        "Scan edge across all three outcomes and decide stake (Betting Agent)",
        "Place order if confirmed and edge exists",
    ]

    try:
        log_step(session_id=session_id, step_type="Planning", tool="planning", response=f"{goal}: {steps}")
    except Exception as e:
        print(f"[planning] Supabase log failed (non-fatal): {e}")
    try:
        submit_records(ledger_planning(session_id, goal, steps))
    except Exception as e:
        print(f"[planning] Ledger submit failed (non-fatal): {e}")

    tactics_result = tactics_analyse(home_team=home_team, away_team=away_team, round_info=round_info,
                                      session_id=session_id, bet_id=bet_id, kickoff_hint=kickoff_hint)
    _log_tool_call(session_id, bet_id, "consult_tactics", {"home_team": home_team, "away_team": away_team}, tactics_result)

    injuries = get_news(home_team, away_team, "injuries", session_id=session_id, bet_id=bet_id)
    _log_tool_call(session_id, bet_id, "get_fixture_news", {"angle": "injuries"}, injuries)

    pundits = get_news(home_team, away_team, "pundits", session_id=session_id, bet_id=bet_id)
    _log_tool_call(session_id, bet_id, "get_fixture_news", {"angle": "pundits"}, pundits)

    atmosphere = get_news(home_team, away_team, "atmosphere", session_id=session_id, bet_id=bet_id)
    _log_tool_call(session_id, bet_id, "get_fixture_news", {"angle": "atmosphere"}, atmosphere)

    h2h_text = get_h2h(home_team, away_team)
    _log_tool_call(session_id, bet_id, "get_h2h", {}, {"answer": h2h_text})

    parts = ["## Pre-gathered context (from Planning Agent)\n"]
    parts.append(f"**General tactical read:**\n{_format_tactics_summary(tactics_result)}")
    parts.append(f"\n**Injury/squad news:**\n{injuries.get('answer', injuries.get('error'))}")
    parts.append(f"\n**Pundit predictions:**\n{pundits.get('answer', pundits.get('error'))}")
    parts.append(f"\n**Atmosphere:**\n{atmosphere.get('answer', atmosphere.get('error'))}")
    parts.append(f"\n**Continent trend:**\n{h2h_text}")

    return "\n".join(parts)


def _log_tool_call(session_id, bet_id, tool_name, params, result):
    summary = result.get("answer") or result.get("summary") or str(result)[:200]
    try:
        log_step(session_id=session_id, step_type="ToolCalling", tool=tool_name, prompt=str(params), response=summary)
    except Exception as e:
        print(f"[planning] Supabase log failed (non-fatal): {e}")
    try:
        submit_records(ledger_tool_calling(session_id, None, tool_name, params, summary, success=result.get("available", True)))
    except Exception as e:
        print(f"[planning] Ledger submit failed (non-fatal): {e}")

def _format_tactics_summary(t: dict) -> str:
    if not t.get("available"):
        return f"Tactical analysis unavailable: {t.get('error', 'unknown error')}"
    return (
        f"Home advantages: {t.get('home_advantages', 'N/A')}\n"
        f"Home vulnerabilities: {t.get('home_vulnerabilities', 'N/A')}\n"
        f"Away advantages: {t.get('away_advantages', 'N/A')}\n"
        f"Away vulnerabilities: {t.get('away_vulnerabilities', 'N/A')}\n"
        f"Style clash: {t.get('style_clash', 'N/A')}\n"
        f"Extra time/penalties likelihood: {t.get('extra_time_or_penalties', 'N/A')}"
    )