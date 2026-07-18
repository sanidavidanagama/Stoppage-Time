# tests/test_tactics_agent.py
from dotenv import load_dotenv

load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.tactics_agent import tactics_analyse

result = tactics_analyse(
    home_team="Belgium",
    away_team="Senegal",
    round_info="Round of 16",
)
print(result)