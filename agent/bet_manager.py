"""
agent/bet_manager.py

Bankroll management agent — a separate Gemini call.
Only called when the reasoning agent says should_bet = True.

Takes the prediction + LTM context and decides:
    - how much to bet
    - at what price
    - which team code to use for the order

Reasoning agent handles football analysis.
Bet manager handles money.
"""

from __future__ import annotations
import json
import re
from google import genai
from google.genai import types
from config import settings
from agent.memory.ltm import get_bankroll_summary, get_ltm_context
from agent.reasoning_logger import log_bet
from pathlib import Path


# --- Gemini client -----------------------------------------------------------

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --- System prompt -----------------------------------------------------------

_BET_MANAGER_PROMPT_PATH = Path(__file__).parent / "prompts" / "bet_manager_prompt.md"

def _load_bet_manager_prompt(ltm_context: str = "") -> str:
    prompt = _BET_MANAGER_PROMPT_PATH.read_text(encoding="utf-8")
    return prompt.replace("{ltm_context}", ltm_context or "No past performance data available.")

# --- Main call ---------------------------------------------------------------

def decide(
    prediction:  dict,
    live_prices: dict,
    home_code:   str,
    away_code:   str,
) -> dict:
    """
    Make bet sizing decision via Gemini.
    Only call this when reasoning agent says should_bet = True.

    Args:
        prediction:  final_decision dict from reasoning.py
        live_prices: live_prices dict from data/polymarket.py
        home_code:   e.g. "MEX"
        away_code:   e.g. "ZAF"

    Returns:
        Bet decision dict with size, limit_price, team_code.
    """
    # get bankroll context from LTM
    bankroll = get_bankroll_summary()
    ltm      = get_ltm_context(ml_market_gap=None)

    payload = {
        "prediction":      prediction,
        "live_prices":     live_prices,
        "home_code":       home_code,
        "away_code":       away_code,
        "current_balance": bankroll["current_balance"],
    }
    system_prompt    = _load_bet_manager_prompt(ltm_context=ltm)
    prompt_snapshot  = _build_prompt_snapshot(payload, system_prompt)

    try:
        client   = _get_client()
        response = client.models.generate_content(
            model    = settings.GEMINI_MODEL,
            contents = json.dumps(payload, default=str),
            config   = types.GenerateContentConfig(
                system_instruction = system_prompt,
                max_output_tokens  = 600,
                thinking_config    = types.ThinkingConfig(
                    include_thoughts = True,
                    thinking_budget  = 512,
                ),
            ),
        )

        raw      = _extract_text(response)
        thinking = _extract_thinking(response)
        log_bet(prompt_snapshot, _format_response_snapshot(thinking, raw))
        result   = _parse_json(raw)

        if result is None:
            result = _fallback_decision(prediction, live_prices, home_code, away_code, bankroll)
            if result is None:
                return _skip("Gemini returned unparseable JSON")
            result["rationale"] = f"Fallback decision used after unparseable Gemini JSON. {result['rationale']}"

        # --- hard safety limits ------------------------------------------
        # cap size
        if (result.get("size_usdc") or 0) > settings.MAX_BET_SIZE:
            result["size_usdc"] = settings.MAX_BET_SIZE

        # never more than 5% of bankroll
        max_from_bankroll = round(bankroll["current_balance"] * 0.05, 2)
        if (result.get("size_usdc") or 0) > max_from_bankroll:
            result["size_usdc"] = max_from_bankroll

        # recover missing team_code from the chosen outcome
        if result.get("team_code") not in [home_code, away_code, "draw"]:
            if result.get("outcome") == "home":
                result["team_code"] = home_code
            elif result.get("outcome") == "away":
                result["team_code"] = away_code
            elif result.get("outcome") == "draw":
                result["team_code"] = "draw"

        # validate team_code
        if result.get("team_code") not in [home_code, away_code, "draw"]:
            return _skip(f"Invalid team_code: {result.get('team_code')}")

        result["_thinking"]  = thinking
        result["_available"] = True
        return result

    except Exception as e:
        log_bet(prompt_snapshot, f"EXCEPTION\n\n{e}")
        return _skip(str(e))


# --- Helpers -----------------------------------------------------------------

def _extract_text(response) -> str:
    parts = []
    for part in response.candidates[0].content.parts:
        if not getattr(part, "thought", False):
            parts.append(getattr(part, "text", "") or "")
    return "\n".join(parts)


def _extract_thinking(response) -> str:
    parts = []
    for part in response.candidates[0].content.parts:
        if getattr(part, "thought", False):
            parts.append(getattr(part, "text", "") or "")
    return "\n".join(parts)


def _build_prompt_snapshot(payload: dict, system_prompt: str) -> str:
    return (
        "# System Prompt\n\n"
        + system_prompt
        + "\n\n# User Payload\n\n```json\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n```\n"
    )


def _format_response_snapshot(thinking: str, raw: str) -> str:
    return (
        "# Thinking\n\n"
        + (thinking or "")
        + "\n\n# Raw Response\n\n"
        + (raw or "")
    )


def _parse_json(raw: str) -> dict | None:
    clean = re.sub(r"```json\s*", "", raw)
    clean = re.sub(r"```\s*",     "", clean)
    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _fallback_decision(
    prediction: dict,
    live_prices: dict,
    home_code: str,
    away_code: str,
    bankroll: dict,
) -> dict | None:
    outcome = prediction.get("outcome")
    if outcome not in ["home", "away", "draw"]:
        return None

    market_mid = live_prices.get(outcome)
    if market_mid is None:
        return None

    agent_prob = float(prediction.get("probability") or 0)
    edge_pp = round((agent_prob - float(market_mid)) * 100, 1)

    if abs(edge_pp) < settings.MIN_EDGE_PP:
        return _skip(f"Edge below threshold: {edge_pp}pp")

    confidence = (prediction.get("confidence_level") or "medium").lower()
    if abs(edge_pp) >= 15:
        size_usdc = 4.0
    else:
        size_usdc = 1.5

    if confidence == "low":
        size_usdc *= 0.5
    elif confidence == "high":
        size_usdc *= 1.5

    size_usdc = round(min(size_usdc, settings.MAX_BET_SIZE, round(bankroll["current_balance"] * 0.05, 2)), 2)
    if size_usdc <= 0:
        return _skip("Bankroll cap reduced size to zero")

    if outcome == "home":
        team_code = home_code
    elif outcome == "away":
        team_code = away_code
    else:
        team_code = "draw"
    limit_price = round(min(max(float(market_mid) + 0.015, 0.01), 0.99), 3)

    return {
        "_available": True,
        "should_place_order": True,
        "team_code": team_code,
        "outcome": outcome,
        "size_usdc": size_usdc,
        "limit_price": limit_price,
        "edge_pp": edge_pp,
        "direction": "long",
        "rationale": (
            f"Heuristic fallback: edge {edge_pp}pp on {outcome}, "
            f"size {size_usdc:.2f}, limit {limit_price:.3f}."
        ),
    }


def _skip(reason: str) -> dict:
    return {
        "_available":       False,
        "should_place_order": False,
        "team_code":        None,
        "outcome":          None,
        "size_usdc":        0.0,
        "limit_price":      0.0,
        "edge_pp":          0.0,
        "direction":        "long",
        "rationale":        f"Skipped: {reason}",
    }