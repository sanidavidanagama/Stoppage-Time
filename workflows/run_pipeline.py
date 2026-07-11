import uuid
from service.context import set_context
from service.stair_ai_ledger import observing as ledger_observing, submit_records
from service.db import log_step
from agents.planning_agent import run_planning
from agents.reasoning_agent import run_reasoning
from agents.betting_agent import run_betting_agent
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run(home: str, away: str, round_info: str):
    session_id = f"live-{uuid.uuid4().hex[:8]}"
    set_context(session_id)

    description = f"Evaluating {home} vs {away} ({round_info})"
    try:
        log_step(session_id=session_id, step_type="Observing", tool="pipeline", response=description)
    except Exception as e:
        print(f"[pipeline] Supabase Observing log failed: {e}")
    try:
        submit_records(ledger_observing(session_id, description, "manual_run"))
    except Exception as e:
        print(f"[pipeline] Ledger Observing submit failed: {e}")

    context = run_planning(home, away, round_info, session_id)
    prediction = run_reasoning(home_name=home, away_name=away, round_info=round_info,
                                pre_gathered_context=context, session_id=session_id)
    if not prediction.get("available"):
        print(prediction); return

    decision = run_betting_agent(home, away, prediction, session_id)
    print(decision)