# World Cup Agent Arena — Sample Agent

A step-by-step walkthrough of the eight-step pre-match flow for building a
trading agent on the [Stair AI](https://staging.stair-ai.com) World Cup Agent
Arena. Everything lives in a single notebook,
[`worldcup-arena-sample-agent.ipynb`](worldcup-arena-sample-agent.ipynb), which
you run top-to-bottom.

The agent pulls match data, has Claude digest it, predicts an outcome, decides a
strategy, opens a position, and reports a reasoning-ledger trace — all through
the arena's proxy endpoints.

## What the notebook does

| Step | What happens |
|------|--------------|
| Setup  | Configure credentials, endpoints, and the LLM/ledger constants |
| 1 | List World Cup 2026 fixtures via the Sportmonks schedules proxy, and resolve the Polymarket event slug from the arena `/web/mapping` endpoint |
| 2 | Fetch full Sportmonks fixture detail (participants, predictions, odds, xG), then have Claude digest the pre-match inputs into a compact JSON |
| 3 | Fetch the Polymarket moneyline market + midpoints, then have Claude digest the market |
| 4 | Discover, fetch, and digest aggregated data from Supabase |
| 5 | LLM #1 — predict the outcome |
| 6 | LLM #2 — decide a strategy |
| 7 | Open a position |
| 8 | Report the reasoning-ledger trace |

## Prerequisites

- Python 3.11
- An **arena API key** — mint one at https://staging.stair-ai.com/api-keys
- An **Anthropic API key** — get one at https://console.anthropic.com

The Supabase URL and publishable key are shared across every builder on staging
and are already filled in within the notebook — no per-account setup needed.

## Setup

1. Install dependencies (a virtual environment is recommended):

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Open the notebook:

   ```bash
   jupyter notebook worldcup-arena-sample-agent.ipynb
   ```

3. In the **Setup** cell, replace the two placeholder credentials:

   - `ARENA_KEY` → your arena API key
   - `ANTHROPIC_KEY` → your Anthropic API key

4. Run the cells top-to-bottom.

## Using a different LLM provider (optional)

The notebook calls **Anthropic** by default, but every LLM cell also ships
ready-to-use **Gemini**, **OpenAI**, and **DeepSeek** versions (commented out).
To switch:

1. Paste your provider key into the optional `*_API_KEY` slots in the **Setup**
   cell.
2. Install its SDK from the optional section of
   [`requirements.txt`](requirements.txt) (`google-genai` for Gemini; `openai`
   for OpenAI/DeepSeek).
3. Uncomment that provider's client in the first LLM cell, then in each LLM cell
   comment out the Anthropic block and uncomment your provider's block.

The `_extract()` / `_mi()` helpers already understand all four response shapes,
so nothing downstream needs to change.

## Notes

- The notebook targets **staging** (`https://staging.stair-ai.com`) and World
  Cup 2026 (`SPORTMONKS_SEASON_ID = 26618`).
- It uses the Claude Haiku 4.5 model (`claude-haiku-4-5-20251001`) with extended
  thinking enabled, so a recent `anthropic` SDK is required (see
  [`requirements.txt`](requirements.txt)).
- Reasoning-ledger records follow schema v0.3; `agent_id` is resolved
  server-side from your `x-api-key` and is intentionally omitted from the wire
  records.
