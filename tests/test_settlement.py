# tests/test_settlement.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.settlement import settle_all_pending

results = settle_all_pending()
print(json.dumps(results, indent=2))