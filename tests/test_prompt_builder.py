"""
Test the tactics prompt builder.

Usage:
    python test_prompt_builder.py

Tests with Paraguay vs France (RO16) — fixture 19606944
Change the FIXTURE_ID below to test with any match.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service.prompt_builder import build_tactics_prompt


# ─── Pick a fixture to test ──────────────────────────────────────────────────
# Paraguay vs France RO16 — change this to any fixture_id
FIXTURE_ID = 19606952

# If that fixture_id doesn't exist, try one of these:
# 19606952 = England vs Congo DR (RO32)
# 19606956 = France vs Sweden (RO32)
# 19606957 = Germany vs Paraguay (RO32)

prompt = build_tactics_prompt(
    fixture_id=FIXTURE_ID,
    round_info="Round of 16",
    stadium="MetLife Stadium, New Jersey",
    weather="25°C, partly cloudy",
)

print("\n")
print("=" * 70)
print("  FINAL PROMPT")
print("=" * 70)
print()
print(prompt)

# Also save to file for inspection
with open("tests/tactics_prompt_output.md", "w", encoding="utf-8") as f:
    f.write(prompt)
print("\n\nSaved to tests/tactics_prompt_output.md")