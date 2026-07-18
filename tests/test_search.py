# tests/test_search.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.search_agent import web_search

result = web_search("Paraguay vs France World Cup 2026 Round of 16 squad news injuries")
print("Answer:\n", result.get("answer"))
print("\nSources:")
for s in result.get("sources", []):
    print(" -", s["title"], "->", s["url"])