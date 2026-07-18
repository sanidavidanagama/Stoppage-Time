# agents/local_unified_agent.py
"""
agents/local_unified_agent.py

Dry-run version of the unified agent. Runs the exact same data gathering
and real Opus call as agents/unified_agent.py, but does NOT place an order,
does NOT write to Supabase, does NOT submit to the Ledger. Instead it prints
ready-to-paste Postman bodies for every ledger behavior in correct session
order (Observing -> Planning -> ToolCalling -> Thinking -> Acting/prediction
-> Acting/order), with real upstream_record_id chaining.
"""

import json, re, time, uuid
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from pathlib import Path

from config.settings import settings
from service.schedule import find_fixture_by_teams, fetch_fixture_detail, build_full_team_form
from service.prompt_builder import _get_formation, _format_lineup
from agents.news_agent import get_news
from service.h2h import get_h2h
from service.polymarket import get_market_data
from service.wallet import get_available_balance
from service.db import get_recent_bets

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


def _ts():
    return int(time.time() * 1000)


def _rid():
    return str(uuid.uuid4())


def dry_run(home_name: str, away_name: str, round_info: str, session_id: str, test_agent_id: str):
    fixture = find_fixture_by_teams(home_name, away_name)
    market = get_market_data(home_name, away_name)
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

    injuries = get_news(home_name, away_name, "injuries")
    pundits = get_news(home_name, away_name, "pundits")
    atmosphere = get_news(home_name, away_name, "atmosphere")
    h2h_text = get_h2h(home_name, away_name)
    balance = get_available_balance()
    recent = get_recent_bets(limit=10)
    track_record = "No past bets." if not recent else f"{len(recent)} past bets on record."

    prompt = _fill(
        _PROMPT_PATH.read_text(encoding="utf-8"),
        home_name=home_name, away_name=away_name, round_info=round_info,
        kick_off_time=fixture["kickoff"], full_tactics_data=full_tactics,
        formations_lineups=formations_lineups,
        news_injuries=injuries.get("answer", "N/A"), news_pundits=pundits.get("answer", "N/A"),
        news_atmosphere=atmosphere.get("answer", "N/A"), h2h_trend=h2h_text,
        market_home=round(market["home"]["price"] * 100, 1),
        market_draw=round(market["draw"]["price"] * 100, 1),
        market_away=round(market["away"]["price"] * 100, 1),
        balance=round(balance, 2), track_record=track_record,
    )

    model = ChatAnthropic(
        model="claude-opus-4-8", max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "high"},
    )
    response = model.invoke([HumanMessage(prompt)])
    thinking_text, final_text = _extract(response)
    result = _parse(final_text)

    # --- Build real record IDs, properly chained ---
    obs_id, plan_id, tool_id, think_id, pred_id = _rid(), _rid(), _rid(), _rid(), _rid()

    def block(title, payload):
        print(f"\n{'='*80}\nPOSTMAN BODY — {title}\n{'='*80}")
        print(json.dumps({"records": [payload]}, indent=2))

    block("1. Observing", {
        "schema_version": settings.LEDGER_SCHEMA_VERSION, "agent_id": test_agent_id, "record_id": obs_id,
        "session_id": session_id, "behavior": "Observing", "client_ts_utc": _ts(),
        "trigger_source": "manual_dry_run", "trigger_type": "cron_trigger",
        "trigger_description": f"Dry run: {home_name} vs {away_name}",
        "trigger_payload_summary": f"{home_name} vs {away_name} ({round_info})",
    })

    block("2. Planning", {
        "schema_version": settings.LEDGER_SCHEMA_VERSION, "agent_id": test_agent_id, "record_id": plan_id,
        "session_id": session_id, "behavior": "Planning", "client_ts_utc": _ts(),
        "upstream_record_id": [obs_id],
        "goal": f"Gather full tactical/news/market context and produce one final decision for {home_name} vs {away_name}",
        "steps": ["Fetch full match history both teams", "Fetch injuries/pundits/atmosphere news",
                   "Fetch continent H2H trend", "Fetch market prices", "Single-call reasoning + decision"],
    })

    block("3. ToolCalling (tactics/news/h2h — send one at a time, same session)", {
        "schema_version": settings.LEDGER_SCHEMA_VERSION, "agent_id": test_agent_id, "record_id": tool_id,
        "session_id": session_id, "behavior": "ToolCalling", "client_ts_utc": _ts(),
        "upstream_record_id": [plan_id], "tool_name": "get_fixture_news",
        "tool_parameters": {"angle": "injuries"}, "result_summary": injuries.get("answer", "")[:500],
        "success": injuries.get("available", False),
    })

    block("4. Thinking (FULL prompt + FULL reasoning — the real Opus call)", {
        "schema_version": settings.LEDGER_SCHEMA_VERSION, "agent_id": test_agent_id, "record_id": think_id,
        "session_id": session_id, "behavior": "Thinking", "client_ts_utc": _ts(),
        "upstream_record_id": [tool_id], "inputs": [],
        "model_invocation": {"provider": "anthropic", "model_name": "claude-opus-4-8", "internal_reasoning": thinking_text},
        "prompt": prompt, "output_payload": final_text,
    })

    if result:
        outcome = result["chosen_outcome"]
        prob = result[f"{outcome}_win_probability" if outcome != "draw" else "draw_probability"]
        code = "draw" if outcome == "draw" else market[outcome]["code"]
        block("5. Acting - prediction (NOTE: no agent_id field on this one)", {
            "schema_version": settings.LEDGER_SCHEMA_VERSION, "record_id": pred_id,
            "session_id": session_id, "behavior": "Acting", "client_ts_utc": _ts(),
            "upstream_record_id": [think_id], "action_type": "prediction", "target_system": "arena",
            "action_summary": f"Predict {code} @ {prob:.3f} for {fixture['fixture_id']}",
            "parameters": {"fixture_id": str(fixture["fixture_id"]), "outcome": code, "probability": max(0.001, min(0.999, prob))},
            "notes": result.get("reasoning", ""), "dry_run": True, "execution_status": "simulated",
        })

        stake = max(5.0, min(float(result.get("stake_usd", 5)), 20.0))
        block("6. Acting - order (dry_run=True, execution_status=simulated — NOT a real order)", {
            "schema_version": settings.LEDGER_SCHEMA_VERSION, "agent_id": test_agent_id, "record_id": _rid(),
            "session_id": session_id, "behavior": "Acting", "client_ts_utc": _ts(),
            "upstream_record_id": [pred_id], "action_type": "order", "target_system": "polymarket",
            "action_summary": f"[DRY RUN] Would buy ${stake:.2f} of {code}",
            "parameters": {"fixture_id": str(fixture["fixture_id"]), "team_code": code, "usd_size": f"{stake:.2f}"},
            "dry_run": True, "execution_status": "simulated",
        })

    print(f"\n{'='*80}\nFULL DECISION JSON\n{'='*80}")
    print(json.dumps(result, indent=2))