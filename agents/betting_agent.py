# agents/betting_agent.py
"""
agents/betting_agent.py

Deterministic betting decision — no LLM involved. Takes the Reasoning
Agent's probabilities and Polymarket's outcome-mapped prices and decides:
which outcome to bet, how much, or skip.
"""

from config.settings import settings
from service.polymarket import get_market_data
from service.wallet import get_available_balance


def decide_bet(home_name: str, away_name: str, prediction: dict) -> dict:
    """
    Args:
        prediction: the Reasoning Agent's output — must contain
            home_win_probability, draw_probability, away_win_probability.

    Returns:
        {
            "decision": "home" | "draw" | "away" | "skip",
            "reason": str,
            "edge_pp": float | None,
            "stake_usd": float | None,
            "price": float | None,
        }
    """
    market = get_market_data(home_name, away_name)

    if market is None:
        return {"decision": "skip", "reason": "no_market_data", "edge_pp": None, "stake_usd": None, "price": None}

    if not market.get("mapping_ok"):
        return {"decision": "skip", "reason": "outcome_mapping_failed", "edge_pp": None, "stake_usd": None, "price": None}

    balance = get_available_balance()

    candidates = [
        ("home", prediction["home_win_probability"], market["home"]["price"]),
        ("draw", prediction["draw_probability"],      market["draw"]["price"]),
        ("away", prediction["away_win_probability"],  market["away"]["price"]),
    ]

    best = None
    for outcome, agent_prob, price in candidates:
        edge_pp = (agent_prob - price) * 100
        if best is None or edge_pp > best["edge_pp"]:
            best = {"outcome": outcome, "agent_prob": agent_prob, "price": price, "edge_pp": edge_pp}

    if best["edge_pp"] < settings.MIN_EDGE_PP:
        return {
            "decision": "skip",
            "reason": f"best_edge_{round(best['edge_pp'], 1)}pp_below_threshold",
            "edge_pp": round(best["edge_pp"], 1),
            "stake_usd": None,
            "price": best["price"],
        }

    stake = _kelly_stake(best["agent_prob"], best["price"], balance)

    return {
        "decision": best["outcome"],
        "reason": f"edge_{round(best['edge_pp'], 1)}pp",
        "edge_pp": round(best["edge_pp"], 1),
        "stake_usd": round(stake, 2),
        "price": best["price"],
    }


def _kelly_stake(agent_prob: float, price: float, balance: float) -> float:
    """Fractional Kelly stake, clamped between MIN_STAKE_USD and MAX_STAKE_PCT of balance."""
    if price <= 0 or price >= 1:
        return 0.0

    b = (1 - price) / price
    q = 1 - agent_prob
    kelly_fraction = (agent_prob * b - q) / b

    if kelly_fraction <= 0:
        return 0.0

    raw_stake = kelly_fraction * settings.KELLY_MULTIPLIER * balance
    ceiling = settings.MAX_STAKE_PCT * balance

    return max(settings.MIN_STAKE_USD, min(raw_stake, ceiling))