# workflows/run_local_dry_run.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import uuid
from agents.local_unified_agent import dry_run

if __name__ == "__main__":
    session_id = f"dryrun-{uuid.uuid4().hex[:8]}"
    dry_run(
        home_name="Spain", away_name="Belgium", round_info="Quarter-final",
        session_id=session_id,
        test_agent_id="54555fe7-4adc-4bcd-ad1f-1307a388d5ef",  # your backup test agent
    )