# tests/test_rls_debug.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from config.settings import settings

print("Key prefix:", settings.ST_SUPABASE_SECRET_KEY[:20], "...")
print("URL:", settings.ST_SUPABASE_URL)

headers = {
    "apikey": settings.ST_SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {settings.ST_SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

print("\n--- GET v2_bets (read test) ---")
with httpx.Client(headers=headers, timeout=15) as client:
    resp = client.get(f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets", params={"select": "id", "limit": "1"})
print("STATUS:", resp.status_code)
print("BODY:", resp.text)

print("\n--- POST v2_bets (write test, harmless dummy row) ---")
test_row = {
    "session_id": "rls-debug-test",
    "home_team": "TestHome",
    "away_team": "TestAway",
    "decision": "skip",
}
with httpx.Client(headers=headers, timeout=15) as client:
    resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets", json=test_row)
print("STATUS:", resp.status_code)
print("BODY:", resp.text)