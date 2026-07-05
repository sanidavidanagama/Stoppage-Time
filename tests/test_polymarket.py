# tests/test_polymarket.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.polymarket import get_polymarket_prices

print(get_polymarket_prices("Paraguay", "France"))