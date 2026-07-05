# tests/test_news.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.news_agent import get_news

# Test the angle that actually burned us last time — injuries — to see
# if the recency instructions fix the stale-info problem
result = get_news("Argentina", "Cape Verde", angle="injuries", match_date="2026-06-30")
print("=== INJURIES ===")
print(result.get("answer"))
print("\nSources:")
for s in result.get("sources", []):
    print(" -", s["title"], "->", s["url"])

print("\n\n=== WILDCARD (just for fun, worth seeing what it finds) ===")
result2 = get_news("Argentina", "Cape Verde", angle="wildcard", match_date="2026-06-30")
print(result2.get("answer"))