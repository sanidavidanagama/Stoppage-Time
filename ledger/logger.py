"""
ledger/logger.py

Posts reasoning records to the Stair AI Arena ledger.
All 7 behavior types supported and tested.

Rules learned from testing:
    - prediction Acting records: NO agent_id (server resolves from API key)
    - all other records: include agent_id
    - execution_status: confirmed | failed | simulated | pending
    - trigger_type: cron_trigger | signal_trigger
    - Thinking.inputs: required array (can be empty)
    - Planning: needs goal + steps array
    - Reflecting: needs inputs array + output_payload string
"""

from __future__ import annotations
import time
import uuid
import requests
from config import settings

LEDGER_ENDPOINT = f"{settings.ARENA}/api/v1/arena/ledger/records/batch"
SCHEMA_VERSION  = settings.LEDGER_SCHEMA_VERSION
LEDGER_BATCH_SIZE = 4


# --- Base record builder -----------------------------------------------------

def _base(session_id: str, behavior: str, include_agent_id: bool = True, **fields) -> dict:
    rec = {
        "schema_version": SCHEMA_VERSION,
        "record_id":      str(uuid.uuid4()),
        "session_id":     session_id,
        "behavior":       behavior,
        "client_ts_utc":  int(time.time() * 1000),
    }
    if include_agent_id:
        rec["agent_id"] = settings.AGENT_ID
    rec.update({k: v for k, v in fields.items() if v is not None})
    return rec


# --- Observing ---------------------------------------------------------------

def observing(
    session_id:   str,
    description:  str,
    source:       str,
    upstream_ids: list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "Observing",
        trigger_source          = source,
        trigger_type            = "cron_trigger",
        trigger_description     = description,
        trigger_payload_summary = description,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- ToolCalling -------------------------------------------------------------

def tool_calling(
    session_id:     str,
    tool_name:      str,
    params:         dict,
    result_summary: str,
    success:        bool = True,
    upstream_ids:   list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "ToolCalling",
        tool_meta      = {"name": tool_name},
        description    = f"{tool_name}",
        input_payload  = params,
        output_payload = {"summary": result_summary[:2000]},
        success        = success,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Planning ----------------------------------------------------------------

def planning(
    session_id:   str,
    goal:         str,
    steps:        list[str],
    upstream_ids: list[str] | None = None,
) -> dict:
    steps_list = [
        {"index": i, "description": s}
        for i, s in enumerate(steps)
    ]
    record = _base(
        session_id, "Planning",
        goal  = goal,
        steps = steps_list,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Thinking ----------------------------------------------------------------

def thinking(
    session_id:         str,
    prompt:             str,
    output_payload:     dict | str,
    model_name:         str,
    tokens_in:          int | None,
    tokens_out:         int | None,
    internal_reasoning: str | None = None,
    upstream_ids:       list[str] | None = None,
    inputs:             list[dict] | None = None,
) -> dict:
    mi = {
        "provider":   "gemini",
        "model_name": model_name,
    }
    if tokens_in is not None:
        mi["tokens_in"] = tokens_in
    if tokens_out is not None:
        mi["tokens_out"] = tokens_out
    if internal_reasoning:
        mi["internal_reasoning"] = internal_reasoning

    record = _base(
        session_id, "Thinking",
        model_invocation = mi,
        prompt           = prompt[:16000],
        inputs           = inputs or [],
        output_payload   = _truncate(output_payload),
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Acting ------------------------------------------------------------------

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
    # prediction records must NOT include agent_id
    is_prediction = action_type == "prediction"
    record = _base(
        session_id, "Acting",
        include_agent_id = not is_prediction,
        action_type      = action_type,
        target_system    = target_system,
        action_summary   = action_summary,
        parameters       = parameters,
        dry_run          = dry_run,
        execution_status = execution_status,
    )
    if execution_id:
        record["execution_id"] = execution_id
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Reflecting --------------------------------------------------------------

def reflecting(
    session_id:    str,
    reflection:    str,
    input_payload: str,
    upstream_ids:  list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "Reflecting",
        inputs         = [{"input_payload": input_payload}],
        output_payload = reflection,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Other -------------------------------------------------------------------

def other(
    session_id: str,
    label:      str,
    data:       dict,
    upstream_ids: list[str] | None = None,
) -> dict:
    record = _base(
        session_id, "Other",
        label = label,
        data  = data,
    )
    if upstream_ids:
        record["upstream_record_id"] = upstream_ids
    return record


# --- Submit ------------------------------------------------------------------

def submit(records: list[dict], fixture_id: str | None = None) -> dict:
    if not records:
        return {"success": True, "stored": 0, "errors": [], "response": None}

    batch_size = 1
    stored = 0
    errors: list[dict] = []
    responses: list[dict] = []

    for batch_start in range(0, len(records), batch_size):
        batch = records[batch_start:batch_start + batch_size]
        payload = {"records": batch}
        if fixture_id:
            payload["fixture_id"] = fixture_id

        try:
            r = requests.post(
                LEDGER_ENDPOINT,
                headers = settings.H_ARENA,
                json    = payload,
                timeout = 60,
            )
            if r.status_code == 404:
                return {"success": True, "stored": stored, "errors": errors,
                        "response": {"note": "ledger endpoint not live (404)"}}

            if not r.ok:
                errors.append({
                    "batch_start": batch_start,
                    "message": r.text[:1000],
                    "status_code": r.status_code,
                })
                continue

            resp = r.json()
            stored += len(resp.get("records", []))

            for err in resp.get("errors", []):
                err_copy = dict(err)
                if isinstance(err_copy.get("index"), int):
                    err_copy["index"] = err_copy["index"] + batch_start
                errors.append(err_copy)

            responses.append(resp)
        except Exception as e:
            errors.append({
                "batch_start": batch_start,
                "message": str(e),
            })

    return {
        "success": len(errors) == 0,
        "stored":  stored,
        "errors":  errors,
        "response": responses,
    }


# --- Helpers -----------------------------------------------------------------

def _truncate(obj, limit: int = 30000) -> str:
    import json
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s[:limit] + "...[truncated]" if len(s) > limit else s