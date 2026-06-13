"""
cli.py

Interactive terminal menu for Stoppage Time.
Entry point: uv run main.py
"""

from __future__ import annotations

from agent.memory.ltm import (
    get_active_bets,
    get_all_orders,
    get_balance_map,
    update_outcome,
)
from data.identity import resolve_identity
from agent.orchestrator import run as orchestrator_run

_STARTING = 100.0


def _fmt_time(kickoff: str | None) -> str:
    if not kickoff:
        return "TBD"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        return dt.strftime("%d %b %H:%M UTC")
    except Exception:
        return str(kickoff)[:16]


def _match_code(idx: int) -> str:
    return f"M{idx:03d}"


def _idx_from_code(code: str) -> int | None:
    code = code.strip().upper()
    if code.startswith("M"):
        try:
            return int(code[1:])
        except ValueError:
            pass
    return None


def _show_active_bets(balance_map: dict | None = None) -> list[dict]:
    bets = get_active_bets()
    if balance_map is None:
        balance_map = get_balance_map(_STARTING)

    if not bets:
        print("  (no active bets)")
    else:
        for idx, bet in enumerate(bets, 1):
            code = _match_code(idx)
            home = bet.get("home_code") or bet["home_team"][:3].upper()
            away = bet.get("away_code") or bet["away_team"][:3].upper()
            time = _fmt_time(bet.get("kickoff"))
            size = f"${bet.get('bet_size_usdc') or 0:.2f}"
            edge = f"{bet.get('edge_pp') or 0:.1f}pp"
            bal  = f"${balance_map.get(bet['id'], 0):.2f}"
            print(f"  {code} | {home} v {away} | {time} | {size} | {edge} | {bal}")
    print()
    return bets


def _add_fixture() -> None:
    home = input("Enter home team: ").strip()
    away = input("Enter away team: ").strip()
    if not home or not away:
        print("Cancelled.\n")
        return

    print("Verifying...")
    try:
        identity_map = resolve_identity(home, away)
    except ValueError as e:
        print(f"Invalid fixture: {e}\n")
        return
    except Exception as e:
        print(f"Error verifying fixture: {e}\n")
        return

    fixture_name = identity_map["fixture_name"]
    kickoff      = _fmt_time(identity_map.get("kickoff"))
    print(f"Fixture: {fixture_name} | {kickoff}")

    confirm = input(
        "Are you sure you want to place a bet? "
        "The agent will reason and decide whether or not to bet (yes/no): "
    ).strip().lower()

    if confirm != "yes":
        print("Cancelled.\n")
        return

    print()
    orchestrator_run(home, away)
    print()


def _update_order_status() -> None:
    balance_map = get_balance_map(_STARTING)
    bets = _show_active_bets(balance_map)
    if not bets:
        return

    code = input("Enter match code to update (or blank to cancel): ").strip()
    if not code:
        print("Cancelled.\n")
        return

    idx = _idx_from_code(code)
    if idx is None or idx < 1 or idx > len(bets):
        print("Invalid match code.\n")
        return

    bet = bets[idx - 1]

    outcome = input("Enter actual outcome (home/draw/away): ").strip().lower()
    if outcome not in ("home", "draw", "away"):
        print("Invalid outcome. Must be home, draw, or away.\n")
        return

    try:
        pnl = float(input("Enter PnL amount (e.g. 4.50 for profit, -5.00 for loss): ").strip())
    except ValueError:
        print("Invalid PnL amount.\n")
        return

    update_outcome(bet["id"], outcome, pnl)
    print(f"Updated {code.upper()}. Outcome: {outcome} | PnL: {pnl:+.2f}\n")


def _view_past_orders() -> None:
    orders = get_all_orders(limit=50)
    balance_map = get_balance_map(_STARTING)

    if not orders:
        print("  (no orders)\n")
        return

    print()
    for idx, order in enumerate(orders, 1):
        code = _match_code(idx)
        home = order.get("home_code") or order["home_team"][:3].upper()
        away = order.get("away_code") or order["away_team"][:3].upper()
        time = _fmt_time(order.get("kickoff"))

        if order.get("should_bet"):
            size = f"${order.get('bet_size_usdc') or 0:.2f}"
            edge = f"{order.get('edge_pp') or 0:.1f}pp"
            bal  = f"${balance_map.get(order['id'], 0):.2f}"
        else:
            size = "$0.00"
            edge = "-"
            bal  = "-"

        won = order.get("won")
        pnl = order.get("pnl")
        if not order.get("should_bet"):
            pnl_str    = "-"
            result_str = "NO BET"
        elif won is None:
            pnl_str    = "PENDING"
            result_str = "PENDING"
        elif won:
            pnl_str    = f"{pnl:+.2f}" if pnl is not None else "?"
            result_str = "Profit"
        else:
            pnl_str    = f"{pnl:+.2f}" if pnl is not None else "?"
            result_str = "Loss"

        print(f"  {code} | {home} v {away} | {time} | {size} | {edge} | {bal} | {pnl_str} | {result_str}")
    print()


def main() -> None:
    balance_map = get_balance_map(_STARTING)

    print()
    print("=" * 55)
    print("  Stoppage Time")
    print("=" * 55)
    print("ACTIVE BETS")
    _show_active_bets(balance_map)

    while True:
        print("1. Add new fixture")
        print("2. Update order status")
        print("3. View past orders")
        print("0. Exit")
        print()

        choice = input("Select: ").strip()

        if choice == "1":
            print()
            _add_fixture()
        elif choice == "2":
            print()
            _update_order_status()
        elif choice == "3":
            print()
            _view_past_orders()
        elif choice == "0":
            break
        else:
            print("Invalid choice.\n")
