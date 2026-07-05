# service/db.py
"""
service/db.py

Persistence layer for Stoppage Time's own Supabase instance (v2_bets,
v2_logs). 
"""

import httpx
from config.settings import settings


def _headers() -> dict:
    return {
        "apikey":        settings.ST_SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.ST_SUPABASE_SECRET_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def save_bet(bet: dict) -> dict:
    """
    Insert a new row into v2_bets. Expects keys matching the table's
    columns (session_id, fixture_id, home_team, etc — see schema).

    Returns the inserted row (including its generated id).
    """
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets", json=bet)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


def update_bet(bet_id: str, fields: dict) -> None:
    """
    Update an existing v2_bets row by id — used later for settlement
    (actual_outcome, pnl, settled_at).
    """
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.patch(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={"id": f"eq.{bet_id}"},
            json=fields,
        )
    resp.raise_for_status()


def log_step(
    session_id: str,
    step_type: str,
    tool: str,
    bet_id: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    response: str | None = None,
) -> None:
    """
    Insert one row into v2_logs — one call per LLM invocation or tool call.
    'tool' is either the agent's own name (e.g. "betting", "reasoning") for
    its own thinking steps, or the actual tool name (e.g. "consult_tactics")
    for a sub-call made during a ReAct loop.
    """
    row = {
        "session_id": session_id,
        "step_type":  step_type,
        "tool":       tool,
        "bet_id":     bet_id,
        "model":      model,
        "prompt":     prompt,
        "response":   response,
    }
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/v2_logs", json=row)
    resp.raise_for_status()

def get_recent_bets(limit: int = 10) -> list[dict]:
    """Most recent bets, newest first — used for the betting agent's track record."""
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
        )
    resp.raise_for_status()
    return resp.json()


def get_bets_by_edge_range(min_edge: float, max_edge: float) -> list[dict]:
    """Settled bets within an edge range — used to build calibration summaries."""
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={
                "select": "*",
                "edge_pp": f"gte.{min_edge}",
                "actual_outcome": "not.is.null",
            },
        )
    resp.raise_for_status()
    rows = resp.json()
    return [r for r in rows if r["edge_pp"] <= max_edge]