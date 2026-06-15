from fastapi import APIRouter, Depends, HTTPException

from backend.auth import get_current_user

router = APIRouter(tags=["logs"], dependencies=[Depends(get_current_user)])

LOG_TYPES = [
    "tactics_prompt",
    "tactics_response",
    "reasoning_prompt",
    "reasoning_response",
    "bet_prompt",
    "bet_response",
]


def _sb():
    from config import settings
    from supabase import create_client
    return create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)


def fetch_logs_by_session(sb, session_id: str) -> dict:
    """
    Shared helper: query logs table by session_id and return structured dict.
    Raises 404 if no logs exist for the session.
    """
    res = (
        sb.table("logs")
        .select("log_type,round,content")
        .eq("session_id", session_id)
        .order("round")
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="No logs found for this session")

    structured: dict = {lt: [] for lt in LOG_TYPES}
    for row in res.data:
        lt = row.get("log_type")
        if lt in structured:
            structured[lt].append({"round": row["round"], "content": row["content"]})
    return structured


# ---------------------------------------------------------------------------
# GET /api/logs  — list all sessions that have logs
# ---------------------------------------------------------------------------

@router.get("/logs")
async def list_log_sessions():
    """
    List every distinct session that has log entries.
    Includes sessions where no bet was placed (should_bet=0 or run crashed).
    Ordered by most recent first.
    """
    sb = _sb()

    # Fetch all log rows (lightweight cols only) to group in Python
    logs_res = (
        sb.table("logs")
        .select("session_id,fixture_name,log_type,created_at")
        .order("created_at", desc=True)
        .execute()
    )

    # Group by session_id — keep first-seen fixture_name and earliest created_at
    sessions: dict = {}
    log_types_map: dict = {}
    for row in (logs_res.data or []):
        sid = row["session_id"]
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "fixture_name": row.get("fixture_name"),
                "created_at": row.get("created_at"),
            }
            log_types_map[sid] = set()
        log_types_map[sid].add(row["log_type"])

    if not sessions:
        return []

    # Look up matching bet records (one query)
    bets_res = (
        sb.table("bets")
        .select("id,session_id,should_bet")
        .in_("session_id", list(sessions.keys()))
        .execute()
    )
    bet_map = {r["session_id"]: r for r in (bets_res.data or [])}

    result = []
    for sid, session in sessions.items():
        bet = bet_map.get(sid)
        result.append({
            **session,
            "log_types": sorted(log_types_map[sid]),
            "log_count": len(log_types_map[sid]),
            "has_bet": bet is not None,
            "bet_placed": bool(bet and bet.get("should_bet") == 1),
            "bet_id": bet["id"] if bet else None,
        })

    return result


# ---------------------------------------------------------------------------
# GET /api/logs/{session_id}  — get all logs for a session directly
# ---------------------------------------------------------------------------

@router.get("/logs/{session_id:path}")
async def get_session_logs(session_id: str):
    """
    Fetch all logs for a session_id directly — no bet_id required.
    Works even when no bet was placed.

    session_id format: prematch:{fixture_id}  e.g. prematch:19609162
    URL-encode the colon: /api/logs/prematch%3A19609162
    """
    sb = _sb()
    structured = fetch_logs_by_session(sb, session_id)

    # Optionally attach the bet_id if one exists
    bet_res = sb.table("bets").select("id,should_bet").eq("session_id", session_id).execute()
    bet = bet_res.data[0] if bet_res.data else None

    return {
        "session_id": session_id,
        "bet_id": bet["id"] if bet else None,
        "bet_placed": bool(bet and bet.get("should_bet") == 1),
        "logs": structured,
    }


# ---------------------------------------------------------------------------
# DELETE /api/logs/{session_id}  — delete all logs for a session
# ---------------------------------------------------------------------------

@router.delete("/logs/{session_id:path}", status_code=204)
async def delete_session_logs(session_id: str):
    """
    Delete all log rows for a given session_id.
    Does NOT delete the corresponding bet record — only the logs.
    """
    sb = _sb()

    # Check logs exist before deleting
    check = (
        sb.table("logs")
        .select("session_id")
        .eq("session_id", session_id)
        .limit(1)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="No logs found for this session")

    sb.table("logs").delete().eq("session_id", session_id).execute()
