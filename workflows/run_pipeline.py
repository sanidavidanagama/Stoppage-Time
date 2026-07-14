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

def run(home: str, away: str, round_info: str, session_id: str | None = None,
        kickoff_hint: int | str | None = None):
    if session_id is None:
        session_id = f"live-{uuid.uuid4().hex[:8]}"
    set_context(session_id)

    # Session must exist before ANY log or bet write — both agent_logs and
    # agent_bets have a hard FK on session_id.
    create_session(session_id, home, away, source="multi_agent")

    record_observing(session_id, f"Evaluating {home} vs {away} ({round_info})", "manual_run")

    context = run_planning(home, away, round_info, session_id, kickoff_hint=kickoff_hint)
    prediction = run_reasoning(home_name=home, away_name=away, round_info=round_info,
                                pre_gathered_context=context, session_id=session_id)
    if not prediction.get("available"):
        update_session_status(session_id, "error")
        print(prediction)
        return prediction

    decision = run_betting_agent(home, away, prediction, session_id, kickoff_hint=kickoff_hint)
    update_session_status(session_id, "skipped" if decision.get("decision") == "skip" else "awaiting_order")
    print(decision)
    return decision


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    from service.order_execution import execute_order

    result = run(home="Argentina", away="Switzerland", round_info="Quarter-final")
    bet_id = result.get("bet_id")
    if bet_id and result.get("decision") != "skip":
        print(execute_order(bet_id))