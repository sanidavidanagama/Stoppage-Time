"""
test_ledger_submit.py
"""

import time
import uuid
import requests
from config import settings

FIXTURE_ID = "19609127"
SESSION_ID = f"prematch:{FIXTURE_ID}"
AGENT_ID   = "54555fe7-4adc-4bcd-ad1f-1307a388d5ef"

def ts():
    return int(time.time() * 1000)

def rid():
    return str(uuid.uuid4())

records = [

    # 6. Acting — prediction (NO agent_id)
{
    "schema_version":  "0.3",
    # NO agent_id here
    "record_id":       rid(),
    "session_id":      SESSION_ID,
    "behavior":        "Acting",
    "client_ts_utc":   ts(),
    "action_type":     "prediction",
    "target_system":   "arena",
    "action_summary":  f"Predict home @ 70% for {FIXTURE_ID}",
    "parameters": {
        "fixture_id":  FIXTURE_ID,
        "outcome":     "home",
        "probability": 0.70,
    },
    "dry_run":         False,
    "execution_status":"confirmed",
},

# 7. Acting — skip (execution_status must be confirmed/failed/simulated/pending)
{
    "schema_version":  "0.3",
    "agent_id":        AGENT_ID,
    "record_id":       rid(),
    "session_id":      SESSION_ID,
    "behavior":        "Acting",
    "client_ts_utc":   ts(),
    "action_type":     "skip",
    "target_system":   "arena",
    "action_summary":  "Agent decided not to place a bet",
    "parameters":      {"reason": "confidence too low"},
    "dry_run":         False,
    "execution_status":"confirmed",   # not "skipped"
},
]

# --- Submit ------------------------------------------------------------------

print(f"Submitting {len(records)} test records...\n")

r = requests.post(
    f"{settings.ARENA}/api/v1/arena/ledger/records/batch",
    headers = settings.H_ARENA,
    json    = {"records": records, "fixture_id": FIXTURE_ID},
    timeout = 30,
)

print(f"HTTP status : {r.status_code}")
resp   = r.json()
stored = resp.get("records", [])
errors = resp.get("errors",  [])

print(f"Stored : {len(stored)}")
print(f"Errors : {len(errors)}\n")

for i, rec in enumerate(records):
    ok  = any(s.get("record_id") == rec["record_id"] for s in stored)
    err = next((e for e in errors if e.get("index") == i), None)
    status = "OK" if ok else f"FAIL — {err.get('message','?')[:80] if err else 'unknown'}"
    label  = rec.get("label") or rec.get("action_type") or "-"
    print(f"  [{i}] {rec['behavior']:12s} ({label:20s}) → {status}")