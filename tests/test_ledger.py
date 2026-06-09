"""
tests/test_ledger.py

Tests for ledger/logger.py and ledger/reader.py
Run with: pytest tests/test_ledger.py -v
"""

import pytest
from ledger.logger import (
    observing, thinking, acting, submit, _truncate,
    tool_calling, planning, reflecting,
)


# --- observing ---------------------------------------------------------------

def test_observing_has_required_keys():
    rec = observing("sess-001", "Fetched fixture", "sportmonks_proxy")
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "description", "source"]:
        assert key in rec


def test_observing_behavior_is_observing():
    rec = observing("sess-001", "test", "test_source")
    assert rec["behavior"] == "Observing"


def test_observing_unique_record_ids():
    r1 = observing("s1", "test", "src")
    r2 = observing("s1", "test", "src")
    assert r1["record_id"] != r2["record_id"]


def test_observing_with_upstream():
    rec = observing("s1", "test", "src", upstream_ids=["abc", "def"])
    assert rec["upstream_record_id"] == ["abc", "def"]


# --- thinking ----------------------------------------------------------------

def test_thinking_has_required_keys():
    rec = thinking(
        session_id     = "s1",
        prompt         = "test prompt",
        output_payload = {"result": "ok"},
        model_name     = "gemini-2.5-flash",
        tokens_in      = 100,
        tokens_out     = 50,
    )
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "model_invocation",
                "prompt", "output_payload"]:
        assert key in rec


def test_thinking_behavior_is_thinking():
    rec = thinking("s1", "prompt", {}, "gemini-2.5-flash", 100, 50)
    assert rec["behavior"] == "Thinking"


def test_thinking_model_invocation_shape():
    rec = thinking("s1", "prompt", {}, "gemini-2.5-flash", 100, 50)
    mi  = rec["model_invocation"]
    assert mi["provider"]   == "gemini"
    assert mi["model_name"] == "gemini-2.5-flash"
    assert mi["tokens_in"]  == 100
    assert mi["tokens_out"] == 50


def test_thinking_with_internal_reasoning():
    rec = thinking("s1", "p", {}, "gemini-2.5-flash", 10, 5,
                   internal_reasoning="I thought about this...")
    assert "internal_reasoning" in rec["model_invocation"]


def test_thinking_prompt_truncated():
    long_prompt = "x" * 20000
    rec = thinking("s1", long_prompt, {}, "gemini-2.5-flash", 10, 5)
    assert len(rec["prompt"]) <= 16000


# --- acting ------------------------------------------------------------------

def test_acting_has_required_keys():
    rec = acting(
        session_id       = "s1",
        action_type      = "prediction",
        action_summary   = "Predict home win",
        parameters       = {"outcome": "home"},
        execution_status = "confirmed",
    )
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "action_type",
                "action_summary", "parameters", "execution_status"]:
        assert key in rec


def test_acting_behavior_is_acting():
    rec = acting("s1", "prediction", "test", {}, "confirmed")
    assert rec["behavior"] == "Acting"


def test_acting_with_execution_id():
    rec = acting("s1", "open_order", "place bet", {}, "pending",
                 execution_id="order-123")
    assert rec["execution_id"] == "order-123"


# --- tool_calling ------------------------------------------------------------

def test_tool_calling_has_required_keys():
    rec = tool_calling(
        "s1", "supabase.get_h2h",
        {"home": "Mexico", "away": "South Africa"},
        "No h2h data found",
    )
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "tool_name", "params"]:
        assert key in rec


def test_tool_calling_behavior():
    rec = tool_calling("s1", "test_tool", {}, "result")
    assert rec["behavior"] == "ToolCalling"


def test_tool_calling_with_upstream():
    rec = tool_calling("s1", "tool", {}, "result",
                       upstream_ids=["rec-001"])
    assert rec["upstream_record_id"] == ["rec-001"]


# --- planning ----------------------------------------------------------------

def test_planning_has_required_keys():
    rec = planning("s1", "Deciding fetch order",
                   "Fetch Sportmonks first, then Polymarket")
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "description", "plan"]:
        assert key in rec


def test_planning_behavior():
    rec = planning("s1", "test", "plan")
    assert rec["behavior"] == "Planning"


# --- reflecting --------------------------------------------------------------

def test_reflecting_has_required_keys():
    rec = reflecting("s1", "Post-match review",
                     "Bet lost — market was right, ML model was wrong")
    for key in ["schema_version", "record_id", "session_id",
                "behavior", "timestamp", "description", "reflection"]:
        assert key in rec


def test_reflecting_behavior():
    rec = reflecting("s1", "test", "reflection")
    assert rec["behavior"] == "Reflecting"


# --- _truncate ---------------------------------------------------------------

def test_truncate_short_string():
    assert _truncate("hello") == "hello"


def test_truncate_long_string():
    long = "x" * 40000
    result = _truncate(long)
    assert len(result) < 40000
    assert "truncated" in result


def test_truncate_dict():
    result = _truncate({"key": "value"})
    assert isinstance(result, str)
    assert "key" in result


# --- submit ------------------------------------------------------------------

def test_submit_empty_list():
    result = submit([])
    assert result["success"] is True
    assert result["stored"]  == 0


def test_submit_returns_correct_shape():
    result = submit([])
    for key in ["success", "stored", "errors", "response"]:
        assert key in result


def test_submit_single_record():
    rec    = observing("test-session", "test observation", "test_source")
    result = submit([rec])
    assert result["success"] is True