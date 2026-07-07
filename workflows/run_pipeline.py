# workflows/run_pipeline.py
"""
workflows/run_pipeline.py

Real end-to-end run: Reasoning -> Betting (edge gate, LLM stake decision,
real order if confirmed). No Stair AI ledger submission yet — deferred.
"""

from dotenv import load_dotenv
load_dotenv()

import sys, os, json, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.reasoning_agent import run_reasoning
from agents.betting_agent import run_betting_agent


def run(home: str, away: str, round_info: str):
    session_id = f"live-{uuid.uuid4().hex[:8]}"
    print(f"Session: {session_id}")
    print(f"Fixture: {home} vs {away} ({round_info})\n")

    print("=== REASONING ===")
    prediction = run_reasoning(home_name=home, away_name=away, round_info=round_info)

    if not prediction.get("available"):
        print(json.dumps(prediction, indent=2))
        print("\nReasoning failed — stopping before betting.")
        return

    print(f"Prediction: home {prediction['home_win_probability']:.0%} / "
          f"draw {prediction['draw_probability']:.0%} / "
          f"away {prediction['away_win_probability']:.0%} "
          f"(confidence: {prediction['confidence']})\n")

    print("=== BETTING ===")
    decision = run_betting_agent(
        home_name=home,
        away_name=away,
        prediction=prediction,
        session_id=session_id,
        leaderboard_status="Rank unknown — leaderboard endpoint currently down",
    )
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    # Update these before every run — check test_upcoming_fixtures.py first
    # to confirm the fixture is still genuinely upcoming.
    run(home="Portugal", away="Spain", round_info="Round of 16")