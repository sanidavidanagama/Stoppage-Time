# tests/test_betting_agent.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.betting_agent import decide_bet

fake_prediction = {
    "home_win_probability": 0.10,
    "draw_probability": 0.15,
    "away_win_probability": 0.75,
}

result = decide_bet("Paraguay", "France", fake_prediction)
print(json.dumps(result, indent=2))