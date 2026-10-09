# How this app was built

A chronological record of the project, kept for memory. It was built in one continuous working
session (2026-10-08 to 2026-10-09) between the owner and Claude Code. The prompts are the owner's
requests in order; the "what came out" lines say what was delivered. Details of each feature live
in `README.md`, `frontend/README.md` and `docs/plans/future-development.md`.

## Ground rules set at the start (and kept all the way)

- **Paper account only.** The bot trades an IBKR paper account through TWS (port 7497).
- **Tests before code.** Every feature began as a failing test.
- **Libraries only when needed.** The environment started as bare Python plus pytest, and each
  dependency was added with `uv` at the moment a step required it.
- **Clean-code structure.** `src/` for the package, `tests/` for tests, small single-purpose
  modules, backend and frontend kept separate.
- **No commit, push or repo changes** on the owner's behalf.

## Phase 1: Environment and TWS connection

1. Created a `uv` environment on Python 3.14, then stripped it back to Python only ("add libraries
   when needed, not now"), then added pytest alone.
2. The owner described what they had configured in TWS (API enabled, paper login, port 7497).
3. Wrote the connection test with `ib_async` (client id 99) and ran it against the real paper TWS.
4. Moved to a standard `src/` + `tests/` layout.

## Phase 2: Orders and a strategy file

- Tests for buying and selling a position, then a strategy file and configuration
  (`config/rules.json`, `.env`, `.env.example`).
- A review of the folder structure against clean-code standards, followed by a refactor.
- Buying MU with three stop styles: percentage, fixed amount and trailing stop. IBKR rejected the
  first trailing attempt (trailing stops attach only to limit or stop-limit orders), which was
  fixed and tested.

## Phase 3: The trading bot (Step 6)

- Built the bot test-first, then ran it check-only on NVDA, then for real in paper, then sold.
- `trades.csv` initially recorded wrong prices, so the work added real fill prices, a SELL row for
  each exit, and corrections to the first BUY row and the missing SELL row. This was verified in
  tests and against the real account.

## Phase 4: Scanners and the autonomous cycle

- **S&P 500 scanner** and a **gapper scanner** (yfinance).
- **Morning prefilter** (Step 8) that writes `watchlist.txt`, run for real.
- **Autonomous trading cycle** (Step 9): filters D1-D3 (daily) and I1-I3 (intraday), position
  sizing, stop management (+0.75R partial, breakeven, trailing stop), force close, heartbeat and a
  decision log in `safety-check-log.json`. It was run once in test and once for real before moving on.
- Steps 10-12 from `prompt.txt` (safety rules, reporting, notifications).

## Phase 5: Scheduling

- `setup-schedule` registered the HT_* Windows Task Scheduler jobs; the work then checked that
  they were enabled, that disabling really stopped them, and that they could be removed.
- A Linux (cron) backend was added.
- The owner noticed a black window that flashed now and then. The cause was console tasks;
  the fix (running through `pythonw`) was deliberately left as a note to put in the README later.

## Phase 6: The dashboard

- The owner asked for backend and frontend to be clearly separated, with a Next.js base app first,
  using Tailwind, shadcn, React, NextJS and TypeScript.
- Backend: a read-only Starlette API (`serve-api`, port 8000) built from dataclasses, because
  pydantic could not be used on the Python 3.14 beta.
- Frontend (`frontend/`): Next.js 16 / React 19 dashboard with KPI cards, equity chart, R
  histogram, open positions, last cycle and a sortable trades table.
- A Playwright end-to-end suite (desktop, phone, accessibility scans, API-down and recovery cases).
- The frontend was made runnable two ways from the same code: in the browser, or as an
  Electron desktop app packaged as a portable `.exe`. Electron serves a static export and forwards
  `/api` to the Python backend.
- A dashboard review led to a round of improvements: period selector (Today / 7 days / 30 days /
  All time), market state in words, stale-data badge, manual refresh, chart readout, positions
  detail, skip reasons, CSV export and a light/dark theme, all tested on web and desktop.

## Phase 7: Hardening from the troubleshooting list (`prompt.txt`)

The owner asked which of the list's items to implement, and chose these:

| Item | Delivered |
|---|---|
| Troubleshooting | `uv run doctor` (8 checks with fixes) and a README troubleshooting table |
| Paper-only safety | Account guard that refuses a paper/live mismatch; a "Paper trading" progress strip on the dashboard (day N of 14) |
| S&P 500 list upkeep | `uv run refresh-sp500` compares the list with Wikipedia and writes nothing |
| Indicators | Optional `custom_filters` in `rules.json`, with RSI and MACD built in |
| macOS | launchd scheduler backend (unit-tested with a fake `launchctl`; not run on a real Mac) |
| IB Gateway | Only the ports documented in `.env.example`; paper stays the default |
| Planned, not built | Short selling, options/futures and strategy analysis, in `docs/plans/future-development.md` |

## Final verification (2026-10-09)

- 796 Python tests, 288 frontend unit tests, 37 web end-to-end tests and 5 Electron tests passed;
  `tsc` and `eslint` were clean.
- The real stack (live API plus dev server) and the rebuilt portable `.exe` were driven with
  Playwright, with and without the API running.
- `setup-schedule` registered 11 tasks, `doctor` passed 8/8, disable/enable worked, and
  `cleanup-schedule` removed everything again.
- Regenerable files (caches, build output, `win-unpacked`) were deleted; the `.exe` was kept.

## State at the end of this record

- No HT_* scheduled tasks are registered. Run `uv run setup-schedule` to start the bot.
- The paper run is at day 1 of 14 (first trade 2026-10-08).
- The `.exe` is unsigned, so Windows SmartScreen may warn on first run.
- Still to do: document the scheduler window-flash fix in the README, and choose which planned
  feature (short selling, analysis, options/futures) to start first.
