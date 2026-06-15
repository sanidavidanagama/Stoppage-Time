# Stoppage-Time API Documentation

Base URL (local): `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

---

## Authentication

The API uses **JWT Bearer tokens**. There is a single admin user configured via environment variables — no signup.

### POST `/auth/login`

Authenticate and receive a JWT token (valid 7 days).

**Request** — `application/x-www-form-urlencoded`

| Field | Type | Description |
|-------|------|-------------|
| `username` | string | Admin username (`ADMIN_USERNAME` env var) |
| `password` | string | Admin password (`ADMIN_PASSWORD` env var) |

**Response `200`**

```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

**Response `401`**

```json
{ "detail": "Incorrect username or password" }
```

---

## Public Endpoints

No authentication required.

### GET `/api/public/stats`

Agent performance summary for the public stats page.

**Response `200`**

```json
{
  "bets_won": 12,
  "bets_lost": 5,
  "win_rate": 70.6,
  "total_pnl": 28.40,
  "current_balance": 128.40,
  "agent_status": "active",
  "next_scheduled_run": "2026-06-16T14:15:00+00:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `bets_won` | int | Bets with `won=1` |
| `bets_lost` | int | Bets with `won=0` |
| `win_rate` | float | Win percentage (0–100) |
| `total_pnl` | float | Total profit/loss in USDC |
| `current_balance` | float | Starting $100 + total PnL |
| `agent_status` | string | `"active"` if a run is in progress, else `"inactive"` |
| `next_scheduled_run` | string \| null | ISO 8601 UTC timestamp of the next pending queue entry |

---

## Protected Endpoints

All requests must include `Authorization: Bearer <token>`.

**`401` response** (missing or invalid token):
```json
{ "detail": "Could not validate credentials" }
```

---

### GET `/api/stats`

Full agent stats for the admin dashboard.

**Response `200`**

```json
{
  "total_bets": 20,
  "bets_won": 12,
  "bets_lost": 5,
  "skipped_bets": 3,
  "win_percentage": 70.6,
  "total_pnl": 28.40,
  "highest_profit": 11.20,
  "highest_loss": -8.50,
  "wallet_balance": 128.40,
  "next_run_seconds": 3240,
  "next_run_human": "54 min",
  "agent_status": "inactive"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `total_bets` | int | All bets where `should_bet=1` |
| `bets_won` | int | Resolved correct predictions |
| `bets_lost` | int | Resolved incorrect predictions |
| `skipped_bets` | int | Runs where `should_bet=0` (no bet placed) |
| `win_percentage` | float | Win rate as a percentage |
| `total_pnl` | float | Sum of all resolved PnL in USDC |
| `highest_profit` | float | Best single bet PnL |
| `highest_loss` | float | Worst single bet PnL (negative) |
| `wallet_balance` | float | Current estimated balance in USDC |
| `next_run_seconds` | int \| null | Seconds until the next scheduled agent run |
| `next_run_human` | string \| null | Human-readable countdown e.g. `"1h 12min"`, `"54 min"` |
| `agent_status` | string | `"active"` or `"inactive"` |

---

### GET `/api/bets`

Paginated list of all bet decisions.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | `1` | Page number |
| `per_page` | int | `20` | Items per page (max 100) |
| `status` | string | — | Filter: `active` \| `resolved` \| `no_bet` |

- `active` — placed bets awaiting result (`should_bet=1`, `won IS NULL`)
- `resolved` — completed bets (`should_bet=1`, `won IS NOT NULL`)
- `no_bet` — runs where the agent decided not to bet (`should_bet=0`)

**Response `200`**

```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "home": "Brazil",
      "away": "Argentina",
      "result": "won",
      "pnl": 8.40,
      "agent_prediction": "home",
      "market_price": 0.62,
      "edge": 11.5,
      "stake": 10.0,
      "actual_outcome": "home"
    }
  ],
  "total": 20,
  "page": 1,
  "per_page": 20,
  "total_pages": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Bet record ID |
| `home` / `away` | string | Team names |
| `result` | string | `"won"` \| `"lost"` \| `"pending"` |
| `pnl` | float \| null | Profit/loss in USDC (null if pending) |
| `agent_prediction` | string | `"home"` \| `"draw"` \| `"away"` |
| `market_price` | float \| null | Polymarket probability for the predicted outcome |
| `edge` | float \| null | Edge in percentage points |
| `stake` | float \| null | Amount wagered in USDC |
| `actual_outcome` | string \| null | Real match result once known |

---

### GET `/api/bets/{bet_id}`

Full details for a single bet.

**Path Parameters**

| Param | Type | Description |
|-------|------|-------------|
| `bet_id` | UUID | Bet record ID |

**Response `200`** — all columns from the `bets` table:

```json
{
  "id": "550e8400-...",
  "session_id": "prematch:12345",
  "created_at": "2026-06-15T12:00:00+00:00",
  "fixture_name": "Brazil vs Argentina",
  "kickoff": "2026-06-16T15:00:00+00:00",
  "stage": "Group Stage",
  "home_team": "Brazil",
  "away_team": "Argentina",
  "home_code": "BRA",
  "away_code": "ARG",
  "predicted_outcome": "home",
  "agent_probability": 0.72,
  "confidence_level": "high",
  "should_bet": 1,
  "bet_outcome": "home",
  "bet_direction": "long",
  "bet_size_usdc": 10.0,
  "edge_pp": 11.5,
  "actual_outcome": "home",
  "pnl": 8.40,
  "won": 1,
  "rationale": "Strong ML signal...",
  "signals_used": "[\"ml\", \"polymarket\", \"form\"]",
  "tool_calls_made": 4,
  "notes": null,
  "ml_home_prob": 0.62,
  "ml_away_prob": 0.22,
  "ml_draw_prob": 0.16,
  "bk_home_prob": 0.55,
  "bk_away_prob": 0.28,
  "bk_draw_prob": 0.17,
  "pm_home_prob": 0.60,
  "pm_away_prob": 0.25,
  "pm_draw_prob": 0.15,
  "ml_market_gap": 2.0
}
```

**Response `404`**
```json
{ "detail": "Bet not found" }
```

---

### GET `/api/bets/{bet_id}/logs`

All reasoning logs for a match via its bet ID. Convenience shortcut — delegates to `GET /api/logs/{session_id}` internally.

**Response `200`**

```json
{
  "bet_id": "550e8400-...",
  "session_id": "prematch:12345",
  "logs": {
    "tactics_prompt":     [{ "round": 1, "content": "..." }],
    "tactics_response":   [{ "round": 1, "content": "..." }],
    "reasoning_prompt":   [{ "round": 1, "content": "..." }, { "round": 2, "content": "..." }],
    "reasoning_response": [{ "round": 1, "content": "..." }, { "round": 2, "content": "..." }],
    "bet_prompt":         [{ "round": 1, "content": "..." }],
    "bet_response":       [{ "round": 1, "content": "..." }]
  }
}
```

---

## Log Endpoints (Protected)

These endpoints let you browse and manage logs **directly by session**, without needing a `bet_id`. This is the primary way to access logs for runs where no bet was placed (`should_bet=0`) or where the agent crashed before saving a bet record.

---

### GET `/api/logs`

List every session that has log entries, most recent first. Includes sessions with no bet placed.

**Response `200`**

```json
[
  {
    "session_id": "prematch:19609162",
    "fixture_name": "Spain vs Cape Verde Islands",
    "created_at": "2026-06-15T12:09:10+00:00",
    "log_types": ["bet_prompt", "bet_response", "reasoning_prompt", "reasoning_response", "tactics_prompt", "tactics_response"],
    "log_count": 6,
    "has_bet": true,
    "bet_placed": false,
    "bet_id": "078ccf7b-..."
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session identifier, format `prematch:{fixture_id}` |
| `fixture_name` | string | Human-readable match name |
| `log_types` | string[] | Log types present for this session |
| `log_count` | int | Number of distinct log types recorded |
| `has_bet` | bool | `true` if a bet record exists in the `bets` table |
| `bet_placed` | bool | `true` if `should_bet=1` (an actual order was attempted) |
| `bet_id` | UUID \| null | Linked bet record ID, or null if none |

---

### GET `/api/logs/{session_id}`

Fetch all logs for a session directly by `session_id`. Works even when no bet was placed.

**Path Parameter**

| Param | Type | Description |
|-------|------|-------------|
| `session_id` | string | URL-encode the colon: `prematch%3A19609162` |

**Response `200`**

```json
{
  "session_id": "prematch:19609162",
  "bet_id": "078ccf7b-...",
  "bet_placed": false,
  "logs": {
    "tactics_prompt":     [{ "round": 1, "content": "..." }],
    "tactics_response":   [{ "round": 1, "content": "..." }],
    "reasoning_prompt":   [{ "round": 1, "content": "..." }],
    "reasoning_response": [{ "round": 1, "content": "..." }],
    "bet_prompt":         [{ "round": 1, "content": "..." }],
    "bet_response":       [{ "round": 1, "content": "..." }]
  }
}
```

**Response `404`**
```json
{ "detail": "No logs found for this session" }
```

---

### DELETE `/api/logs/{session_id}`

Delete all log rows for a session. Does **not** delete the corresponding bet record.

**Path Parameter** — same as `GET /api/logs/{session_id}`, URL-encode the colon.

**Response `204`** — no content.

**Response `404`**
```json
{ "detail": "No logs found for this session" }
```

---

### PUT `/api/bets/{bet_id}/outcome`

Update a bet's actual match result and P&L after the game has concluded.

**Request Body** — `application/json`

```json
{
  "actual_outcome": "home",
  "pnl": 8.40
}
```

| Field | Type | Description |
|-------|------|-------------|
| `actual_outcome` | string | Real match result: `"home"` \| `"draw"` \| `"away"` |
| `pnl` | float | Profit (positive) or loss (negative) in USDC |

The `won` field is computed automatically: `1` if `predicted_outcome == actual_outcome`, else `0`.

**Response `200`**
```json
{ "ok": true, "bet_id": "550e8400-..." }
```

**Response `404`**
```json
{ "detail": "Bet not found" }
```

---

### GET `/api/queue`

List all match queue entries with live countdown fields.

**Response `200`**

```json
[
  {
    "id": "a1b2c3d4-...",
    "home_team": "France",
    "away_team": "Germany",
    "kickoff_time": "2026-06-16T15:00:00+00:00",
    "scheduled_run_time": "2026-06-16T14:15:00+00:00",
    "status": "pending",
    "session_id": null,
    "error_message": null,
    "created_at": "2026-06-15T10:00:00+00:00",
    "updated_at": "2026-06-15T10:00:00+00:00",
    "seconds_until_run": 3240,
    "seconds_until_kickoff": 5940
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"pending"` \| `"running"` \| `"done"` \| `"failed"` |
| `session_id` | string \| null | Links to logs/bets after run completes |
| `seconds_until_run` | int | Seconds until the agent fires (0 if overdue or done) |
| `seconds_until_kickoff` | int | Seconds until kickoff (0 if past) |

---

### POST `/api/queue`

Add a match to the queue. The agent will run automatically 45 minutes before kickoff.

**Request Body** — `application/json`

```json
{
  "home_team": "France",
  "away_team": "Germany",
  "kickoff_time": "2026-06-16T15:00:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `home_team` | string | Home team name (must match Sportmonks naming) |
| `away_team` | string | Away team name |
| `kickoff_time` | string | ISO 8601 UTC timestamp of kickoff |

`scheduled_run_time` is automatically computed as `kickoff_time - 45 minutes`.

**Response `201`** — the created entry with countdown fields (same shape as `GET /api/queue` items).

---

### DELETE `/api/queue/{entry_id}`

Remove a match from the queue.

**Response `204`** — no content.

**Response `404`**
```json
{ "detail": "Queue entry not found" }
```

**Response `409`** (if the entry is currently running)
```json
{ "detail": "Cannot remove a running entry" }
```

---

### POST `/api/queue/{entry_id}/run`

Immediately trigger the agent for a queued match, bypassing the countdown. The entry is cleared from the queue (moved to `done` or `failed`) after the run.

**Response `200`** — the updated queue entry with countdown fields.

**Response `404`**
```json
{ "detail": "Queue entry not found" }
```

**Response `409`**
```json
{ "detail": "Entry is already running" }
```

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid Bearer token |
| `404` | Resource not found |
| `409` | Conflict (e.g. entry already running) |
| `422` | Validation error — request body malformed |

---

## Supabase Setup

Before running the backend, create the `match_queue` table in your LTM Supabase project (`ST_SUPABASE`):

```sql
CREATE TABLE match_queue (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    home_team          TEXT NOT NULL,
    away_team          TEXT NOT NULL,
    kickoff_time       TIMESTAMPTZ NOT NULL,
    scheduled_run_time TIMESTAMPTZ NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'done', 'failed')),
    session_id         TEXT,
    error_message      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_match_queue_scheduler ON match_queue (status, scheduled_run_time)
    WHERE status = 'pending';
```

---

## Running Locally

```bash
# Copy and fill in your secrets
cp .env.example .env

# Start the server
uv run main.py serve
```

Server starts at `http://localhost:8000`.  
Interactive Swagger UI: `http://localhost:8000/docs`

---

## Deployment

The backend must run as a **persistent server** (not serverless) because the scheduler needs to stay alive. Recommended platforms: Render, Railway, Fly.io.

The `Procfile` at the repo root is pre-configured:

```
web: uv run main.py serve
```

Set these environment variables on your hosting platform (in addition to the existing agent secrets):

```
ADMIN_USERNAME
ADMIN_PASSWORD
JWT_SECRET_KEY
ALLOWED_ORIGINS   # comma-separated frontend origins
PORT              # set automatically by most platforms
```
