# tests/test_stoppage_db.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.db import save_bet, log_step, get_recent_bets

bet = save_bet({
    "session_id": "test-session-001",
    "fixture_id": 19606967,
    "fixture_name": "Paraguay vs France",
    "home_team": "Paraguay",
    "home_code": "PAR",
    "away_team": "France",
    "away_code": "FRA",
    "home_probability": 0.10,
    "draw_probability": 0.15,
    "away_probability": 0.75,
    "confidence": "medium",
    "decision": "skip",
    "edge_pp": 3.2,
})
print("Saved bet:", bet)

log_step(
    session_id="test-session-001",
    step_type="Thinking",
    agent="betting",
    bet_id=bet["id"],
    model="claude-haiku-4-5-20251001",
    prompt="test prompt",
    response="test response",
)
print("Logged step OK")

print("Recent bets:", get_recent_bets(limit=3))