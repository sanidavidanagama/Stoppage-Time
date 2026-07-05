"""
service/polymarket.py

Live Polymarket odds for a fixture, via the Arena's single-call
markets-by-fixture endpoint.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from config.settings import settings
from service.schedule import find_fixture_by_teams


def _client() -> httpx.Client:
    return httpx.Client(headers=settings.H_ARENA, timeout=15)


def get_polymarket_prices(home_name: str, away_name: str) -> str:
    """
    Get current Polymarket implied win probabilities for a fixture.

    Args:
        home_name: e.g. "Paraguay"
        away_name: e.g. "France"

    Returns:
        Plain-text summary of implied probabilities, or an explanation
        if the fixture or market isn't available.
    """
    fixture = find_fixture_by_teams(home_name, away_name)
    if fixture is None:
        return f"No fixture found for {home_name} vs {away_name}."

    url = f"{settings.POLYMARKET_MARKET_URL}/{fixture['fixture_id']}"

    with _client() as client:
        resp = client.get(url)

    if resp.status_code == 404:
        return f"No Polymarket market found for {home_name} vs {away_name}."
    resp.raise_for_status()

    data = resp.json()
    outcomes = data.get("outcomes", [])
    if not outcomes:
        return f"Polymarket market exists for {home_name} vs {away_name} but has no outcome prices yet."

    return _summarize(data, outcomes, home_name, away_name)


def get_market_data(home_name: str, away_name: str) -> dict | None:
    """
    Get raw Polymarket data for a fixture, with outcomes explicitly mapped
    to home/draw/away using Sportmonks short_codes.

    Returns None if the fixture or market isn't found. If found but the
    short_codes don't match any outcome name, returns the data with
    mapping_ok=False so the caller can skip safely.
    """
    fixture = find_fixture_by_teams(home_name, away_name)
    if fixture is None:
        return None

    with _client() as client:
        resp = client.get(f"{settings.POLYMARKET_MARKET_URL}/{fixture['fixture_id']}")

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    outcomes = data.get("outcomes", [])
    if not outcomes:
        return None

    home_code = (fixture["home"].get("short_code") or "").upper()
    away_code = (fixture["away"].get("short_code") or "").upper()

    result = {
        "fixture_id": fixture["fixture_id"],
        "home": {"code": home_code, "price": None},
        "draw": {"price": None},
        "away": {"code": away_code, "price": None},
        "fetched_at": data.get("fetched_at"),
    }

    for outcome in outcomes:
        name = (outcome.get("name") or "").upper()
        price = outcome.get("mid_price")
        if name == "DRAW":
            result["draw"]["price"] = price
        elif home_code and name == home_code:
            result["home"]["price"] = price
        elif away_code and name == away_code:
            result["away"]["price"] = price

    result["mapping_ok"] = all([
        result["home"]["price"] is not None,
        result["draw"]["price"] is not None,
        result["away"]["price"] is not None,
    ])

    return result


def _summarize(data: dict, outcomes: list[dict], home_name: str, away_name: str) -> str:
    lines = [f"Polymarket odds for {home_name} vs {away_name}:"]

    for outcome in outcomes:
        name = outcome.get("name", "unknown")
        price = outcome.get("mid_price")

        if price is None:
            lines.append(f"{name}: price unavailable")
            continue

        label = "Draw" if name.lower() == "draw" else name
        lines.append(f"{label}: {round(price * 100, 1)}% implied win probability")

    fetched_at = data.get("fetched_at")
    if fetched_at:
        age_minutes = max(0, (datetime.now(timezone.utc).timestamp() * 1000 - fetched_at) / 60000)
        if age_minutes < 1:
            lines.append("(fetched just now)")
        else:
            lines.append(f"(fetched {round(age_minutes, 1)} minutes ago)")

    return "\n".join(lines)