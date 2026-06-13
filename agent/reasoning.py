"""
agent/reasoning.py

Main reasoning agent — the core Gemini call.
Assembles all data from STSSM + LTM into a single prompt
and calls Gemini once per round.

Returns either:
    - final_decision: agent is ready to bet or skip
    - tool_request:   agent needs more data
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from google import genai
from google.genai import types
from config import settings
from agent.memory.stssm import STSSM
from agent.memory.ltm import get_ltm_context
from agent.reasoning_logger import log_reasoning


# --- Gemini client -----------------------------------------------------------

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --- Prompt loader -----------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent / "prompts" / "reasoning_prompt.md"

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# --- Data formatters ---------------------------------------------------------

def _format_sportmonks(stm: STSSM) -> str:
    sm = stm.sportmonks
    if not sm:
        return "No Sportmonks data available."

    lines = []

    # ML predictions
    preds = sm.get("predictions", {})
    if preds.get("available"):
        c = preds.get("consensus", {})
        lines.append(
            f"ML model consensus ({len(preds.get('one_x_two', []))} models): "
            f"home={c.get('home')}%  draw={c.get('draw')}%  away={c.get('away')}%"
        )
    else:
        lines.append("ML predictions: not available")

    # Bookmaker odds
    odds = sm.get("odds", {})
    if odds.get("available"):
        c = odds.get("consensus", {})
        lines.append(
            f"Bookmaker consensus ({odds.get('bookmaker_count')} bookmakers): "
            f"home={round((c.get('home') or 0)*100, 1)}%  "
            f"draw={round((c.get('draw') or 0)*100, 1)}%  "
            f"away={round((c.get('away') or 0)*100, 1)}%  "
            f"(stale: {odds.get('stale_count', 0)})"
        )
    else:
        lines.append("Bookmaker odds: not available")

    # xG
    xg = sm.get("xg", {})
    if xg.get("available"):
        lines.append(
            f"Expected goals: home={xg.get('home_xg')}  away={xg.get('away_xg')}"
        )
    else:
        lines.append("Expected goals (xG): not available on staging")

    # Lineups
    lineups = sm.get("lineups", {})
    if lineups.get("available"):
        home_f = (lineups.get("home") or {}).get("formation", "unknown")
        away_f = (lineups.get("away") or {}).get("formation", "unknown")
        lines.append(f"Formations: home={home_f}  away={away_f}")
    else:
        lines.append("Lineups: not yet published")

    return "\n".join(lines)


def _format_polymarket(stm: STSSM) -> str:
    pm = stm.polymarket
    if not pm:
        return "No Polymarket data available."

    lines = []

    prices = pm.get("live_prices", {})
    if prices.get("available"):
        lines.append(
            f"Live CLOB mid prices: "
            f"home={prices.get('home')}  "
            f"draw={prices.get('draw')}  "
            f"away={prices.get('away')}  "
            f"(sum={prices.get('sum')})"
        )
    else:
        lines.append("Live prices: not available")

    meta = pm.get("meta", {})
    if meta.get("available"):
        lines.append(
            f"Market: liquidity=${meta.get('liquidity'):,.0f}  "
            f"volume=${meta.get('volume'):,.0f}  "
            f"volume_24hr=${meta.get('volume_24hr'):,.0f}  "
            f"competitive={meta.get('competitive'):.3f}"
        )

    history = pm.get("price_history", {})
    if history.get("available"):
        for outcome in ["home", "draw", "away"]:
            h = history.get(outcome)
            if h:
                chg_24h = f"{h.get('change_24hr'):+.3f}" if h.get('change_24hr') is not None else "N/A"
                chg_1wk = f"{h.get('change_1wk'):+.3f}"  if h.get('change_1wk')  is not None else "N/A"
                lines.append(
                    f"  {outcome}: last={h.get('last_price')}  "
                    f"24hr_chg={chg_24h}  "
                    f"1wk_chg={chg_1wk}  "
                    f"spread={h.get('spread')}"
                )

    return "\n".join(lines)


def _format_supabase(stm: STSSM) -> str:
    sb = stm.supabase
    if not sb:
        return "No Supabase data available."

    lines = []
    im = stm.identity_map

    # checkpoint stats
    ck = sb.get("checkpoint_stats", {})
    if ck.get("available"):
        lines.append(f"2022 WC checkpoint stats for {im.get('home', {}).get('name')}:")
        for m in ck.get("home_matches", []):
            lines.append(
                f"  {m.get('opponent'):20s} "
                f"goals={m.get('cum_goals')}  "
                f"shots={m.get('cum_shots_total')}  "
                f"on_target={m.get('cum_shots_on_target')}  "
                f"poss={m.get('cum_possession_pct')}%  "
                f"pass_acc={round((m.get('cum_pass_accuracy_pct') or 0)*100, 1)}%"
            )
    else:
        lines.append(
            f"Checkpoint stats: not available for "
            f"{im.get('home', {}).get('name')} — "
            f"{im.get('away', {}).get('name')} did not qualify for 2022 WC"
        )

    # stage record
    stage = sb.get("stage_record", {})
    if stage.get("available"):
        for side in ["home", "away"]:
            name = im.get(side, {}).get("name", side)
            record = stage.get(side, {})
            if record and "group" in record:
                g = record["group"]
                lines.append(
                    f"{name} group stage record: "
                    f"W{g.get('wins')} D{g.get('draws')} L{g.get('losses')} "
                    f"({g.get('matches')} matches, win_rate={g.get('win_rate'):.1%})"
                )

    return "\n".join(lines) if lines else "No Supabase data available."


def _format_tactics(stm: STSSM) -> str:
    t = stm.tactics
    if not t or not t.get("_available"):
        reason = t.get("_error", "not run") if t else "not run"
        return f"Tactical analysis: unavailable ({reason})"

    lines = [
        f"Overall advantage : {t.get('overall_advantage')} ({t.get('advantage_strength')})",
        f"Confidence        : {t.get('confidence')} — {t.get('confidence_reason', '')}",
        f"Analyst verdict   : {t.get('analyst_verdict', '')}",
    ]

    battlegrounds = t.get("key_battlegrounds")
    if battlegrounds:
        if isinstance(battlegrounds, list):
            lines.append(f"Key battlegrounds : {', '.join(str(b) for b in battlegrounds)}")
        else:
            lines.append(f"Key battlegrounds : {battlegrounds}")

    gaps = t.get("data_gaps")
    if gaps:
        lines.append(f"Data gaps         : {gaps}")

    return "\n".join(lines)


def _format_news(stm: STSSM) -> str:
    if not stm.news:
        return "No recent news found."

    lines = []
    for a in stm.news[:5]:
        lines.append(f"{a.get('source')}: {a.get('summary', '')}")
    return "\n".join(lines)


# --- Prompt assembler --------------------------------------------------------

def _assemble_prompt(stm: STSSM, ml_market_gap: float | None = None) -> str:
    """Fill all {placeholders} in the system prompt template."""
    im = stm.identity_map

    template = _load_prompt()

    # compute ML/market gap if not provided
    if ml_market_gap is None:
        try:
            ml_home = stm.sportmonks["predictions"]["consensus"]["home"] / 100
            pm_home = stm.polymarket["live_prices"]["home"]
            ml_market_gap = round((ml_home - pm_home) * 100, 1)
        except (KeyError, TypeError):
            ml_market_gap = None

    replacements = {
        "{home}":                    im.get("home", {}).get("name", "Home"),
        "{away}":                    im.get("away", {}).get("name", "Away"),
        "{kickoff_utc}":             stm.kickoff or "unknown",
        "{stage}":                   im.get("stage", "unknown"),
        "{round}":                   str(im.get("round", "unknown")),
        "{data_availability}":       stm.data_availability_summary(),
        "{sportmonks_predictions}":  _format_sportmonks(stm),
        "{sportmonks_odds}":         _format_sportmonks(stm),
        "{polymarket_prices}":       _format_polymarket(stm),
        "{supabase_checkpoint}":     _format_supabase(stm),
        "{supabase_priors}":         _format_supabase(stm),
        "{tactics_analysis}":        _format_tactics(stm),
        "{news_summary}":            _format_news(stm),
        "{ltm_context}":             get_ltm_context(ml_market_gap),
        "{tool_history}":            stm.tool_history_summary(),
        "{rounds_remaining}":        str(settings.MAX_TOOL_ROUNDS - stm.current_round),
    }

    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, str(value))

    return prompt


# --- Response parser ---------------------------------------------------------

def _parse_response(raw: str) -> dict | None:
    """
    Parse Gemini response — strips code fences and extracts JSON.
    Returns None if parsing fails.
    """
    clean = re.sub(r"```json\s*", "", raw)
    clean = re.sub(r"```\s*",     "", clean)

    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


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

def _validate_final_decision(result: dict) -> bool:
    """Validate final_decision has correct shape and values."""
    if result.get("type") != "final_decision":
        return True   # tool_request and error types skip validation
    if result.get("outcome") not in ["home", "away"]:
        return False
    if not isinstance(result.get("probability"), (int, float)):
        return False
    if not isinstance(result.get("should_bet"), bool):
        return False
    return True

# --- Main call ---------------------------------------------------------------

def call(stm: STSSM) -> dict:
    """
    Make one Gemini reasoning call for the current session state.

    Args:
        stm: populated STSSM with all fetched data

    Returns:
        Parsed response dict with type "final_decision" or "tool_request".
        On failure returns {"type": "error", "reason": ...}
    """
    prompt = _assemble_prompt(stm)

    try:
        client   = _get_client()
        response = client.models.generate_content(
            model    = settings.GEMINI_MODEL,
            contents = prompt,
            config   = types.GenerateContentConfig(
                max_output_tokens  = 2000,
                response_mime_type = "application/json",   # force JSON
                thinking_config    = types.ThinkingConfig(
                    include_thoughts = True,
                    thinking_budget  = 1024,
                ),
            ),
        )

        raw      = _extract_text(response)
        thinking = _extract_thinking(response)

        log_reasoning(
            prompt,
            _format_response_snapshot(thinking, raw),
        )

        print(f"    [DEBUG] Raw response preview: {raw[:200]}")

        result = _parse_response(raw)

        if result is None:
            return {
                "type":      "error",
                "reason":    "unparseable response",
                "_raw":      raw,
                "_thinking": thinking,
            }

        if not _validate_final_decision(result):
            return {
                "type":      "error",
                "reason":    "invalid final_decision — outcome must be home or away",
                "_raw":      raw,
                "_thinking": thinking,
            }

        result["_thinking"] = thinking
        result["_raw"]      = raw
        return result

    except Exception as e:
        log_reasoning(prompt, f"EXCEPTION\n\n{e}")
        return {
            "type":   "error",
            "reason": str(e),
        }


def get_assembled_prompt(stm: STSSM) -> str:
    """
    Return the fully assembled prompt without calling Gemini.
    Useful for debugging and testing.
    """
    return _assemble_prompt(stm)


def _format_response_snapshot(thinking: str, raw: str) -> str:
    return (
        "# Thinking\n\n"
        + (thinking or "")
        + "\n\n# Raw Response\n\n"
        + (raw or "")
    )