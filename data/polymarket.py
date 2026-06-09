"""
data/polymarket.py

Fetches Polymarket market data for a given fixture.
Uses identity_map from data/identity.py for all token/condition IDs.
No LLM calls here — pure data fetching and cleaning.

Functions:
    get_market_meta(identity_map)   -> event metadata (liquidity, volume, etc)
    get_live_prices(identity_map)   -> live CLOB mid prices per outcome
    get_price_history(identity_map) -> 24hr/1wk/1mo price changes
    get_all(identity_map)           -> runs all of the above
"""

import requests
from config import settings


POLYMARKET_TIMEOUT = 30


# --- Market metadata ----------------------------------------------------------

def get_market_meta(identity_map: dict) -> dict:
    """
    Fetch Polymarket Gamma event metadata.
    Returns liquidity, volume, competitive score, negRisk flag.

    Returns:
        {
            "title":        str,
            "liquidity":    float,
            "volume":       float,
            "volume_24hr":  float,
            "competitive":  float,
            "neg_risk":     bool,
            "active":       bool,
            "closed":       bool,
            "available":    bool,
        }
    """
    if not identity_map.get("pm_event_slug"):
        return _unavailable_meta()

    try:
        r = requests.get(
            f"{settings.POLYMARKET_GAMMA}/events",
            params={"slug": identity_map["pm_event_slug"]},
            headers=settings.H_ARENA,
            timeout=POLYMARKET_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException:
        return _unavailable_meta()

    events = r.json().get("body") or []
    if not events:
        return _unavailable_meta()

    e = events[0]
    return {
        "title":       e.get("title"),
        "liquidity":   float(e.get("liquidity") or 0),
        "volume":      float(e.get("volume") or 0),
        "volume_24hr": float(e.get("volume24hr") or 0),
        "competitive": float(e.get("competitive") or 0),
        "neg_risk":    bool(e.get("negRisk")),
        "active":      bool(e.get("active")),
        "closed":      bool(e.get("closed")),
        "available":   True,
    }


def _unavailable_meta() -> dict:
    return {
        "title": None, "liquidity": 0, "volume": 0,
        "volume_24hr": 0, "competitive": 0, "neg_risk": False,
        "active": False, "closed": False, "available": False,
    }


# --- Live CLOB prices ---------------------------------------------------------

def get_live_prices(identity_map: dict) -> dict:
    """
    Fetch live mid prices from Polymarket CLOB for all three outcomes.
    Mid price = implied probability (0..1).

    Returns:
        {
            "home":      float | None,
            "draw":      float | None,
            "away":      float | None,
            "sum":       float | None,
            "available": bool,
        }
    """
    if not identity_map.get("pm_event_slug"):
        return {"home": None, "draw": None, "away": None,
                "sum": None, "available": False}

    def _mid(token_yes: str | None) -> float | None:
        if not token_yes:
            return None
        try:
            r = requests.get(
                f"{settings.POLYMARKET_CLOB}/midpoint",
                params={"token_id": token_yes},
                headers=settings.H_ARENA,
                timeout=10,
            )
            if not r.ok:
                return None
            body = r.json().get("body")
            if isinstance(body, dict) and "mid" in body:
                return round(float(body["mid"]), 4)
        except Exception:
            pass
        return None

    home = _mid(identity_map["home"].get("pm_token_yes"))
    draw = _mid(identity_map["draw"].get("pm_token_yes"))
    away = _mid(identity_map["away"].get("pm_token_yes"))

    mids = [m for m in [home, draw, away] if m is not None]
    total = round(sum(mids), 4) if mids else None
    available = len(mids) == 3

    return {
        "home":      home,
        "draw":      draw,
        "away":      away,
        "sum":       total,
        "available": available,
    }


# --- Price history ------------------------------------------------------------

def get_price_history(identity_map: dict) -> dict:
    """
    Fetch price movement per outcome from Gamma markets.
    Shows how prices have shifted over 24hr, 1wk, 1mo.

    Returns:
        {
            "home": {"change_24hr", "change_1wk", "change_1mo", "last_price"},
            "draw": {...},
            "away": {...},
            "available": bool,
        }
    """
    if not identity_map.get("pm_event_slug"):
        return {"home": None, "draw": None, "away": None, "available": False}

    try:
        r = requests.get(
            f"{settings.POLYMARKET_GAMMA}/events",
            params={"slug": identity_map["pm_event_slug"]},
            headers=settings.H_ARENA,
            timeout=POLYMARKET_TIMEOUT,
        )
        r.raise_for_status()
    except requests.RequestException:
        return {"home": None, "draw": None, "away": None, "available": False}

    events = r.json().get("body") or []
    if not events:
        return {"home": None, "draw": None, "away": None, "available": False}

    markets = events[0].get("markets") or []

    # map slug suffix → outcome key
    slug      = identity_map["pm_event_slug"]
    home_code = identity_map["home"]["short_code"].lower()
    away_code = identity_map["away"]["short_code"].lower()

    outcome_map = {
        f"{slug}-{home_code}": "home",
        f"{slug}-draw":        "draw",
        f"{slug}-{away_code}": "away",
    }

    history = {"home": None, "draw": None, "away": None}

    for mkt in markets:
        market_slug = (mkt.get("slug") or "").lower()
        outcome = outcome_map.get(market_slug)
        if outcome:
            history[outcome] = {
                "change_24hr": mkt.get("oneDayPriceChange"),
                "change_1wk":  mkt.get("oneWeekPriceChange"),
                "change_1mo":  mkt.get("oneMonthPriceChange"),
                "last_price":  mkt.get("lastTradePrice"),
                "best_bid":    mkt.get("bestBid"),
                "best_ask":    mkt.get("bestAsk"),
                "spread":      mkt.get("spread"),
            }

    available = any(v is not None for v in history.values())
    return {**history, "available": available}


# --- Fetch all ----------------------------------------------------------------

def get_all(identity_map: dict) -> dict:
    """
    Runs all Polymarket fetchers and returns a single clean dict.
    This is what the orchestrator calls.

    Returns:
        {
            "meta":          {...},
            "live_prices":   {...},
            "price_history": {...},
        }
    """
    return {
        "meta":          get_market_meta(identity_map),
        "live_prices":   get_live_prices(identity_map),
        "price_history": get_price_history(identity_map),
    }