from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.scheduler import run_queue_entry_now

router = APIRouter(tags=["queue"], dependencies=[Depends(get_current_user)])


def _sb():
    from config import settings
    from supabase import create_client
    return create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)


def _add_countdowns(entry: dict) -> dict:
    now = datetime.now(timezone.utc)
    entry = dict(entry)
    for field, key in [
        ("scheduled_run_time", "seconds_until_run"),
        ("kickoff_time", "seconds_until_kickoff"),
    ]:
        value = entry.get(field)
        if value:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                entry[key] = max(0, int((dt - now).total_seconds()))
            except (ValueError, TypeError):
                entry[key] = None
        else:
            entry[key] = None
    return entry


# ---------------------------------------------------------------------------
# GET /api/queue
# ---------------------------------------------------------------------------

@router.get("/queue")
async def list_queue():
    res = _sb().table("match_queue").select("*").order("scheduled_run_time").execute()
    return [_add_countdowns(e) for e in (res.data or [])]


# ---------------------------------------------------------------------------
# POST /api/queue
# ---------------------------------------------------------------------------

class QueueEntry(BaseModel):
    home_team: str
    away_team: str
    kickoff_time: str  # ISO 8601 UTC


@router.post("/queue", status_code=201)
async def add_to_queue(body: QueueEntry):
    kickoff_dt = datetime.fromisoformat(body.kickoff_time.replace("Z", "+00:00"))
    scheduled_dt = kickoff_dt - timedelta(minutes=45)

    res = _sb().table("match_queue").insert({
        "home_team": body.home_team,
        "away_team": body.away_team,
        "kickoff_time": kickoff_dt.isoformat(),
        "scheduled_run_time": scheduled_dt.isoformat(),
        "status": "pending",
    }).execute()

    return _add_countdowns(res.data[0])


# ---------------------------------------------------------------------------
# DELETE /api/queue/{entry_id}
# ---------------------------------------------------------------------------

@router.delete("/queue/{entry_id}", status_code=204)
async def remove_from_queue(entry_id: str):
    sb = _sb()
    res = sb.table("match_queue").select("status").eq("id", entry_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    if res.data[0]["status"] == "running":
        raise HTTPException(status_code=409, detail="Cannot remove a running entry")
    sb.table("match_queue").delete().eq("id", entry_id).execute()


# ---------------------------------------------------------------------------
# POST /api/queue/{entry_id}/run
# ---------------------------------------------------------------------------

@router.post("/queue/{entry_id}/run")
async def run_now(entry_id: str):
    """Manually trigger a queue entry immediately, bypassing the countdown."""
    result = await run_queue_entry_now(entry_id)
    return _add_countdowns(result)
