# service/telemetry.py
"""
service/telemetry.py

One call, two writes: every LLM call, tool call, and pipeline step gets
recorded to both Supabase (v2_logs) and Stair AI's Reasoning Ledger. Both
are best-effort — a logging failure never blocks a real decision.
"""

from config.settings import settings
from service.db import log_step
from service.stair_ai_ledger import (
    observing as ledger_observing,
    planning as ledger_planning,
    thinking as ledger_thinking,
    tool_calling as ledger_tool_calling,
    acting_prediction as ledger_acting_prediction,
    acting_order as ledger_acting_order,
    reflecting as ledger_reflecting,
    submit_records,
)


def record_observing(session_id: str, description: str, source: str) -> None:
    """Record what triggered this decision cycle."""
    try:
        log_step(session_id=session_id, step_type="Observing", tool="pipeline", response=description)
    except Exception as e:
        print(f"[telemetry] Supabase Observing log failed (non-fatal): {e}")
    try:
        submit_records(ledger_observing(session_id, description, source))
    except Exception as e:
        print(f"[telemetry] Ledger Observing submit failed (non-fatal): {e}")


def record_planning(session_id: str, goal: str, steps: list[str], bet_id: str | None = None) -> None:
    """Record the plan for this decision cycle."""
    try:
        log_step(session_id=session_id, step_type="Planning", tool="planning", bet_id=bet_id, response=f"{goal}: {steps}")
    except Exception as e:
        print(f"[telemetry] Supabase Planning log failed (non-fatal): {e}")
    try:
        submit_records(ledger_planning(session_id, goal, steps))
    except Exception as e:
        print(f"[telemetry] Ledger Planning submit failed (non-fatal): {e}")


def record_thinking(
    session_id: str,
    bet_id: str | None,
    tool: str,
    model: str,
    prompt: str,
    response: str,
    internal_reasoning: str = "",
) -> None:
    """Record one LLM call (an agent's own reasoning step)."""
    try:
        log_step(
            session_id=session_id, step_type="Thinking", tool=tool, bet_id=bet_id,
            model=model, prompt=prompt, response=response,
        )
    except Exception as e:
        print(f"[telemetry] Supabase Thinking log failed (non-fatal): {e}")

    try:
        submit_records(
            ledger_thinking(
                session_id=session_id, upstream_id=None, model_name=model,
                internal_reasoning=internal_reasoning or response,
                prompt=prompt, output_payload=response,
            )
        )
    except Exception as e:
        print(f"[telemetry] Ledger Thinking submit failed (non-fatal): {e}")


def record_tool_call(
    session_id: str,
    bet_id: str | None,
    tool_name: str,
    params: dict,
    result_summary: str,
    success: bool = True,
) -> None:
    """Record one tool invocation (e.g. consult_tactics, get_fixture_news)."""
    try:
        log_step(
            session_id=session_id, step_type="ToolCalling", tool=tool_name, bet_id=bet_id,
            prompt=str(params), response=result_summary,
        )
    except Exception as e:
        print(f"[telemetry] Supabase ToolCalling log failed (non-fatal): {e}")

    try:
        submit_records(
            ledger_tool_calling(
                session_id=session_id, upstream_id=None, tool_name=tool_name,
                params=params, result_summary=result_summary, success=success,
            )
        )
    except Exception as e:
        print(f"[telemetry] Ledger ToolCalling submit failed (non-fatal): {e}")


def record_prediction(session_id: str, fixture_id, outcome: str, probability: float, notes: str = "") -> str | None:
    """
    Submit the required Acting/prediction record. Returns the server-assigned
    record_id (needed as the order record's upstream_record_id), or None if
    the submission failed.
    """
    try:
        result = submit_records(ledger_acting_prediction(session_id, fixture_id, outcome, probability, notes))
        records = result.get("records", [])
        return records[0]["record_id"] if records else None
    except Exception as e:
        print(f"[telemetry] Ledger Acting/prediction submit failed (non-fatal): {e}")
        return None


def record_order(session_id: str, fixture_id, team_code: str, usd_size: float, summary: str, upstream_id: str | None = None) -> None:
    try:
        submit_records(ledger_acting_order(session_id, upstream_id, fixture_id, team_code, usd_size, summary))
    except Exception as e:
        print(f"[telemetry] Ledger Acting/order submit failed (non-fatal): {e}")

def record_reflecting(session_id: str, bet_id: str, output_payload: str) -> None:
    """Record a post-settlement self-reflection (personality update or not)."""
    try:
        log_step(session_id=session_id, step_type="Reflecting", tool="reflecting", bet_id=bet_id, response=output_payload)
    except Exception as e:
        print(f"[telemetry] Supabase Reflecting log failed (non-fatal): {e}")
    try:
        submit_records(ledger_reflecting(session_id, bet_id, output_payload))
    except Exception as e:
        print(f"[telemetry] Ledger Reflecting submit failed (non-fatal): {e}")