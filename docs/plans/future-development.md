# Future development plans

Plans only. Nothing here is built. Each one assumes the same rules as the rest of the project:
tests first, paper account only, a library is added only when a step really needs it, and a
change ships only after two weeks of clean paper results (the dashboard's "Paper trading" strip
counts them).

Other brokers are deliberately out of scope for now (the FAQ lists it as future development):
it would mean replacing `src/trading_bot/broker/` wholesale.

---

## 1. Short selling

**Goal:** a `direction` setting in `config/rules.json` (`long_only` today; add `short_only` and
`long_short`) that mirrors the entry filters and sells to open.

**Why it is not a one-liner.** The code assumes a position is long in about a dozen places:

| Area | File | What changes |
|---|---|---|
| Entry filters | `cycle/filters.py` | A mirrored set: price below prior-day low (D1), prior close below SMA200 (D2), gap *down* of at least X% (D3), below the premarket low (I1), below today's low of day (I2); relative volume (I3) is direction-free. Keep the same `checks` shape so the dashboard needs no change. |
| Stop and size | `sizing.py` | Initial stop is high of day plus 1% (above the entry), so risk per share is `stop - entry`. |
| Orders | `broker/client.py` | `held_positions()` keeps only `position > 0`; it must return signed quantities. `place_stop` places a BUY stop. Entry is SELL-to-open. |
| Position state | `cycle/positions.py`, `cycle/manage.py` | `Position` gains `side`. R, the +0.75R partial, breakeven and the trailing stop all flip (swing *highs*, stops only move down). |
| Force close | `cycle/engine.py` | `_force_close` buys to cover instead of selling. |
| Accounting | `reporting/performance.py`, `reporting/rmultiple.py` | `pair_trades` assumes BUY opens. It needs short lots (SELL then BUY) with P&L `(entry - exit) * qty`. |
| Dashboard | `api/schemas.py`, `frontend/src/types` | `side` on positions and trades; the colour logic is sign-based, so it already works. |

**IBKR requirements to verify first (in paper):** a margin account, the symbol being shortable
(tick 236 `shortableShares`), and locates/borrow fees. Hard-to-borrow names must be skipped, with
a reason written to the decision log.

**Order of work**
1. Make accounting side-aware with long-only behaviour unchanged (all current tests stay green).
2. Make `Position` and `held_positions` signed. Same behaviour, new shape.
3. Add the mirrored filters behind `direction`, with unit tests per filter.
4. Add the short entry, stop, manage and force-close paths, tested with the existing fake broker.
5. Dry-run the filters on real data with `uv run cycle` on a weekend (no orders), then paper.

**Done when:** `long_only` results are byte-identical to today, and a paper short enters, trails
and covers with the stop restored if any step fails (the same "never leave a gap" rule as longs).

---

## 2. Options and futures

**Goal:** trade something other than US stocks without breaking the stock path.

**What breaks.** The code builds `Stock(symbol, "SMART", "USD")` in five places (`broker/client.py`,
`broker/orders.py`, `strategy.py`), sizes in shares, and assumes a price multiplier of 1. Options and futures need a contract abstraction,
not a new `if`.

**Design**
1. An `Instrument` value object (kind, symbol, expiry, strike, right, multiplier, currency) with
   `to_contract()`. Stocks are the default and produce exactly today's contract.
2. Put the multiplier into `sizing.py` and `reporting/` (options x100, futures = point value),
   and into `trades.csv` as a column so history stays correct.
3. Futures first, options second. A micro future (for example MES) has one contract per
   expiry, tight spreads and a simple stop; options need contract selection (expiry, delta,
   liquidity) and a stop on the *underlying*, because stop orders on option prices fill badly.
4. Roll handling for futures (front month changes) and expiry/assignment guards for options.
5. A separate `rules` section per instrument kind. The Trend Join Long filters are equity
   logic (gap, premarket, S&P 500 membership) and do not transfer as they are.

**Costs and limits to confirm:** options data (OPRA) and futures data are paid subscriptions,
paper accounts only see delayed or limited data, and margin rules differ per product.

**Done when:** the stock path is unchanged and tested, and one instrument type has completed a
two-week paper run with correct P&L (multiplier included) on the dashboard.

---

## 3. Strategy analysis ("Part 3")

**Goal:** let Claude read the bot's own history and propose rule changes, instead of guessing.

**Data that already exists:** `trades.csv` (fills), `safety-check-log.json` (every skipped
candidate with the exact filter checks that failed, entries with their real stop), and the
dashboard's R-multiples.

**Build**
1. `uv run analyze` writes a Markdown report from those files (read-only):
   - the filter funnel: how many candidates each of D1-D3 and I1-I3 removed;
   - R and win rate by entry hour, gap size and relative-volume bucket;
   - how often a trade reached +0.75R, breakeven, or the stop, and the average hold time;
   - how many skips *would* have worked, only where the data to say so exists.
2. A small replay harness over cached Yahoo 5-minute bars (Yahoo keeps only about 60 days,
   so the cache must be saved going forward) to compare rule variants on the same days.
3. Claude proposes a change as a `rules.json` diff, using the new `custom_filters` list so a
   test never edits strategy code. Every proposal must state the sample size.

**Guardrails.** Ignore any conclusion under about 30 trades, judge changes on days the rule
was not tuned on (walk-forward), and treat a result that only appears after many tries as noise.
A proposal goes to paper for two weeks before it is believed.

**Done when:** the report runs on today's files, and one proposed rule has been tried on paper
and written up, whether it helped or not.

---

## Decisions needed before starting any of these

- Which one first. Suggested order: short selling (reuses the most), then analysis, then
  options/futures (largest).
- Whether the paper account has margin and shorting enabled.
- Whether paid market data is acceptable for futures/options.
