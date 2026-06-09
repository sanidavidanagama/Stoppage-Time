"""
main.py

Entry point for Stoppage Time.
Run with: python main.py
"""

import sys
from agent.orchestrator import run


def main():
    # default fixture — Mexico vs South Africa
    home = "Mexico"
    away = "South Africa"

    # allow override from command line
    # usage: python main.py "Spain" "Saudi Arabia"
    if len(sys.argv) == 3:
        home = sys.argv[1]
        away = sys.argv[2]

    result = run(home, away)

    print("\nFinal result:")
    for key, value in result.items():
        if not key.startswith("_"):
            print(f"  {key:<20} : {value}")


if __name__ == "__main__":
    main()