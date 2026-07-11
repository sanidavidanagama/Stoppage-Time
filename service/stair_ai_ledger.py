# service/stair_ai_ledger.py
"""
service/stair_ai_ledger.py

Submits reasoning records to Stair AI's Reasoning Ledger.
All 7 behaviors, shapes confirmed via /records/validate in Postman.
"""

import time
import uuid
import httpx
from config.settings import settings

RECORDS_URL = f"{settings.ARENA}/api/v1/arena/ledger/records/batch"
VALIDATE_URL = f"{settings.ARENA}/api/v1/arena/ledger/records/validate"


def _ts() -> int:
    return int(time.time() * 1000)


def _rid() -> str:
    return str(uuid.uuid4())


def _post(url: str, records: list[dict], fixture_id: str | None = None) -> dict:
    payload = {"records": records}
    if fixture_id:
        payload["fixture_id"] = str(fixture_id)
    with httpx.Client(headers=settings.H_ARENA, timeout=30) as client:
        resp = client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def submit_records(records: list[dict], fixture_id: str | None = None) -> dict:
    """Real submission — persists to the Ledger."""
    return _post(RECORDS_URL, records, fixture_id)


def validate_records(records: list[dict], fixture_id: str | None = None) -> dict:
    """Dry-run check — does not persist anything."""
    return _post(VALIDATE_URL, records, fixture_id)


# --- Observing ---------------------------------------------------------------

def observing(session_id: str, description: str, source: str, fixture_id: str | None = None) -> list[dict]:
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Observing",
        "client_ts_utc": _ts(),
        "trigger_source": source,
        "trigger_type": "cron_trigger",
        "trigger_description": description,
        "trigger_payload_summary": description,
    }]


# --- ToolCalling ---------------------------------------------------------------

def tool_calling(session_id, upstream_id, tool_name, params, result_summary, success=True):
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "ToolCalling",
        "client_ts_utc": _ts(),
        "upstream_record_id": [upstream_id] if upstream_id else [],
        "tool_meta": {"tool_name": tool_name, **params},
        "description": result_summary,
        "success": success,
    }]


# --- Thinking ---------------------------------------------------------------

def thinking(session_id: str, upstream_id: str | None, model_name: str, internal_reasoning: str, prompt: str, output_payload: str) -> list[dict]:
    provider = "anthropic" if "claude" in model_name.lower() else "google" if "gemini" in model_name.lower() else "unknown"
    rec = {
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Thinking",
        "client_ts_utc": _ts(),
        "inputs": [],
        "model_invocation": {"provider": provider, "model_name": model_name, "internal_reasoning": internal_reasoning},
        "prompt": prompt,
        "output_payload": output_payload,
    }
    if upstream_id:
        rec["upstream_record_id"] = [upstream_id]
    return [rec]


# --- Acting: prediction (no agent_id) ---------------------------------------

def acting_prediction(session_id: str, fixture_id: str, outcome: str, probability: float, notes: str = "") -> list[dict]:
    probability = max(0.001, min(0.999, probability))
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Acting",
        "client_ts_utc": _ts(),
        "action_type": "prediction",
        "target_system": "arena",
        "action_summary": f"Predict {outcome} @ {probability:.3f} for {fixture_id}",
        "parameters": {"fixture_id": str(fixture_id), "outcome": outcome, "probability": probability},
        "notes": notes,
        "dry_run": False,
        "execution_status": "confirmed",
    }]


# --- Acting: order -----------------------------------------------------------

def acting_order(session_id: str, upstream_id: str, fixture_id: str, team_code: str, usd_size: float, summary: str) -> list[dict]:
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Acting",
        "client_ts_utc": _ts(),
        "upstream_record_id": [upstream_id] if upstream_id else [],
        "action_type": "order",
        "target_system": "polymarket",
        "action_summary": summary,
        "parameters": {"fixture_id": str(fixture_id), "team_code": team_code, "usd_size": f"{usd_size:.2f}"},
        "dry_run": False,
        "execution_status": "confirmed",
    }]


# --- Planning ---------------------------------------------------------------

def planning(session_id, goal, steps):
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Planning",
        "client_ts_utc": _ts(),
        "goal": goal,
        "steps": [{"index": i, "description": s} for i, s in enumerate(steps)],
    }]

# --- Reflecting ---------------------------------------------------------------

def reflecting(session_id: str, upstream_id: str, output_payload: str) -> list[dict]:
    return [{
        "schema_version": settings.LEDGER_SCHEMA_VERSION,
        "agent_id": settings.AGENT_ID,
        "record_id": _rid(),
        "session_id": session_id,
        "behavior": "Reflecting",
        "client_ts_utc": _ts(),
        "inputs": [upstream_id] if upstream_id else [],
        "output_payload": output_payload,
    }]