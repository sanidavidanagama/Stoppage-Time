# tests/test_supabase_full.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.db import (
    create_session, update_session_status, log_step,
    save_bet, update_bet, get_recent_bets, get_bet_by_id, get_logs_for_bet,
)
from service.telemetry import record_thinking, record_tool_call, record_observing, record_planning

session_id = f"supabase-test-{uuid.uuid4().hex[:8]}"
print(f"Session: {session_id}\n")

try:
    print("1. create_session...")
    create_session(session_id, "TestHome", "TestAway")
    print("   OK")

    print("2. record_observing (telemetry -> db)...")
    record_observing(session_id, "Test observing record", "manual_test")
    print("   OK")

    print("3. record_planning (telemetry -> db)...")
    record_planning(session_id, "Test goal", ["step 1", "step 2"])
    print("   OK")

    print("4. record_tool_call (telemetry -> db)...")
    record_tool_call(session_id, None, "test_tool", {"param": "value"}, "test result", True)
    print("   OK")

    print("5. save_bet...")
    bet = save_bet({"session_id": session_id, "home_team": "TestHome", "away_team": "TestAway", "decision": "pending"})
    bet_id = bet.get("id")
    print(f"   OK, bet_id={bet_id}")

    print("6. record_thinking (telemetry -> db)...")
    record_thinking(session_id, bet_id, "unified", "test-model", "test prompt", "test response", "test reasoning")
    print("   OK")

    print("7. update_bet...")
    update_bet(bet_id, {"decision": "skip", "bet_reason": "test complete"})
    print("   OK")

    print("8. update_session_status...")
    update_session_status(session_id, "completed")
    print("   OK")

    print("9. get_logs_for_bet (session_id join)...")
    logs = get_logs_for_bet(bet_id)
    print(f"   OK, found {len(logs)} logs: {[l['step_type'] for l in logs]}")

    print("\nALL SUPABASE WRITES/READS WORKING.")

except Exception as e:
    print(f"\nFAILED AT THIS STEP: {e}")