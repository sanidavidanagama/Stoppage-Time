# service/order_execution.py
"""
service/order_execution.py

The single function that actually moves money. Reasoning (unified or
multi-agent) only ever gets a bet row to "awaiting_order" — this is what
turns that into a real Polymarket order. Deliberately agent-agnostic:
agent_bets rows are shape-identical regardless of which pipeline produced
them (fixture_id, home_code/away_code, decision, stake_usd are all already
on the row), so this one function serves both.
"""

from service.db import get_bet_by_id, update_bet, update_session_status
from service.polymarket import get_market_data_by_fixture_id
from service.orders import place_order, poll_order
from service.telemetry import record_order

PLACEABLE_DECISIONS = ("home", "draw", "away")


def execute_order(bet_id: str) -> dict:
    bet = get_bet_by_id(bet_id)
    if bet is None:
        return {"status": "error", "reason": "bet_not_found"}

    decision = bet.get("decision")
    if decision not in PLACEABLE_DECISIONS:
        return {"status": "error", "reason": f"nothing_to_order_decision_is_{decision}"}

    if bet.get("order_id"):
        # Idempotency — a retry (double-click, network retry) must not place a second order.
        return {
            "status": "already_ordered",
            "order_id": bet["order_id"],
            "order_status": bet.get("order_status"),
            "fill_price": bet.get("fill_price"),
        }

    session_id = bet["session_id"]
    fixture_id = bet["fixture_id"]
    stake = bet.get("stake_usd")
    if not stake or stake <= 0:
        update_session_status(session_id, "error")
        return {"status": "error", "reason": "invalid_stake"}

    # Fresh price, not the reasoning-time snapshot — time may have passed
    # between the decision and this call being triggered.
    market = get_market_data_by_fixture_id(fixture_id, bet.get("home_code"), bet.get("away_code"))
    if market is None or not market.get("mapping_ok"):
        update_session_status(session_id, "error")
        return {"status": "error", "reason": "no_live_market"}

    code = "draw" if decision == "draw" else market[decision]["code"]
    price = market["draw"]["price"] if decision == "draw" else market[decision]["price"]

    order_result = place_order(fixture_id, code, stake, price)
    order_id = order_result.get("order_id")
    if not order_id:
        update_bet(bet_id, {"order_status": order_result.get("status", "error")})
        update_session_status(session_id, "error")
        return {"status": "error", "reason": order_result.get("reason", order_result.get("status", "order_rejected"))}

    final_order = poll_order(order_id)
    order_info = {
        "order_id": order_id,
        "order_status": final_order.get("status", order_result.get("status")),
        "fill_price": final_order.get("open_avg_fill_price"),
    }
    update_bet(bet_id, order_info)
    record_order(session_id, fixture_id, code, stake, f"Bought ${stake} of {code}")
    update_session_status(session_id, "completed")

    return {"status": "completed", "decision": decision, "stake_usd": stake, **order_info}
