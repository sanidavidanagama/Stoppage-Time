# tests/test_market_debug.py — just update the team names
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.schedule import find_fixture_by_teams
from service.polymarket import get_market_data

fixture = find_fixture_by_teams("Spain", "Portugal")
print("Fixture:", fixture)

market = get_market_data("Spain", "Portugal")
print("Market:", market)