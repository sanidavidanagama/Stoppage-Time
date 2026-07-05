# tests/test_full_pipeline.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.reasoning_agent import run_reasoning
from agents.betting_agent import run_betting_agent

HOME = "Mexico"
AWAY = "England"
ROUND = "Round of 16"

session_id = f"live-{uuid.uuid4().hex[:8]}"
print(f"Session: {session_id}\n")

print("=== REASONING ===")
prediction = run_reasoning(
    home_name=HOME,
    away_name=AWAY,
    round_info=ROUND,
)
print(json.dumps(prediction, indent=2))

if not prediction.get("available"):
    print("\nReasoning failed — stopping before betting.")
else:
    print("\n=== BETTING ===")
    decision = run_betting_agent(
        home_name=HOME,
        away_name=AWAY,
        prediction=prediction,
        session_id=session_id,
        leaderboard_status="Rank unknown — leaderboard endpoint currently down",
    )
    print(json.dumps(decision, indent=2))