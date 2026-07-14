import uuid
from service.context import set_context
from service.db import create_session, update_session_status
from service.telemetry import record_observing
from agents.planning_agent import run_planning
from agents.reasoning_agent import run_reasoning
from agents.betting_agent import run_betting_agent
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run(home: str, away: str, round_info: str):
    session_id = f"live-{uuid.uuid4().hex[:8]}"
    set_context(session_id)

    # Session must exist before ANY log or bet write — both agent_logs and
    # agent_bets have a hard FK on session_id.
    create_session(session_id, home, away, source="multi_agent")

    record_observing(session_id, f"Evaluating {home} vs {away} ({round_info})", "manual_run")

    context = run_planning(home, away, round_info, session_id)
    prediction = run_reasoning(home_name=home, away_name=away, round_info=round_info,
                                pre_gathered_context=context, session_id=session_id)
    if not prediction.get("available"):
        update_session_status(session_id, "error")
        print(prediction)
        return prediction

    decision = run_betting_agent(home, away, prediction, session_id)
    update_session_status(session_id, "skipped" if decision.get("decision") == "skip" else "completed")
    print(decision)
    return decision