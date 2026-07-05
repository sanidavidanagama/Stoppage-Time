# tests/test_schedule.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.schedule import find_fixture_by_teams

result = find_fixture_by_teams("Paraguay", "France")
print(result)