# service/settlement.py
"""
service/settlement.py

Checks Polymarket settlement for a fixture and updates the matching
v2_bets row with the actual outcome and computed P&L.
"""

import httpx
from datetime import datetime, timezone

from config.settings import settings
from service.db import update_bet, get_pending_bets


def get_settlement(fixture_id: int) -> dict | None:
    """Returns the settlement dict if settled, None if still pending or not found."""
    with httpx.Client(headers=settings.H_ARENA, timeout=15) as client:
        resp = client.get(f"{settings.ARENA}/api/v1/data/polymarket/markets/{fixture_id}/settlement")

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if data.get("status") != "settled":
        return None
    return data


def _map_outcome(settled_outcome: str, home_code: str, away_code: str) -> str:
    if settled_outcome == "draw":
        return "draw"
    if settled_outcome == home_code:
        return "home"
    if settled_outcome == away_code:
        return "away"
    return "unknown"


def _compute_pnl(decision: str, actual_outcome: str, stake_usd: float, fill_price: float | None) -> float:
    if decision != actual_outcome:
        return -stake_usd
    if not fill_price or fill_price <= 0:
        return 0.0  # can't compute a real payout without knowing what we paid
    shares = stake_usd / fill_price
    payout = shares * 1.0  # winning YES shares redeem at $1 each
    return round(payout - stake_usd, 2)


def settle_bet(bet: dict) -> dict:
    settlement = get_settlement(bet["fixture_id"])
    if settlement is None:
        return {"bet_id": bet["id"], "status": "still_pending"}

    settled_outcome = settlement["settled_outcome"]
    actual_outcome = _map_outcome(settled_outcome, bet["home_code"], bet["away_code"])

    pnl = None
    if bet.get("decision") not in (None, "skip"):
        pnl = _compute_pnl(bet["decision"], actual_outcome, bet.get("stake_usd") or 0, bet.get("fill_price"))

    settled_at_iso = datetime.fromtimestamp(
        settlement["settled_at"] / 1000, tz=timezone.utc
    ).isoformat()

    update_bet(bet["id"], {
        "actual_outcome": actual_outcome,
        "pnl": pnl,
        "settled_at": settled_at_iso,
    })

    return {"bet_id": bet["id"], "status": "settled", "actual_outcome": actual_outcome, "pnl": pnl}

def settle_all_pending() -> list[dict]:
    """Check every unsettled bet and settle whichever ones have finished."""
    pending = get_pending_bets()
    return [settle_bet(bet) for bet in pending]