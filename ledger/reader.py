"""
ledger/reader.py

Reads past sessions from the Arena ledger.
Used by the orchestrator to populate LTM context
and verify past decisions.
"""

from __future__ import annotations
import requests
from config import settings


def get_sessions(limit: int = 10) -> list[dict]:
    """
    Fetch the most recent agent sessions from the ledger.

    Returns:
        List of session dicts or empty list on failure.
    """
    try:
        r = requests.get(
            f"{settings.ARENA}/api/v1/arena/ledger/sessions",
            headers = settings.H_ARENA,
            params  = {"limit": limit},
            timeout = 10,
        )
        if r.ok:
            return r.json().get("sessions", [])
        return []
    except Exception:
        return []


def get_session_records(session_id: str) -> list[dict]:
    """
    Fetch all records for a specific session.

    Returns:
        List of record dicts or empty list on failure.
    """
    try:
        r = requests.get(
            f"{settings.ARENA}/api/v1/arena/ledger/records",
            headers = settings.H_ARENA,
            params  = {"session_id": session_id},
            timeout = 10,
        )
        if r.ok:
            return r.json().get("records", [])
        return []
    except Exception:
        return []