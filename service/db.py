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
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.patch(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={"id": f"eq.{bet_id}"},
            json=fields,
        )
    print("STATUS:", resp.status_code, "BODY:", resp.text)  # temporary debug
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

def get_recent_bets(limit: int = 10, exclude_test: bool = True) -> list[dict]:
    params = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
    if exclude_test:
        params["session_id"] = "not.like.test-%"
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets", params=params)
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

def get_pending_bets() -> list[dict]:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={
                "select": "*",
                "actual_outcome": "is.null",
                "fixture_id": "not.is.null",
            },
        )
    resp.raise_for_status()
    return resp.json()

def get_current_personality() -> str:
    """
    Fetch the most recent personality-note update from v2_logs.
    Returns a default message if none exists yet.
    """
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_logs",
            params={
                "select": "response,created_at",
                "tool": "eq.memory",
                "order": "created_at.desc",
                "limit": "1",
            },
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["response"] if rows else "No prior self-reflection yet — this is a fresh start."


def save_personality_update(bet_id: str, session_id: str, personality_text: str) -> None:
    """
    Saves a new personality-note version as a v2_logs row (tool='memory').
    Old versions are never deleted — get_current_personality always reads
    the most recent one.
    """
    log_step(
        session_id=session_id,
        step_type="Reflecting",
        tool="memory",
        bet_id=bet_id,
        response=personality_text,
    )


def get_bet_by_id(bet_id: str) -> dict | None:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_bets",
            params={"select": "*", "id": f"eq.{bet_id}"},
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_logs_for_bet(bet_id: str) -> list[dict]:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/v2_logs",
            params={"select": "*", "bet_id": f"eq.{bet_id}", "order": "created_at.asc"},
        )
    resp.raise_for_status()
    return resp.json()