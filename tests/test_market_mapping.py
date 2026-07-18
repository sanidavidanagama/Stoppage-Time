# tests/test_market_mapping.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.polymarket import get_market_data

result = get_market_data("Paraguay", "France")
print(result)