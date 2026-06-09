"""
ledger/logger.py

Posts reasoning records to the Stair AI Arena ledger.
Every observation, thinking step, and action gets recorded here.
This is what the Arena uses to score the agent.

Record types:
    Observing  - data the agent read (API calls, DB queries)
    Thinking   - LLM reasoning calls
    Acting     - decisions the agent took (prediction, order)
"""

from __future__ import annotations
import time
import uuid
import requests
from config import settings


# --- Constants ---------------------------------------------------------------

LEDGER_ENDPOINT = f"{settings.ARENA}/api/v1/arena/ledger/records/batch"
SCHEMA_VERSION  = settings.LEDGER_SCHEMA_VERSION


# --- Record builders ---------------------------------------------------------

def _base(session_id: str, behavior: str, **fields) -> dict:
    """Build a base ledger record."""
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id":      str(uuid.uuid4()),
        "session_id":     session_id,
        "behavior":       behavior,
        "client_ts_utc":  int(time.time() * 1000),   # milliseconds
        **fields,
    }

def observing(
    session_id:   str,
    description:  str,
    source:       str,
    upstream_ids: list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "Observing",
        trigger_source            = source,
        trigger_type              = "data_fetch",
        trigger_description       = description,
        trigger_payload_summary   = description,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


def thinking(
    session_id:     str,
    prompt:         str,
    output_payload: dict | str,
    model_name:     str,
    tokens_in:      int | None,
    tokens_out:     int | None,
    internal_reasoning: str | None = None,
    upstream_ids:   list[str] | None = None,
    inputs:         list[dict] | None = None,
) -> dict:
    """
    Record a Gemini reasoning call.

    Args:
        session_id:          current session UUID
        prompt:              system prompt used (truncated to 16000 chars)
        output_payload:      what Gemini returned
        model_name:          e.g. "gemini-2.5-flash"
        tokens_in:           prompt token count
        tokens_out:          completion token count
        internal_reasoning:  Gemini thinking trace
        upstream_ids:        record_ids this thinking depends on
        inputs:              list of {input_record_id, input_payload} dicts
    """
    mi = {
        "provider":   "gemini",
        "model_name": model_name,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
    }
    if internal_reasoning:
        mi["internal_reasoning"] = internal_reasoning

    record = _base(
        session_id, "Thinking",
        model_invocation = mi,
        prompt           = prompt[:16000],
        output_payload   = _truncate(output_payload),
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    if inputs:
        record["inputs"] = inputs
    return record


def acting(
    session_id:       str,
    action_type:      str,
    action_summary:   str,
    parameters:       dict,
    execution_status: str,
    target_system:    str = "arena",
    execution_id:     str | None = None,
    upstream_ids:     list[str] | None = None,
    dry_run:          bool = False,
) -> dict:
    # ensure fixture_id is always a string
    safe_params = {
        k: str(v) if k == "fixture_id" else v
        for k, v in parameters.items()
    }
    record = _base(
        session_id, "Acting",
        action_type      = action_type,
        target_system    = target_system,
        action_summary   = action_summary,
        parameters       = safe_params,
        dry_run          = dry_run,
        execution_status = execution_status,
    )
    if execution_id:
        record["execution_id"] = execution_id
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


def tool_calling(
    session_id:    str,
    tool_name:     str,
    params:        dict,
    result_summary: str,
    success:       bool = True,
    upstream_ids:  list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "ToolCalling",
        tool_meta      = {"name": tool_name},
        description    = f"Tool call: {tool_name}",
        input_payload  = _truncate(params),
        output_payload = _truncate(result_summary),
        success        = success,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


def planning(
    session_id:  str,
    description: str,
    plan:        str,
    upstream_ids: list[str] | None = None,
) -> dict:
    """
    Record a planning step — what the agent decided to do next.
    """
    record = _base(
        session_id, "Planning",
        description = description,
        plan        = plan,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


def reflecting(
    session_id:  str,
    description: str,
    reflection:  str,
    upstream_ids: list[str] | None = None,
) -> dict:
    """
    Record a reflection — post-match review or LTM update.
    """
    record = _base(
        session_id, "Reflecting",
        description = description,
        reflection  = reflection,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record

# --- Batch submit ------------------------------------------------------------

def submit(records: list[dict]) -> dict:
    """
    Submit a batch of ledger records to the Arena.

    Args:
        records: list of record dicts built by observing/thinking/acting

    Returns:
        {
            "success":  bool,
            "stored":   int,
            "errors":   list,
            "response": dict | None,
        }
    """
    if not records:
        return {"success": True, "stored": 0, "errors": [], "response": None}

    try:
        r = requests.post(
            LEDGER_ENDPOINT,
            headers = settings.H_ARENA,
            json    = {"records": records},
            timeout = 60,
        )

        if r.status_code == 404:
            # expected on staging when ledger endpoint not yet live
            return {
                "success":  True,
                "stored":   0,
                "errors":   [],
                "response": {"note": "ledger endpoint not live on staging (404)"},
            }

        if r.ok:
            resp = r.json()
            return {
                "success":  True,
                "stored":   len(resp.get("records", [])),
                "errors":   resp.get("errors", []),
                "response": resp,
            }

        return {
            "success":  False,
            "stored":   0,
            "errors":   [{"message": r.text[:300]}],
            "response": None,
        }

    except Exception as e:
        return {
            "success":  False,
            "stored":   0,
            "errors":   [{"message": str(e)}],
            "response": None,
        }


# --- Helpers -----------------------------------------------------------------

def _truncate(obj, limit: int = 30000) -> str:
    """Truncate large payloads before logging."""
    import json
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    if len(s) <= limit:
        return s
    return s[:limit] + f"...[truncated, was {len(s)} chars]"