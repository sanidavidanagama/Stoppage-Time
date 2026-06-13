"""
main.py

Entry point for Stoppage Time.

Local:          uv run main.py          → interactive CLI menu
GitHub Actions: uv run main.py          → auto mode (check upcoming fixture)
Manual run:     uv run main.py "Spain" "Morocco"  → run specific fixture
"""

import os
import sys


def main() -> None:
    # manual fixture override to work both locally and in CI
    if len(sys.argv) == 3:
        from agent.orchestrator import run
        run(sys.argv[1], sys.argv[2])
        return

    # GitHub Actions automated mode
    if os.getenv("GITHUB_ACTIONS") == "true":
        from data.identity import get_upcoming_fixture
        from agent.orchestrator import run

        fixture = get_upcoming_fixture(hours_ahead=1)
        if not fixture:
            print("No upcoming fixture in the next hour — exiting.")
            sys.exit(0)

        print(f"Upcoming fixture: {fixture['fixture_name']}")
        run(fixture["home"], fixture["away"])
        return

    # local interactive CLI
    from cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()