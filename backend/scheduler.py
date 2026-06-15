import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_executor = ThreadPoolExecutor(max_workers=2)


def start_scheduler() -> None:
    _scheduler.add_job(
        _poll_queue,
        trigger="interval",
        seconds=60,
        id="queue_poll",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — polling match_queue every 60s")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    _executor.shutdown(wait=False)
    logger.info("Scheduler stopped")


async def _poll_queue() -> None:
    from config import settings
    from supabase import create_client

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)
    now_iso = datetime.now(timezone.utc).isoformat()

    res = (
        sb.table("match_queue")
        .select("*")
        .eq("status", "pending")
        .lte("scheduled_run_time", now_iso)
        .execute()
    )
    rows = res.data or []

    for row in rows:
        asyncio.create_task(_run_queue_entry(sb, row))


async def _run_queue_entry(sb, row: dict) -> None:
    entry_id = row["id"]

    # Optimistic lock: only claim if still pending
    claim = (
        sb.table("match_queue")
        .update({"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", entry_id)
        .eq("status", "pending")
        .execute()
    )
    if not claim.data:
        return  # another process already claimed it

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            lambda: _run_orchestrator(row["home_team"], row["away_team"]),
        )
        sb.table("match_queue").update({
            "status": "done",
            "session_id": result.get("session_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", entry_id).execute()
        logger.info(f"Queue entry {entry_id} done — session={result.get('session_id')}")
    except Exception as exc:
        sb.table("match_queue").update({
            "status": "failed",
            "error_message": str(exc)[:500],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", entry_id).execute()
        logger.error(f"Queue entry {entry_id} failed: {exc}")


def _run_orchestrator(home: str, away: str) -> dict:
    from agent.orchestrator import run
    return run(home, away)


async def run_queue_entry_now(entry_id: str) -> dict:
    """Called by POST /api/queue/{id}/run — bypasses the countdown."""
    from config import settings
    from fastapi import HTTPException
    from supabase import create_client

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)

    res = sb.table("match_queue").select("*").eq("id", entry_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    row = res.data[0]
    if row["status"] == "running":
        raise HTTPException(status_code=409, detail="Entry is already running")
    if row["status"] in ("done", "failed"):
        raise HTTPException(status_code=409, detail=f"Entry is already {row['status']}")

    await _run_queue_entry(sb, row)

    updated = sb.table("match_queue").select("*").eq("id", entry_id).execute()
    return updated.data[0] if updated.data else row
