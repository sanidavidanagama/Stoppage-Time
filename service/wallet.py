# service/wallet.py
"""
service/wallet.py

Fetches the agent's current available USDC balance from the Arena.
"""

import httpx
from config.settings import settings


def get_available_balance() -> float:
    """
    Get the agent's currently available (unlocked) USDC balance.
    """
    with httpx.Client(headers=settings.H_ARENA, timeout=15) as client:
        resp = client.get(f"{settings.ARENA}/api/v1/arena/agents/me")
    resp.raise_for_status()
    data = resp.json()
    return float(data["wallet"]["available_balance_usdc"])