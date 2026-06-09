"""
agent/strategy.py

Bet sizing and trading decision — a separate Gemini call.
Takes the agent's prediction and live Polymarket prices.
Decides whether to trade, how much, and at what price.

The LLM reasons freely about edge and sizing.
We only enforce hard safety limits after the fact.

Note: Arena order API only supports BUY YES (long).
      Only home or away outcomes — no draw bets.
"""

from __future__ import annotations
import json
import re
from google import genai
from google.genai import types
from config import settings


# --- Gemini client -----------------------------------------------------------

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --- System prompt -----------------------------------------------------------

STRATEGY_PROMPT = """
You are a bankroll manager for a $100 demo account competing in the
Stair AI World Cup Agent Arena.

You receive the agent's own prediction and the current Polymarket prices.
Decide whether to place a bet and on what terms.

## Key concept: Edge

Edge = (agent's probability) - (market's implied probability) for the same outcome.
Positive edge = market underprices the pick = consider going LONG (buy YES).
Negative edge = market overprices the pick = consider going SHORT (fade it).

## Important constraints

1. The order API only supports BUY YES (long bets).
   - If you want to go LONG on home win  -> bet on home
   - If you want to go SHORT on home win -> go LONG on away instead
   - NEVER bet on draw — no draw bets allowed.
   - Only bet on home or away.

2. Size discipline (max $5 per trade, $100 wallet):
   - |edge| < 5pp  -> don't trade (noise)
   - |edge| 5-15pp -> $1-2 (modest)
   - |edge| > 15pp -> $3-5 (high conviction, cap $5)
   - Halve size if confidence is low
   - High confidence -> up to 1.5x size (still capped at $5)

3. limit_price is the worst price you'll accept per share (0..1):
   - Long: slightly above current mid (e.g. mid=0.685 -> limit=0.70)
   - Must leave room for execution

4. If Polymarket prices are unavailable -> skip, cannot price edge.

## Output (return ONLY this JSON — no prose, no code fences)

{
  "should_trade":  true | false,
  "team_code":     "MEX" | "ZAF" | null,
  "outcome":       "home" | "away" | null,
  "size_usdc":     float,
  "limit_price":   float,
  "edge_pp":       float,
  "rationale":     "1-3 sentences: state the edge, size logic, limit price logic"
}

Be conservative. Small wallet + weak conviction = skipping is valid.
"""


# --- Main call ---------------------------------------------------------------

def decide(
    prediction:  dict,
    live_prices: dict,
    home_code:   str,
    away_code:   str,
    event_slug:  str,
    bankroll:    float = 100.0,
) -> dict:
    """
    Make trading decision via Gemini.

    Args:
        prediction:  final_decision dict from reasoning.py
        live_prices: live_prices dict from data/polymarket.py
        home_code:   short code e.g. "MEX"
        away_code:   short code e.g. "ZAF"
        event_slug:  Polymarket event slug
        bankroll:    current balance from LTM

    Returns:
        Strategy decision dict.
    """
    payload = {
        "prediction":  prediction,
        "live_prices": live_prices,
        "home_code":   home_code,
        "away_code":   away_code,
        "event_slug":  event_slug,
        "bankroll":    bankroll,
    }

    try:
        client   = _get_client()
        response = client.models.generate_content(
            model    = settings.GEMINI_MODEL,
            contents = json.dumps(payload, default=str),
            config   = types.GenerateContentConfig(
                system_instruction = STRATEGY_PROMPT,
                max_output_tokens  = 800,
                thinking_config    = types.ThinkingConfig(
                    include_thoughts = True,
                    thinking_budget  = 512,
                ),
            ),
        )

        raw      = _extract_text(response)
        thinking = _extract_thinking(response)
        result   = _parse_json(raw)

        if result is None:
            return _skip("Gemini returned unparseable JSON")

        # --- hard safety limits ------------------------------------------
        if result.get("size_usdc", 0) > settings.MAX_BET_SIZE:
            result["size_usdc"] = settings.MAX_BET_SIZE

        # no draw bets
        if result.get("outcome") == "draw":
            result["should_trade"] = False
            result["team_code"]    = None
            result["rationale"]    = "Draw bets not supported — skipping."

        result["_thinking"]  = thinking
        result["_available"] = True
        return result

    except Exception as e:
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


def _skip(reason: str) -> dict:
    return {
        "_available":  False,
        "should_trade": False,
        "team_code":    None,
        "outcome":      None,
        "size_usdc":    0.0,
        "limit_price":  0.0,
        "edge_pp":      0.0,
        "rationale":    f"Skipped: {reason}",
    }