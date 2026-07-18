# service/orders.py
"""
service/orders.py

Submits Polymarket orders via the Arena's orders endpoint.
"""

import httpx
import uuid
from config.settings import settings
import time

LIMIT_PRICE_BUFFER = 0.03


def place_order(fixture_id: int, team_code: str, usd_size: float, market_price: float) -> dict:
    """
    Buy YES of team_code (or "draw") for a fixture.

    Args:
        fixture_id: Sportmonks numeric fixture id (confirmed same as used elsewhere).
        team_code: short code (e.g. "MEX") or "draw".
        usd_size: dollar amount to spend.
        market_price: current mid_price for this outcome — used to set a
            realistic limit price with a small buffer, not a blind 0.99.

    Returns:
        The order response on success, or {"status": "error"/"rejected", "reason": ...} on failure.
    """
    limit_price = min(round(market_price + LIMIT_PRICE_BUFFER, 3), 0.99)

    payload = {
        "fixture_id":            str(fixture_id),
        "team_code":             team_code,
        "usd_size":              f"{usd_size:.2f}",
        "limit_price":           limit_price,
        "time_in_force_seconds": 30,
        "idempotency_key":       str(uuid.uuid4()),
    }

    try:
        with httpx.Client(headers=settings.H_ARENA, timeout=30) as client:
            resp = client.post(f"{settings.ARENA}/api/v1/arena/orders", json=payload)

        if resp.status_code == 404:
            return {"status": "not_live", "payload_sent": payload}
        if resp.status_code >= 400:
            return {"status": "rejected", "reason": resp.text[:300], "payload_sent": payload}

        return resp.json()
    except Exception as e:
        return {"status": "error", "reason": str(e), "payload_sent": payload}
    

def poll_order(order_id: str, max_wait_seconds: int = 30, interval: int = 5) -> dict:
    attempts = max_wait_seconds // interval
    last = {}

    for i in range(attempts):
        time.sleep(interval)
        try:
            with httpx.Client(headers=settings.H_ARENA, timeout=10) as client:
                resp = client.get(f"{settings.ARENA}/api/v1/arena/orders/{order_id}")
            if not resp.ok:
                print(f"[poll_order] attempt {i+1}: HTTP {resp.status_code} — {resp.text[:200]}")
                continue
            last = resp.json()
            status = last.get("status")
            if status in ("completed", "rejected", "filled", "settled"):
                return last
        except Exception as e:
            print(f"[poll_order] attempt {i+1} exception: {e}")
            continue

    return last or {"status": "unknown", "reason": "polling timed out with no response"}
