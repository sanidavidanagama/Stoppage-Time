# tests/test_betting_agent.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.betting_agent import run_betting_agent

fake_prediction = {
    "home_win_probability": 0.55,
    "draw_probability": 0.15,
    "away_win_probability": 0.4,
    "confidence": "medium",
}

result = run_betting_agent(
    "Brazil", "Norway",   # swap for whichever fixture is still upcoming right now
    prediction=fake_prediction,
    session_id="test-betting-002",
    leaderboard_status="Rank unknown — leaderboard endpoint currently down",
)
print(json.dumps(result, indent=2))