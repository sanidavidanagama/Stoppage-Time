# tests/test_new_schema.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.db import (
    create_session, update_session_status, log_step,
    save_bet, update_bet, get_recent_bets, get_bet_by_id, get_logs_for_bet,
)

session_id = f"schema-test-{uuid.uuid4().hex[:8]}"
print(f"Session: {session_id}\n")

print("1. create_session...")
create_session(session_id, "TestHome", "TestAway")
print("   OK")

print("2. log_step (Observing)...")
log_step(session_id=session_id, step_type="Observing", tool="pipeline", response="Test run started")
print("   OK")

print("3. log_step (Thinking)...")
log_step(session_id=session_id, step_type="Thinking", tool="tactics", model="test-model",
          prompt="test prompt", response="test response")
print("   OK")

print("4. save_bet...")
bet = save_bet({
    "session_id": session_id, "home_team": "TestHome", "away_team": "TestAway",
    "decision": "skip",
})
bet_id = bet.get("id")
print(f"   OK, bet_id={bet_id}")

print("5. update_bet...")
update_bet(bet_id, {"bet_reason": "updated in test"})
print("   OK")

print("6. update_session_status...")
update_session_status(session_id, "completed")
print("   OK")

print("7. get_bet_by_id...")
fetched = get_bet_by_id(bet_id)
print(f"   OK, bet_reason={fetched.get('bet_reason')}")

print("8. get_logs_for_bet (via session_id lookup)...")
logs = get_logs_for_bet(bet_id)
print(f"   OK, found {len(logs)} log rows")

print("9. get_recent_bets...")
recent = get_recent_bets(limit=3)
print(f"   OK, {len(recent)} bets returned")

print("\nAll checks passed.")