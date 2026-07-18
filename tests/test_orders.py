# tests/test_orders.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.polymarket import get_market_data
from service.orders import place_order

market = get_market_data("Mexico", "England")
print("Market:", market)

if market and market.get("mapping_ok"):
    result = place_order(
        fixture_id=market["fixture_id"],
        team_code=market["away"]["code"],   # England, just as a small live test
        usd_size=1.00,
        market_price=market["away"]["price"],
    )
    print(json.dumps(result, indent=2))
else:
    print("Market not available/mapped right now — pick a different live fixture.")