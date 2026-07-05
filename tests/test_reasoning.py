# tests/test_reasoning.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.reasoning_agent import run_reasoning

result = run_reasoning(
    home_name="Spain",
    away_name="Austria",
    round_info="Round of 32",
)
print(json.dumps(result, indent=2))