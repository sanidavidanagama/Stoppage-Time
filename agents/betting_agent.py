# agents/betting_agent.py
"""
agents/betting_agent.py

The Betting Agent. Edge is calculated deterministically first —
the LLM is only called when a real edge (>= MIN_EDGE_PP) exists
on at least one outcome. When called, it decides stake size and whether
to actually act, informed by its own track record — not a formula.
"""

import json
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from config.settings import settings
from service.polymarket import get_market_data
from service.wallet import get_available_balance
from service.db import save_bet, update_bet, log_step, get_recent_bets

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "betting_prompt.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _fill_template(template: str, **kwargs) -> str:
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _model():
    return ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_REASONING_MAX_TOKENS,
        thinking={"type": "enabled", "budget_tokens": settings.ANTHROPIC_THINKING_BUDGET},
    )


def _extract(response) -> tuple[str, str]:
    if isinstance(response.content, str):
        return "", response.content
    thinking_parts, text_parts = [], []
    for block in response.content:
        if isinstance(block, dict):
            if block.get("type") == "thinking":
                thinking_parts.append(block.get("thinking", ""))
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))
    return "\n\n".join(thinking_parts), "\n\n".join(text_parts)


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _scan_edge(prediction: dict, market: dict) -> dict:
    """Pure math — no LLM. Finds the best-edge outcome among home/draw/away."""
    candidates = [
        ("home", prediction["home_win_probability"], market["home"]["price"]),
        ("draw", prediction["draw_probability"],      market["draw"]["price"]),
        ("away", prediction["away_win_probability"],  market["away"]["price"]),
    ]
    best = None
    for outcome, agent_prob, price in candidates:
        edge_pp = (agent_prob - price) * 100
        if best is None or edge_pp > best["edge_pp"]:
            best = {"outcome": outcome, "agent_prob": agent_prob, "price": price, "edge_pp": edge_pp}
    return best


def _track_record_summary(recent_bets: list[dict]) -> str:
    if not recent_bets:
        return "No past bets yet — this is your first."

    settled = [b for b in recent_bets if b.get("actual_outcome") is not None]
    if not settled:
        return f"{len(recent_bets)} past bet(s), none settled yet."

    wins = sum(1 for b in settled if b.get("pnl", 0) > 0)
    losses = sum(1 for b in settled if b.get("pnl", 0) <= 0)

    lines = [f"Last {len(settled)} settled bets: {wins}W {losses}L"]
    for b in settled[:5]:
        lines.append(
            f"  {b['fixture_name']}: bet {b['decision']} @ {b['edge_pp']}pp edge, "
            f"stake ${b['stake_usd']}, result: {'WIN' if b.get('pnl', 0) > 0 else 'LOSS'} "
            f"(pnl {b.get('pnl')})"
        )
    return "\n".join(lines)


def _pnl_summary(recent_bets: list[dict]) -> str:
    settled = [b for b in recent_bets if b.get("pnl") is not None]
    if not settled:
        return "No settled P&L yet."
    total = sum(b["pnl"] for b in settled)
    return f"Total realized P&L across {len(settled)} settled bets: {total:+.2f} USDC"


def run_betting_agent(
    home_name: str,
    away_name: str,
    prediction: dict,
    session_id: str,
    leaderboard_status: str = "Unknown",
) -> dict:
    market = get_market_data(home_name, away_name)

    if market is None or not market.get("mapping_ok"):
        bet_row = save_bet({
            "session_id": session_id,
            "home_team": home_name,
            "away_team": away_name,
            "decision": "skip",
            "bet_reason": "no_market_data_or_mapping_failed",
        })
        return {"decision": "skip", "reason": "no_market_data_or_mapping_failed", "bet_id": bet_row.get("id")}

    edge = _scan_edge(prediction, market)

    base_fields = {
        "session_id": session_id,
        "fixture_id": market["fixture_id"],
        "home_team": home_name,
        "away_team": away_name,
        "home_code": market["home"]["code"],
        "away_code": market["away"]["code"],
        "home_probability": prediction["home_win_probability"],
        "draw_probability": prediction["draw_probability"],
        "away_probability": prediction["away_win_probability"],
        "confidence": prediction.get("confidence"),
        "market_home_price": market["home"]["price"],
        "market_draw_price": market["draw"]["price"],
        "market_away_price": market["away"]["price"],
        "edge_pp": round(edge["edge_pp"], 1),
    }

    if edge["edge_pp"] < settings.MIN_EDGE_PP:
        bet_row = save_bet({
            **base_fields,
            "decision": "skip",
            "bet_reason": f"edge_{round(edge['edge_pp'], 1)}pp_below_{settings.MIN_EDGE_PP}pp_threshold",
        })
        return {"decision": "skip", "reason": "below_edge_threshold", "edge_pp": round(edge["edge_pp"], 1), "bet_id": bet_row.get("id")}

    # Real edge exists — create the bet row NOW (decision pending), so every
    # log row from here on can reference a real bet_id.
    bet_row = save_bet({**base_fields, "decision": "pending"})
    bet_id = bet_row.get("id")

    balance = get_available_balance()
    recent = get_recent_bets(limit=10)

    prompt = _fill_template(
        _load_prompt(),
        home_name=home_name,
        away_name=away_name,
        home_prob=round(prediction["home_win_probability"] * 100, 1),
        draw_prob=round(prediction["draw_probability"] * 100, 1),
        away_prob=round(prediction["away_win_probability"] * 100, 1),
        confidence=prediction.get("confidence", "unknown"),
        market_home=round(market["home"]["price"] * 100, 1),
        market_draw=round(market["draw"]["price"] * 100, 1),
        market_away=round(market["away"]["price"] * 100, 1),
        edge_pp=round(edge["edge_pp"], 1),
        edge_outcome=edge["outcome"],
        balance=round(balance, 2),
        leaderboard_status=leaderboard_status,
        past_bets_summary=_track_record_summary(recent),
        pnl_summary=_pnl_summary(recent),
    )

    model = _model()
    response = model.invoke([HumanMessage(prompt)])
    thinking, final_text = _extract(response)

    log_step(
        session_id=session_id,
        step_type="Thinking",
        tool="betting",
        bet_id=bet_id,
        model=settings.ANTHROPIC_MODEL,
        prompt=prompt,
        response=final_text,
    )

    result = _parse_json(final_text)
    if result is None:
        update_bet(bet_id, {"decision": "skip", "bet_reason": "llm_unparseable_response"})
        return {"decision": "skip", "reason": "llm_unparseable_response", "raw": final_text, "bet_id": bet_id}

    decision = result.get("decision", "skip")
    stake = float(result.get("stake_usd", 0) or 0)

    stake = min(stake, settings.MAX_STAKE_PCT * balance)
    if decision == "confirm" and stake < settings.MIN_STAKE_USD:
        stake = 0
        decision = "skip"

    update_bet(bet_id, {
        "decision": edge["outcome"] if decision == "confirm" else "skip",
        "stake_usd": stake if decision == "confirm" else None,
        "bet_reason": result.get("reasoning", ""),
    })

    return {
        "decision": edge["outcome"] if decision == "confirm" else "skip",
        "stake_usd": stake if decision == "confirm" else None,
        "edge_pp": round(edge["edge_pp"], 1),
        "reasoning": result.get("reasoning"),
        "bet_id": bet_id,
    }