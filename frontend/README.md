# Trading Bot dashboard (frontend)

Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4 and shadcn/ui. It only *displays*
what the Python backend serves; all trading data and logic live in `../src/trading_bot`.

## What the dashboard shows

- **Period selector** (Today / 7 days / 30 days / All time, remembered per browser): the P&L card,
  equity chart, R histogram and trades table all cover the same period.
- **Header**: bot status, the market state in words (why it is IDLE), last cycle time, "Updated
  Ns ago" with a **Stale** badge after 2 minutes, and a **Refresh now** button (auto-refresh is 30 s).
- **Paper trading strip**: which day of the recommended 14-day paper run you are on, counted from
  the first trade (over all history, whatever period is selected). It turns into a warning if the
  bot is configured for a live account.
- **Cumulative P&L**: dollar axis, first/last trade times, and a readout you can hover or step
  through with the arrow keys.
- **Open positions**: state in words, price, stop and +1R target with distances, time held.
- **Last cycle**: entries, skipped candidates (with reasons), actions taken and any errors.
- **Recent trades**: sortable columns, symbol filter, CSV export, `est.` tag on estimated R.
- **Phones**: the sidebar becomes a top-bar menu and tables become cards; no sideways scrolling.
- **Light / dark theme** switch, remembered per browser. Gains and losses carry a ▲/▼ as well as colour.

## Run it

```bash
# 1. the backend, from the repository root (localhost:8000, read-only)
uv run serve-api

# 2. the frontend, from this folder (http://localhost:3000)
npm install
npm run dev
```

The browser only talks to this app. `next.config.ts` proxies `/api/*` to the backend
(`API_URL`, default `http://127.0.0.1:8000`), so there is no CORS to configure.

## Run it as a desktop app (Electron)

The same dashboard can run in its own window instead of the browser. Pick one:

| Mode                | Command                                  |
| ------------------- | ---------------------------------------- |
| Web (browser)       | `npm run dev`                            |
| Desktop window      | `npm run desktop` (builds, then opens)   |
| Desktop, live code  | `npm run dev` + `DESKTOP_DEV_URL=http://127.0.0.1:3000 npm run desktop:dev` |
| Executable (.exe)   | `npm run desktop:dist` -> `dist-desktop/TradingBot-<version>-portable.exe` |

How it works (`desktop/`): the desktop build is a static export of the same pages
(`BUILD_TARGET=desktop`, output in `out/`). Electron's main process serves it on a free
localhost port and forwards `/api/*` to the Python backend, exactly what the Next rewrites do
in web mode, so no page code differs. The renderer is sandboxed with no Node access.

The backend is **not** bundled in the exe. On start the app uses a backend already answering on
`API_URL` (default `http://127.0.0.1:8000`), otherwise runs `uv run serve-api` in the project
root and stops it on quit. Unpackaged, that root is the folder above `frontend/`; for the exe
set `TRADING_BOT_ROOT` to your trading-bot folder (or start `uv run serve-api` yourself). If the
backend can't be reached, the window shows the usual "Is the API running?" message.

## Scripts

| Command             | What it does                      |
| ------------------- | --------------------------------- |
| `npm run dev`       | development server                |
| `npm run build`     | production build                  |
| `npm test`          | Vitest + React Testing Library    |
| `npm run typecheck` | `tsc --noEmit`                    |
| `npm run lint`      | ESLint                            |
| `npm run e2e`       | Playwright browser tests: layout, flows and WCAG scans (first time: `npx playwright install chromium`) |
| `npm run e2e:desktop` | Playwright test of the Electron app |

## Structure

```
src/
  app/                 routes, layout, global CSS (Tailwind + theme tokens)
  components/
    ui/                shadcn primitives (generated; don't hand-edit)
    layout/            app shell and sidebar
    dashboard/         one component per card, plus the view that wires them up
  hooks/               use-dashboard (polling, period, manual refresh), use-now, use-media-query, use-active-section
  lib/                 API client, formatting, chart geometry (pure, unit-tested)
  types/               dashboard.ts: the API contract (mirrors backend api/schemas.py)
  config/              site metadata
  test/                shared fixtures
```

`e2e/` holds the Playwright tests (desktop, phone, accessibility, API-down, recovery, Electron). They
mock `/api/dashboard`, so they need neither the Python backend nor TWS; Playwright starts the dev
server itself. Next allows only one dev server per project folder, so if `npm run dev` is already
running, reuse it: `E2E_HOST=localhost E2E_PORT=3000 npm run e2e` (Next serves its scripts only to
the host it was started for).

Tests sit next to the code they cover (`*.test.ts(x)`). Tests are written before the code.

## Notes

- Colours that mean "good/bad" are driven by a `data-sign` attribute (`lib/sign.ts`), so a
  component says *what* a value is and one place decides how it looks.
- An R-multiple tagged **est.** is an estimate: no stop was recorded for that trade, so 1% of the
  entry price was used as the risk. Trades the scheduled cycle opens record their real stop.
- The light theme works by flipping Tailwind's zinc/white palette variables in `globals.css`
  (`:root:not(.dark)`), so components are written once.
- Electron 37 and electron-builder 25 are pinned because newer majors need Node 20.19+.
- Needs Node 20.9+. The test tooling is pinned for Node 20.13 (Vitest 3, jsdom 26); newer
  majors of those need Node 20.19+.
