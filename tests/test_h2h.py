# tests/test_h2h.py
from dotenv import load_dotenv
load_dotenv()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.h2h import get_h2h

print(get_h2h("Mexico", "Germany"))
print("================================")
print(get_h2h("Japan", "Spain"))
print("================================")
print(get_h2h("Spain", "France"))