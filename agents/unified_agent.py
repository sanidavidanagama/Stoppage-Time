import json, re
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pathlib import Path

from config.settings import settings
from service.schedule import find_fixture_by_teams, fetch_fixture_detail, build_full_team_form
from service.prompt_builder import _get_participants, _get_formation, _format_lineup
from agents.news_agent import get_news
from service.h2h import get_h2h
from service.polymarket import get_market_data
from service.wallet import get_available_balance
from service.db import create_session, update_session_status, save_bet, update_bet, get_recent_bets
from service.orders import place_order, poll_order
from service.telemetry import record_thinking, record_prediction, record_order, record_observing

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "unified_agent_prompt.md"


def _fill(template, **kw):
    for k, v in kw.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _extract(response):
    if isinstance(response.content, str):
        return "", response.content
    t, a = [], []
    for b in response.content:
        if isinstance(b, dict):
            if b.get("type") == "thinking": t.append(b.get("thinking", ""))
            elif b.get("type") == "text": a.append(b.get("text", ""))
    return "\n\n".join(t), "\n\n".join(a)


def _parse(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0)) if m else None


def run_unified_agent(home_name: str, away_name: str, round_info: str, session_id: str) -> dict:
    # Session must exist before ANY log or bet write — both tables have a
    # hard FK on session_id now.
    create_session(session_id, home_name, away_name, source="v2")

    record_observing(session_id, f"Unified single-call run: {home_name} vs {away_name}", "manual_run")

    fixture = find_fixture_by_teams(home_name, away_name)
    if fixture is None:
        update_session_status(session_id, "failed")
        return {"decision": "error", "reason": "fixture_not_found"}

    market = get_market_data(home_name, away_name)
    if market is None or not market.get("mapping_ok"):
        update_session_status(session_id, "failed")
        return {"decision": "error", "reason": "no_live_market", "bet_id": None}

    detail = fetch_fixture_detail(fixture["fixture_id"])
    home_id, away_id = fixture["home"]["team_id"], fixture["away"]["team_id"]

    full_tactics = (
        build_full_team_form(home_id, home_name, fixture["kickoff_timestamp"]) + "\n\n" +
        build_full_team_form(away_id, away_name, fixture["kickoff_timestamp"])
    )

    formations_lineups = (
        f"{home_name} formation: {_get_formation(detail, home_id)}\n{_format_lineup(detail, home_id)}\n\n"
        f"{away_name} formation: {_get_formation(detail, away_id)}\n{_format_lineup(detail, away_id)}"
    )

    injuries = get_news(home_name, away_name, "injuries", session_id=session_id)
    pundits = get_news(home_name, away_name, "pundits", session_id=session_id)
    atmosphere = get_news(home_name, away_name, "atmosphere", session_id=session_id)
    h2h_text = get_h2h(home_name, away_name)
    balance = get_available_balance()
    recent = get_recent_bets(limit=10)

    track_record = "No past bets." if not recent else f"{len(recent)} past bets on record."

    prompt = _fill(
        _PROMPT_PATH.read_text(encoding="utf-8"),
        home_name=home_name, away_name=away_name, round_info=round_info,
        kick_off_time=fixture["kickoff"],
        full_tactics_data=full_tactics,
        formations_lineups=formations_lineups,
        news_injuries=injuries.get("answer", "N/A"),
        news_pundits=pundits.get("answer", "N/A"),
        news_atmosphere=atmosphere.get("answer", "N/A"),
        h2h_trend=h2h_text,
        market_home=round(market["home"]["price"] * 100, 1),
        market_draw=round(market["draw"]["price"] * 100, 1),
        market_away=round(market["away"]["price"] * 100, 1),
        balance=round(balance, 2),
        track_record=track_record,
    )

    model = ChatAnthropic(
        model="claude-opus-4-8",
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "high"},
    )
    response = model.invoke([HumanMessage(prompt)])
    thinking_text, final_text = _extract(response)

    bet_row = save_bet({
        "session_id": session_id, "fixture_id": fixture["fixture_id"],
        "fixture_name": f"{home_name} vs {away_name}",
        "home_team": home_name, "away_team": away_name,
        "home_code": market["home"]["code"], "away_code": market["away"]["code"],
        "market_home_price": market["home"]["price"], "market_draw_price": market["draw"]["price"],
        "market_away_price": market["away"]["price"], "decision": "pending",
    })
    bet_id = bet_row.get("id")

    record_thinking(session_id, bet_id, "unified", "claude-opus-4-8", prompt, final_text, thinking_text)

    result = _parse(final_text)
    if result is None:
        update_bet(bet_id, {"decision": "skip", "bet_reason": "unparseable"})
        update_session_status(session_id, "failed")
        return {"decision": "error", "raw": final_text, "bet_id": bet_id}

    print("\n" + "="*80)
    print("FULL REASONING (thinking):")
    print("="*80)
    print(thinking_text)
    print("\n" + "="*80)
    print("TACTICAL SUMMARY:")
    print("="*80)
    print(result.get("tactical_summary", ""))
    print("\n" + "="*80)
    print("FINAL DECISION JSON:")
    print("="*80)
    print(json.dumps(result, indent=2))
    print("="*80 + "\n")

    outcome = result["chosen_outcome"]
    prob = result[f"{outcome}_win_probability" if outcome != "draw" else "draw_probability"]
    code = "draw" if outcome == "draw" else market[outcome]["code"]

    stake = float(result.get("stake_usd", 5))
    stake = max(5.0, min(stake, 20.0))
    edge_pp = round((prob - (market["draw"]["price"] if outcome == "draw" else market[outcome]["price"])) * 100, 1)

    prediction_record_id = record_prediction(session_id, fixture["fixture_id"], code, prob, result.get("reasoning", ""))

    order_result = place_order(fixture["fixture_id"], code, stake, market[outcome]["price"] if outcome != "draw" else market["draw"]["price"])
    order_id = order_result.get("order_id")
    order_info = {}
    if order_id:
        final_order = poll_order(order_id)
        order_info = {"order_id": order_id, "order_status": final_order.get("status"), "fill_price": final_order.get("open_avg_fill_price")}
        record_order(session_id, fixture["fixture_id"], code, stake, f"Bought ${stake} of {code}", upstream_id=prediction_record_id)

    update_bet(bet_id, {
        "decision": outcome, "stake_usd": stake, "edge_pp": edge_pp,
        "home_probability": result["home_win_probability"], "draw_probability": result["draw_probability"],
        "away_probability": result["away_win_probability"], "confidence": result["confidence"],
        "bet_reason": result["reasoning"], **order_info,
    })
    update_session_status(session_id, "completed")

    return {"decision": outcome, "stake_usd": stake, "reasoning": result["reasoning"], "bet_id": bet_id, **order_info}