# tests/test_wallet.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.wallet import get_available_balance

balance = get_available_balance()
print(f"Available balance: ${balance}")