# service/telemetry.py
"""
service/telemetry.py

One call, two writes: every LLM call and tool call gets recorded to both
Supabase (v2_logs) and Stair AI's Reasoning Ledger. Both are
best-effort — a logging failure never blocks a real decision.
"""

from config.settings import settings
from service.db import log_step
from service.stair_ai_ledger import thinking as ledger_thinking, tool_calling as ledger_tool_calling, submit_records


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
            session_id=session_id,
            step_type="Thinking",
            tool=tool,
            bet_id=bet_id,
            model=model,
            prompt=prompt,
            response=response,
        )
    except Exception as e:
        print(f"[telemetry] Supabase Thinking log failed (non-fatal): {e}")

    try:
        submit_records(
            ledger_thinking(
                session_id=session_id,
                upstream_id=None,
                model_name=model,
                internal_reasoning=internal_reasoning or response,
                prompt=prompt,
                output_payload=response,
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
            session_id=session_id,
            step_type="ToolCalling",
            tool=tool_name,
            bet_id=bet_id,
            prompt=str(params),
            response=result_summary,
        )
    except Exception as e:
        print(f"[telemetry] Supabase ToolCalling log failed (non-fatal): {e}")

    try:
        submit_records(
            ledger_tool_calling(
                session_id=session_id,
                upstream_id=None,
                tool_name=tool_name,
                params=params,
                result_summary=result_summary,
                success=success,
            )
        )
    except Exception as e:
        print(f"[telemetry] Ledger ToolCalling submit failed (non-fatal): {e}")