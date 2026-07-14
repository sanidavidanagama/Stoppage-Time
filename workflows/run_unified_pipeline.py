import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import uuid
from agents.unified_agent import run_unified_agent

if __name__ == "__main__":
    session_id = f"unified-{uuid.uuid4().hex[:8]}"
    result = run_unified_agent(home_name="Argentina", away_name="Switzerland", round_info="Quarter-final", session_id=session_id)
    print(result)