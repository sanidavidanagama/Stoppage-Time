"""
agent/orchestrator.py

Main orchestration loop for Stoppage Time.
Ties together all modules into one complete agent run.

Flow:
    1. Create STSSM
    2. Planning record
    3. Resolve identities
    4. Fetch initial data (Sportmonks + Polymarket + Supabase + News)
    5. ReAct loop (reasoning -> tool calls -> reasoning...)
    6. If should_bet -> call bet_manager
    7. Place order
    8. Reflecting record
    9. Log everything to Arena ledger
    10. Save bet to LTM
"""

from __future__ import annotations
import json
import uuid
import requests

from config import settings
from data.identity   import resolve_identity
from data.sportmonks import get_all as sm_get_all
from data.polymarket import get_all as pm_get_all
from data.supabase   import get_all as sb_get_all
from data.news.fetcher  import fetch_news
from data.news.embedder import embed_articles
from data.news.store    import store_articles, clear_collection

from agent.memory.stssm  import new_session, STSSM
from agent.memory.ltm    import save_bet, get_bankroll_summary
from agent.reasoning     import call as reasoning_call
from agent.bet_manager   import decide as bet_manager_decide
from agent.tool_executor import execute as tool_execute

from ledger.logger import (
    observing, thinking, acting, tool_calling,
    planning, reflecting, other, submit,
)


# --- Main entry point --------------------------------------------------------

def run(home: str, away: str) -> dict:
    """
    Run one complete agent cycle for a fixture.
    """
    stm     = new_session()
    records = []

    print(f"\n{'='*55}")
    print(f"Stoppage Time — {home} vs {away}")
    print(f"{'='*55}\n")

    try:
        # ── Step 1: Identity resolution ──────────────────────────────────────
        print("Step 1: Resolving identities...")
        identity_map     = resolve_identity(home, away)
        stm.identity_map = identity_map
        stm.session_id   = f"prematch:{identity_map['fixture_id']}"
        stm.fixture_name = identity_map["fixture_name"]
        stm.kickoff      = identity_map["kickoff"]

        fixture_id_str = str(identity_map["fixture_id"])

        print(f"  Fixture  : {identity_map['fixture_name']}")
        print(f"  Kickoff  : {identity_map['kickoff']}")

        # ── Step 2: Planning record ───────────────────────────────────────────
        rec_plan = planning(
            session_id = stm.session_id,
            goal       = f"Analyse {home} vs {away} and decide whether to place a pre-match bet",
            steps      = [
                "Fetch Sportmonks predictions and bookmaker odds",
                "Fetch Polymarket live prices and liquidity",
                "Fetch Supabase historical priors and checkpoint stats",
                "Fetch recent news articles via RSS",
                "Run Gemini reasoning over all data",
                "Call bet manager if agent decides to bet",
                "Place order on Polymarket if bet is confirmed",
                "Reflect on decision and update long term memory",
            ],
        )
        records.append(rec_plan)

        # ── Step 3: Fetch data ────────────────────────────────────────────────
        stm.status = "fetching"
        print("\nStep 2: Fetching data...")

        # Sportmonks
        stm.sportmonks = sm_get_all(identity_map)
        rec_sm = observing(
            stm.session_id,
            f"Fetched Sportmonks data for {identity_map['fixture_name']}: "
            f"predictions={stm.sportmonks['predictions']['available']} "
            f"odds={stm.sportmonks['odds']['available']}",
            "sportmonks_proxy",
            upstream_ids=[rec_plan["record_id"]],
        )
        records.append(rec_sm)
        print(f"  Sportmonks: predictions={stm.sportmonks['predictions']['available']}  "
              f"odds={stm.sportmonks['odds']['available']}")

        # Polymarket
        stm.polymarket = pm_get_all(identity_map)
        rec_pm = observing(
            stm.session_id,
            f"Fetched Polymarket data: "
            f"prices={stm.polymarket['live_prices']['available']} "
            f"liquidity=${stm.polymarket['meta'].get('liquidity', 0):,.0f}",
            "polymarket_proxy",
            upstream_ids=[rec_plan["record_id"]],
        )
        records.append(rec_pm)
        print(f"  Polymarket: prices={stm.polymarket['live_prices']['available']}  "
              f"liquidity=${stm.polymarket['meta'].get('liquidity', 0):,.0f}")

        # Supabase
        stm.supabase = sb_get_all(identity_map)
        rec_sb = observing(
            stm.session_id,
            f"Fetched Supabase data: "
            f"checkpoint={stm.supabase['checkpoint_stats']['available']} "
            f"priors={stm.supabase['country_style']['available']}",
            "supabase",
            upstream_ids=[rec_plan["record_id"]],
        )
        records.append(rec_sb)
        print(f"  Supabase  : checkpoint={stm.supabase['checkpoint_stats']['available']}  "
              f"priors={stm.supabase['country_style']['available']}")

        # News
        articles = fetch_news(home, away)
        if articles:
            embedded = embed_articles(articles)
            clear_collection()
            store_articles(embedded)
        stm.news = articles
        rec_news = observing(
            stm.session_id,
            f"Fetched {len(articles)} news articles via RSS feeds",
            "rss_feeds",
            upstream_ids=[rec_plan["record_id"]],
        )
        records.append(rec_news)
        print(f"  News      : {len(articles)} articles")

        # Weather
        from data.sportmonks import get_fixture_meta
        from data.weather    import get_match_weather
        meta    = get_fixture_meta(identity_map)
        wx      = get_match_weather(
            venue_id     = meta.get("venue_id"),
            kickoff_date = stm.kickoff[:10] if stm.kickoff else None,
        )
        rec_wx = other(
            session_id = stm.session_id,
            label      = "weather_fetch",
            data       = {
                "venue":     wx.get("venue"),
                "city":      wx.get("city"),
                "temp_c":    wx.get("temp_c"),
                "condition": wx.get("condition"),
                "wind_kph":  wx.get("wind_kph"),
                "precip_mm": wx.get("precip_mm"),
                "available": wx.get("available"),
                "summary":   wx.get("summary"),
            },
            upstream_ids=[rec_plan["record_id"]],
        )
        records.append(rec_wx)
        print(f"  Weather   : {wx.get('summary', 'unavailable')}")

        # ── Step 4: ReAct loop ────────────────────────────────────────────────
        stm.status = "reasoning"
        print(f"\nStep 3: ReAct loop (max {settings.MAX_TOOL_ROUNDS} rounds)...")

        final_decision = None
        rec_think      = None

        for round_num in range(1, settings.MAX_TOOL_ROUNDS + 1):
            stm.current_round = round_num
            print(f"\n  Round {round_num}:")

            response = reasoning_call(stm)
            stm.add_gemini_message("assistant", json.dumps(response, default=str))

            upstream = [r["record_id"] for r in
                        [rec_sm, rec_pm, rec_sb, rec_news, rec_wx]
                        if r is not None]

            clean_response = {k: v for k, v in response.items()
                            if k not in ["_thinking", "_raw"]}

            rec_think = thinking(
                session_id         = stm.session_id,
                prompt             = f"Round {round_num} — Analyse {home} vs {away} and decide",
                output_payload     = clean_response if clean_response else {"type": "error"},
                model_name         = settings.GEMINI_MODEL,
                tokens_in          = None,
                tokens_out         = None,
                internal_reasoning = None, 
                upstream_ids       = upstream,
                inputs             = [{"input_payload": json.dumps({
                    "sportmonks": stm.sportmonks.get("predictions", {}).get("consensus"),
                    "polymarket": stm.polymarket.get("live_prices", {}),
                }, default=str)[:2000]}],
            )
            records.append(rec_think)

            resp_type = response.get("type")
            print(f"    Response type: {resp_type}")

            if resp_type == "final_decision":
                final_decision = response
                print(f"    Outcome      : {response.get('outcome')}")
                print(f"    Should bet   : {response.get('should_bet')}")
                print(f"    Confidence   : {response.get('confidence_level')}")
                break

            elif resp_type == "tool_request":
                tool_name = response.get("tool")
                params    = dict(response.get("params", {}))
                reason    = response.get("reason", "")
                params["reason"] = reason

                print(f"    Tool request : {tool_name}")
                print(f"    Reason       : {reason[:80]}")

                tc = tool_execute(tool_name, params, stm, round_num)
                stm.add_tool_call(tc)

                # use Other for weather/tactics, ToolCalling for data fetches
                if tool_name in ["weather.get_match_weather", "tactics.analyse"]:
                    rec_tc = other(
                        session_id   = stm.session_id,
                        label        = tool_name.replace(".", "_"),
                        data         = {
                            "params":  params,
                            "result":  (tc.result_summary or "")[:2000],
                            "success": tc.error is None,
                        },
                        upstream_ids = [rec_think["record_id"]],
                    )
                else:
                    rec_tc = tool_calling(
                        session_id    = stm.session_id,
                        tool_name     = tool_name,
                        params        = params,
                        result_summary = tc.result_summary or "",
                        success       = tc.error is None,
                        upstream_ids  = [rec_think["record_id"]],
                    )
                records.append(rec_tc)

                print(f"    Result       : {(tc.result_summary or '')[:80]}...")
                stm.add_gemini_message(
                    "user",
                    f"Tool result for {tool_name}:\n{tc.result_summary}"
                )

            elif resp_type == "error":
                print(f"    ERROR: {response.get('reason')}")
                break

        # max rounds fallback
        if final_decision is None:
            final_decision = {
                "type":             "final_decision",
                "outcome":          None,
                "should_bet":       False,
                "confidence_level": "low",
                "rationale":        f"Max rounds ({settings.MAX_TOOL_ROUNDS}) reached without decision.",
            }

        # ── Step 5: Prediction record ─────────────────────────────────────────
        _pred_prob = max(0.001, min(0.999, float(final_decision.get("probability") or 0.5)))
        rec_predict = acting(
            session_id       = stm.session_id,
            action_type      = "prediction",
            action_summary   = (
                f"Predict {final_decision.get('outcome')} "
                f"@ p={_pred_prob:.2f} "
                f"for {identity_map['fixture_name']}"
            ),
            parameters       = {
                "fixture_id":  fixture_id_str,
                "outcome":     final_decision.get("outcome"),
                "probability": _pred_prob,
            },
            execution_status = "confirmed",
            upstream_ids     = [rec_think["record_id"]] if rec_think else [],
        )
        if final_decision.get("outcome") in ["home", "away"]:
            records.append(rec_predict)
        stm.prediction = final_decision

        # ── Step 6: Bet manager ───────────────────────────────────────────────
        bet_decision = None
        order_result = None

        if final_decision.get("should_bet"):
            stm.status  = "acting"
            print(f"\nStep 4: Calling bet manager...")

            live_prices  = stm.polymarket.get("live_prices", {})
            bet_decision = bet_manager_decide(
                prediction  = final_decision,
                live_prices = live_prices,
                home_code   = identity_map["home"]["short_code"],
                away_code   = identity_map["away"]["short_code"],
            )
            stm.strategy = bet_decision

            rec_bet_think = thinking(
                session_id         = stm.session_id,
                prompt             = "Bet manager — decide size and limit price",
                output_payload     = {k: v for k, v in bet_decision.items()
                                    if k not in ["_thinking", "_raw"]},
                model_name         = settings.GEMINI_MODEL,
                tokens_in          = None,
                tokens_out         = None,
                internal_reasoning = None,   # remove — too large
                upstream_ids       = [rec_predict["record_id"]],
                inputs             = [{"input_payload": json.dumps({
                    "prediction":  final_decision,
                    "live_prices": live_prices,
                }, default=str)[:2000]}],
            )
            records.append(rec_bet_think)

            print(f"  Should place order: {bet_decision.get('should_place_order')}")
            print(f"  Team code         : {bet_decision.get('team_code')}")
            print(f"  Size              : ${bet_decision.get('size_usdc')}")
            print(f"  Edge              : {bet_decision.get('edge_pp')}pp")

            # ── Step 7: Place order ───────────────────────────────────────────
            if bet_decision.get("should_place_order"):
                print(f"\nStep 5: Placing order...")
                order_result = _place_order(
                    fixture_id  = identity_map["fixture_id"],
                    team_code   = bet_decision["team_code"],
                    size_usdc   = bet_decision["size_usdc"],
                    limit_price = bet_decision["limit_price"],
                )
                stm.order_response = order_result

                rec_order = acting(
                    session_id       = stm.session_id,
                    action_type      = "open_order",
                    action_summary   = (
                        f"Open long ${bet_decision['size_usdc']:.2f} on "
                        f"{bet_decision['team_code']} "
                        f"@ ≤{bet_decision['limit_price']}"
                    ),
                    parameters       = {
                        "fixture_id":  fixture_id_str,
                        "team_code":   bet_decision["team_code"],
                        "usd_size":    str(bet_decision["size_usdc"]),
                        "limit_price": bet_decision["limit_price"],
                    },
                    execution_status = "pending" if order_result.get("status") not in ["error", "rejected"] else "failed",
                    execution_id     = order_result.get("order_id"),
                    upstream_ids     = [rec_bet_think["record_id"]],
                )
                records.append(rec_order)
                print(f"  Order status: {order_result.get('status', 'unknown')}")
        else:
            print(f"\nStep 4: Agent decided not to bet.")
            print(f"  Reason: {final_decision.get('rationale', '')[:100]}")

            rec_skip = acting(
                session_id       = stm.session_id,
                action_type      = "skip",
                action_summary   = "Agent decided not to place a bet",
                parameters       = {"reason": final_decision.get("rationale", "")[:200]},
                execution_status = "confirmed",
                upstream_ids     = [rec_predict["record_id"]] if final_decision.get("outcome") else [],
            )
            records.append(rec_skip)

        # ── Step 8: Reflecting ────────────────────────────────────────────────
        rec_reflect = reflecting(
            session_id    = stm.session_id,
            input_payload = json.dumps({
                "outcome":       final_decision.get("outcome"),
                "probability":   _pred_prob,
                "should_bet":    final_decision.get("should_bet"),
                "confidence":    final_decision.get("confidence_level"),
                "tool_calls":    len(stm.tool_history),
            }, default=str),
            reflection = (
                f"Decision: predict {final_decision.get('outcome')} "
                f"@ {_pred_prob:.0%} confidence={final_decision.get('confidence_level')}. "
                f"Bet placed: {bool(bet_decision and bet_decision.get('should_place_order'))}. "
                f"Rationale: {final_decision.get('rationale', '')[:200]}"
            )[:1000],
            upstream_ids  = [rec_predict["record_id"]] if final_decision.get("outcome") else [],
        )
        records.append(rec_reflect)

        # ── Step 9: Save to LTM ───────────────────────────────────────────────
        print(f"\nStep 6: Saving to LTM...")
        pm_prices = stm.polymarket.get("live_prices", {})
        ml_cons   = stm.sportmonks.get("predictions", {}).get("consensus", {})
        bk_cons   = stm.sportmonks.get("odds", {}).get("consensus", {})

        bet_id = save_bet(
            session_id        = stm.session_id,
            fixture_name      = identity_map["fixture_name"],
            home_team         = identity_map["home"]["name"],
            away_team         = identity_map["away"]["name"],
            predicted_outcome = final_decision.get("outcome") or "none",
            agent_probability = float(final_decision.get("probability") or 0),
            confidence_level  = final_decision.get("confidence_level", "low"),
            should_bet        = bool(final_decision.get("should_bet")),
            bet_outcome       = bet_decision.get("outcome") if bet_decision else None,
            bet_direction     = "long" if bet_decision else None,
            bet_size_usdc     = bet_decision.get("size_usdc") if bet_decision else None,
            edge_pp           = bet_decision.get("edge_pp") if bet_decision else None,
            signals_used      = final_decision.get("signals_used", []),
            rationale         = final_decision.get("rationale", ""),
            kickoff           = identity_map["kickoff"],
            stage             = identity_map["stage"],
            ml_home_prob      = (ml_cons.get("home") or 0) / 100 if ml_cons else None,
            ml_draw_prob      = (ml_cons.get("draw") or 0) / 100 if ml_cons else None,
            ml_away_prob      = (ml_cons.get("away") or 0) / 100 if ml_cons else None,
            bk_home_prob      = bk_cons.get("home") if bk_cons else None,
            bk_draw_prob      = bk_cons.get("draw") if bk_cons else None,
            bk_away_prob      = bk_cons.get("away") if bk_cons else None,
            pm_home_prob      = pm_prices.get("home"),
            pm_draw_prob      = pm_prices.get("draw"),
            pm_away_prob      = pm_prices.get("away"),
            ml_market_gap     = _compute_gap(final_decision, pm_prices),
            tool_calls_made   = len(stm.tool_history),
        )
        print(f"  Saved bet_id: {bet_id[:8]}...")

        # ── Step 10: Submit to Arena ledger ───────────────────────────────────
        print(f"\nStep 7: Submitting {len(records)} records to ledger...")
        ledger_result = submit(
            records,
            fixture_id=fixture_id_str,
        )
        print(f"  Success : {ledger_result['success']}")
        print(f"  Stored  : {ledger_result['stored']}")
        if ledger_result["errors"]:
            print(f"  Errors  : {len(ledger_result['errors'])} records failed")
            for e in ledger_result["errors"]:
                print(f"    [{e.get('index')}] {e.get('message','')[:80]}")

        stm.status = "done"
        print(f"\n{'='*55}")
        print(f"Session complete — {stm.session_id}")
        print(f"{'='*55}\n")

        return {
            "session_id":    stm.session_id,
            "fixture":       identity_map["fixture_name"],
            "outcome":       final_decision.get("outcome"),
            "should_bet":    final_decision.get("should_bet"),
            "confidence":    final_decision.get("confidence_level"),
            "bet_placed":    bool(bet_decision and bet_decision.get("should_place_order")),
            "bet_size":      bet_decision.get("size_usdc") if bet_decision else None,
            "ledger_stored": ledger_result["stored"],
            "bet_id":        bet_id,
        }

    except Exception as e:
        stm.status = "error"
        print(f"\nOrchestrator error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "session_id": stm.session_id,
            "error":      str(e),
            "status":     "error",
        }


# --- Helpers -----------------------------------------------------------------

def _place_order(
    fixture_id:  int,
    team_code:   str,
    size_usdc:   float,
    limit_price: float,
) -> dict:
    size_usdc = min(size_usdc, 1.0)   # debug cap

    payload = {
        "fixture_code":          str(fixture_id),
        "team_code":             team_code,
        "usd_size":              str(round(size_usdc, 2)),
        "limit_price":           limit_price,
        "time_in_force_seconds": 30,
        "idempotency_key":       str(uuid.uuid4()),
    }
    try:
        r = requests.post(
            f"{settings.ARENA}/api/v1/arena/orders",
            headers = settings.H_ARENA,
            json    = payload,
            timeout = 30,
        )
        if r.ok:
            return r.json()
        if r.status_code == 404:
            return {"status": "not_live"}
        return {"status": "rejected", "reason": r.text[:200]}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _compute_gap(prediction: dict, pm_prices: dict) -> float | None:
    try:
        outcome    = prediction.get("outcome")
        agent_prob = float(prediction.get("probability") or 0)
        market_mid = pm_prices.get(outcome)
        if market_mid is None:
            return None
        return round((agent_prob - market_mid) * 100, 1)
    except Exception:
        return None