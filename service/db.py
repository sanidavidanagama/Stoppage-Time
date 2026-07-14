import httpx
from datetime import datetime, timezone
from config.settings import settings


def _headers() -> dict:
    return {
        "apikey":        settings.ST_SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.ST_SUPABASE_SECRET_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def create_session(session_id: str, home_team: str, away_team: str, source: str = "v2") -> None:
    """Must be called FIRST, before any log or bet for this session — both
    agent_logs and agent_bets have a hard FK requiring the session to exist."""
    row = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fixture_name": f"{home_team} vs {away_team}",
        "home_team": home_team,
        "away_team": away_team,
        "status": "running",
        "source": source,
    }
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/sessions", json=row)
    resp.raise_for_status()


def update_session_status(session_id: str, status: str) -> None:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.patch(
            f"{settings.ST_SUPABASE_URL}/rest/v1/sessions",
            params={"session_id": f"eq.{session_id}"},
            json={"status": status},
        )
    resp.raise_for_status()


def log_step(session_id: str, step_type: str, tool: str, model: str = None,
             prompt: str = None, response: str = None) -> None:
    row = {
        "session_id": session_id, "step_type": step_type, "tool": tool,
        "model": model, "prompt": prompt, "response": response,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/agent_logs", json=row)
    resp.raise_for_status()


def save_bet(bet: dict) -> dict:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.post(f"{settings.ST_SUPABASE_URL}/rest/v1/agent_bets", json=bet)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


def update_bet(bet_id: str, fields: dict) -> None:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.patch(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_bets",
            params={"id": f"eq.{bet_id}"},
            json=fields,
        )
    resp.raise_for_status()


def get_recent_bets(limit: int = 10) -> list[dict]:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_bets",
            params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
        )
    resp.raise_for_status()
    return resp.json()


def get_pending_bets() -> list[dict]:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_bets",
            params={"select": "*", "actual_outcome": "is.null", "fixture_id": "not.is.null"},
        )
    resp.raise_for_status()
    return resp.json()


def get_bet_by_id(bet_id: str) -> dict | None:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_bets",
            params={"select": "*", "id": f"eq.{bet_id}"},
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def get_logs_for_bet(bet_id: str) -> list[dict]:
    """agent_logs has no bet_id column — join via the bet's session_id instead."""
    bet = get_bet_by_id(bet_id)
    if bet is None:
        return []
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_logs",
            params={"select": "*", "session_id": f"eq.{bet['session_id']}", "order": "created_at.asc"},
        )
    resp.raise_for_status()
    return resp.json()


def get_current_personality() -> str:
    with httpx.Client(headers=_headers(), timeout=15) as client:
        resp = client.get(
            f"{settings.ST_SUPABASE_URL}/rest/v1/agent_logs",
            params={"select": "response,created_at", "tool": "eq.memory", "order": "created_at.desc", "limit": "1"},
        )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["response"] if rows else "No prior self-reflection yet — this is a fresh start."


def save_personality_update(bet_id: str, session_id: str, personality_text: str) -> None:
    log_step(session_id=session_id, step_type="Reflecting", tool="memory", response=personality_text)