# tests/test_reflecting.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.reflecting_agent import run_reflection

result = run_reflection("7fa642ce-3daa-4d1c-bfde-2aa9107d254c")
print(json.dumps(result, indent=2))