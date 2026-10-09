"""The 9-step cycle, with a fake broker, fake market data and a fake trade runner."""
import json
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from trading_bot.cycle.decision_log import DecisionLog
from trading_bot.cycle.engine import CycleContext, run_cycle
from trading_bot.cycle.filters import FilterResult
from trading_bot.cycle.positions import (
    STATE_BE_NO_PARTIAL,
    STATE_BE_PARTIAL,
    STATE_PRE_BREAKEVEN,
    Position,
    PositionStore,
)
from trading_bot.settings import Settings
from trading_bot.timeutil import ET
from trading_bot.trades_log import TradeLog

ENV = {
    "IBKR_HOST": "127.0.0.1", "IBKR_PORT": "7497", "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3", "PAPER_TRADING": "true",
    "PORTFOLIO_VALUE_USD": "25000", "MAX_TRADE_SIZE_USD": "2500",
    "MAX_TRADES_PER_DAY": "5", "MAX_RISK_PER_TRADE_PCT": "1.0",
}
RULES = {
    "time_filter": {"earliest_entry_et": "10:05", "latest_entry_et": "15:30", "force_close_et": "15:51"},
    "exit": {"partial_profit_trigger_R": 0.75, "breakeven_trigger_R": 1.0},
    "risk": {"max_position_size_pct_of_portfolio": 10, "max_concurrent_positions": 5},
}


def at(hour, minute):
    return datetime(2026, 10, 8, hour, minute, tzinfo=ET)  # a Thursday


class FakeBroker:
    def __init__(self):
        self.calls, self.held, self.stop_fills = [], {}, {}  # stop_fills: order id -> price
        self.next_id, self.stop_failures, self.since = 100, 0, None

    def place_order(self, symbol, side, qty):
        self.calls.append(("order", symbol, side, qty))
        if side == "SELL":
            self.held[symbol] = self.held.get(symbol, 0) - qty
        return SimpleNamespace(
            order=SimpleNamespace(orderId=self._id()),
            orderStatus=SimpleNamespace(status="Filled", avgFillPrice=105.0), log=[],
        )

    def wait_for_fill(self, trade):
        pass

    def place_stop(self, symbol, qty, price):
        self.calls.append(("stop", symbol, qty, price))
        if self.stop_failures:
            self.stop_failures -= 1
            raise RuntimeError("stop rejected")
        return self._id()

    def cancel_order_id(self, order_id):
        self.calls.append(("cancel", order_id))
        return True

    def held_positions(self):
        return {s: q for s, q in self.held.items() if q > 0}

    def wait_for_position(self, symbol, timeout=20):
        return self.held_positions().get(symbol, 0)

    def stop_fill_prices(self, since):
        self.since = since
        return dict(self.stop_fills)

    def _id(self):
        self.next_id += 1
        return self.next_id


class FakeMarketData:
    def __init__(self):
        self.snapshots, self.fail = {}, set()

    def position_snapshot(self, symbol, today):
        return self.snapshots[symbol]

    def entry_inputs(self, symbol):
        if symbol in self.fail:
            raise ConnectionError("yahoo down")
        return symbol, symbol  # sentinels; the fake evaluator looks symbols up


def pos(symbol="NVDA", state=STATE_PRE_BREAKEVEN, qty=9, stop_order_id=7, stop_price=98.0):
    return Position(
        symbol=symbol, entry_price=100.0, entry_time_iso="2026-10-08T14:00:00+00:00",
        qty=qty, initial_stop=98.0, stop_order_id=stop_order_id, state=state, R=2.0,
        stop_price=stop_price,
    )


def passing(price=100.0, low=98.0):
    return FilterResult(True, dict.fromkeys(["D1", "D2", "D3", "I1", "I2", "I3"], True), [], price, low)


def failing(*names):
    checks = dict.fromkeys(["D1", "D2", "D3", "I1", "I2", "I3"], True) | dict.fromkeys(names, False)
    return FilterResult(False, checks, list(names), 100.0, 98.0)


class Harness:
    def __init__(self, tmp_path, now=at(11, 0)):
        self.now = now
        self.broker, self.md = FakeBroker(), FakeMarketData()
        self.store = PositionStore(tmp_path / "open_positions.json")
        self.trades = TradeLog(tmp_path / "trades.csv")
        self.log = DecisionLog(tmp_path / "safety-check-log.json", clock=lambda: self.now)
        self.watchlist = tmp_path / "watchlist.txt"
        self.watchlist.write_text("# header\nNVDA  # gap +5%\n", encoding="utf-8")
        self.results, self.spawned = {}, []
        self.buy_mode = "fill"  # fill | timeout_after_fill | nofill
        self.sent = []  # (title, body, priority) of every notification
        self.notifier_error = None

    def notify(self, title, body, priority="default"):
        if self.notifier_error:
            raise self.notifier_error
        self.sent.append((title, body, priority))

    def evaluate(self, daily, intraday, rules, now):
        return self.results[daily]

    def runner(self, symbol, side, size):
        self.spawned.append((symbol, side, size))
        if self.buy_mode in ("fill", "timeout_after_fill"):
            self.broker.held[symbol] = self.broker.held.get(symbol, 0) + size
            self.trades.append({
                "timestamp_iso": "2026-10-08T15:00:00+00:00", "symbol": symbol, "side": side,
                "size": size, "fill_price": 100.1, "order_id": 1, "status": "Filled",
            })
        if self.buy_mode == "timeout_after_fill":
            raise subprocess.TimeoutExpired("trade", 30)
        return subprocess.CompletedProcess([], 0 if self.buy_mode == "fill" else 1, "", "")

    def run(self):
        ctx = CycleContext(
            settings=Settings.from_env(ENV), rules=RULES, broker=self.broker,
            market_data=self.md, store=self.store, trades=self.trades, log=self.log,
            watchlist_path=self.watchlist, clock=lambda: self.now,
            runner=self.runner, evaluate=self.evaluate, notify=self.notify,
        )
        return run_cycle(ctx)

    def events(self):
        if not self.log.path.exists():
            return []
        return [json.loads(line) for line in self.log.path.read_text().splitlines()]

    def event_names(self):
        return [e["event"] for e in self.events()]


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


class TestTimeGate:
    @pytest.mark.parametrize("now, status", [
        (datetime(2026, 10, 10, 12, 0, tzinfo=ET), "weekend"),
        (at(9, 0), "too_early"),
        (at(16, 30), "closed"),
    ])
    def test_inactive_hours_do_nothing(self, tmp_path, now, status):
        h = Harness(tmp_path, now)
        h.store.save([pos()])
        assert h.run() == status
        assert h.broker.calls == [] and h.spawned == [] and h.events() == []

    def test_returns_status_when_active(self, h):
        assert h.run() == "ok"


class TestStopOuts:
    def test_position_whose_stop_filled_is_removed(self, h):
        h.store.save([pos("NVDA", stop_order_id=7), pos("MU", stop_order_id=8)])
        h.broker.held = {"NVDA": 9, "MU": 9}
        h.broker.stop_fills = {7: 97.5}
        h.md.snapshots = {"MU": (100.0, [])}
        h.run()
        assert [p.symbol for p in h.store.load()] == ["MU"]
        assert "stopped_out" in h.event_names()

    def test_matches_by_order_id_never_by_quantity(self, h):
        # a partial leaves qty 3; an unrelated fill id must not stop it out
        h.store.save([pos("NVDA", qty=3, stop_order_id=7)])
        h.broker.held = {"NVDA": 3}
        h.broker.stop_fills = {99: 97.5}
        h.md.snapshots = {"NVDA": (100.0, [])}
        h.run()
        assert [p.symbol for p in h.store.load()] == ["NVDA"]

    def test_looks_back_one_hour(self, h):
        h.store.save([pos()])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (100.0, [])}
        h.run()
        assert (h.now - h.broker.since).total_seconds() == 3600

    def test_position_no_longer_held_is_dropped(self, h):
        h.store.save([pos("NVDA")])
        h.broker.held = {}
        h.run()
        assert h.store.load() == []
        assert "position_missing" in h.event_names()


class TestHeartbeat:
    def test_every_active_cycle_logs_a_heartbeat_with_the_gate_status(self, h):
        h.run()
        assert h.events()[0] == {"timestamp": h.now.isoformat(), "event": "cycle", "status": "ok"}

    def test_heartbeat_records_manage_only_and_force_close(self, tmp_path):
        for now, status in ((at(10, 2), "manage_only"), (at(15, 55), "force_close")):
            folder = tmp_path / status
            folder.mkdir()
            h = Harness(folder, now)
            h.run()
            assert h.events()[0]["event"] == "cycle" and h.events()[0]["status"] == status

    def test_inactive_hours_log_nothing_at_all(self, tmp_path):
        h = Harness(tmp_path, at(9, 0))
        h.run()
        assert h.events() == []


class TestNotifications:
    def test_new_entry(self, h):
        h.results = {"NVDA": passing(price=100.0, low=98.0)}
        h.run()
        assert h.sent == [("BUY NVDA", "@ $100.10, stop $97.02, qty 25", "default")]

    def test_stop_out_reports_exit_price_and_pnl(self, h):
        h.store.save([pos("NVDA", qty=9, stop_order_id=7)])  # entry 100.0
        h.broker.held = {"NVDA": 9}
        h.broker.stop_fills = {7: 97.5}
        h.run()
        assert ("STOP NVDA", "exit $97.50, P&L $-22.50", "default") in h.sent

    def test_profitable_stop_out_shows_a_plus_sign(self, h):
        h.store.save([pos("NVDA", qty=10, stop_order_id=7)])
        h.broker.held = {"NVDA": 10}
        h.broker.stop_fills = {7: 101.25}
        h.run()
        assert ("STOP NVDA", "exit $101.25, P&L $+12.50", "default") in h.sent

    def test_partial_profit(self, h):
        h.store.save([pos("NVDA", qty=9)])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (101.5, [])}
        h.run()
        assert h.sent == [("PARTIAL NVDA", "sold 3/9 @ $105.00", "default")]  # only this one

    def test_breakeven_flip(self, h):
        h.store.save([pos("NVDA", qty=9)])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (102.0, [])}
        h.run()
        assert h.sent == [("BE NVDA", "stop -> $100.00", "default")]

    def test_trailing_stop_update(self, h):
        h.store.save([pos("NVDA", state=STATE_BE_NO_PARTIAL, stop_price=100.0)])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (112.0, [110, 109, 105, 109, 110, 111])}
        h.run()
        assert h.sent == [("TRAIL NVDA", "stop $100.00 -> $104.99", "default")]

    def test_force_close_announces_how_many_positions_with_high_priority(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.store.save([pos("NVDA", stop_order_id=7), pos("MU", stop_order_id=8)])
        h.broker.held = {"NVDA": 9, "MU": 9}
        h.run()
        assert h.sent == [("EOD Force Close", "flattening 2 positions", "high")]

    def test_force_close_with_nothing_open_stays_quiet(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.run()
        assert h.sent == []

    def test_no_news_is_no_notification(self, h):
        h.store.save([pos("NVDA")])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (100.5, [])}
        h.run()
        assert h.sent == []

    def test_a_failing_notifier_never_breaks_trading(self, h):
        h.notifier_error = RuntimeError("telegram is down")
        h.results = {"NVDA": passing()}
        h.run()
        assert h.spawned == [("NVDA", "BUY", 25)]
        assert [p.symbol for p in h.store.load()] == ["NVDA"]  # entry still saved

    def test_failing_notifier_does_not_break_management_or_force_close(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.notifier_error = RuntimeError("telegram is down")
        h.store.save([pos("NVDA", stop_order_id=7)])
        h.broker.held = {"NVDA": 9}
        h.run()
        assert ("order", "NVDA", "SELL", 9) in h.broker.calls and h.store.load() == []


class TestUntrackedPositions:
    def test_broker_position_missing_from_the_state_file_is_flagged_critical(self, h):
        h.broker.held = {"BBY": 28}
        h.watchlist.write_text("", encoding="utf-8")
        h.run()
        (e,) = [e for e in h.events() if e["event"] == "untracked_position"]
        assert (e["symbol"], e["qty"], e["critical"]) == ("BBY", 28, True)

    def test_tracked_positions_are_not_flagged(self, h):
        h.store.save([pos("NVDA")])
        h.broker.held = {"NVDA": 9}
        h.md.snapshots = {"NVDA": (100.0, [])}
        h.run()
        assert "untracked_position" not in h.event_names()


class TestManagement:
    def setup_position(self, h, **kw):
        h.store.save([pos(**kw)])
        h.broker.held = {"NVDA": kw.get("qty", 9)}

    def test_breakeven_moves_stop_to_entry(self, h):
        self.setup_position(h)
        h.md.snapshots = {"NVDA": (102.0, [])}
        h.run()
        assert h.broker.calls[:2] == [("cancel", 7), ("stop", "NVDA", 9, 100.0)]
        (p,) = h.store.load()
        assert p.state == STATE_BE_NO_PARTIAL and p.stop_price == 100.0
        assert p.stop_order_id != 7

    def test_partial_sells_a_third_and_restops_remaining_at_99pct(self, h):
        self.setup_position(h)
        h.md.snapshots = {"NVDA": (101.5, [])}
        h.run()
        assert h.broker.calls[:3] == [
            ("cancel", 7), ("order", "NVDA", "SELL", 3), ("stop", "NVDA", 6, 99.0),
        ]
        (p,) = h.store.load()
        assert (p.qty, p.state, p.stop_price) == (6, STATE_BE_PARTIAL, 99.0)
        sell = h.trades.last_row()
        assert (sell["side"], sell["size"], sell["fill_price"]) == ("SELL", "3", "105.0")

    def test_trailing_ratchets_stop_up_to_swing_low(self, h):
        self.setup_position(h, state=STATE_BE_NO_PARTIAL, stop_price=100.0)
        h.md.snapshots = {"NVDA": (112.0, [110, 109, 105, 109, 110, 111])}
        h.run()
        assert h.broker.calls[:2] == [("cancel", 7), ("stop", "NVDA", 9, 104.99)]
        assert h.store.load()[0].stop_price == 104.99

    def test_no_change_means_no_broker_calls(self, h):
        self.setup_position(h)
        h.md.snapshots = {"NVDA": (100.5, [])}
        h.run()
        assert h.broker.calls == []

    def test_failed_new_stop_restores_the_old_one(self, h):
        self.setup_position(h)
        h.md.snapshots = {"NVDA": (102.0, [])}
        h.broker.stop_failures = 1
        h.run()
        assert h.broker.calls == [
            ("cancel", 7), ("stop", "NVDA", 9, 100.0), ("stop", "NVDA", 9, 98.0),
        ]
        (p,) = h.store.load()
        assert p.stop_price == 98.0 and p.state == STATE_PRE_BREAKEVEN
        assert "stop_move_failed" in h.event_names()

    def test_missing_market_data_skips_that_position_only(self, h):
        h.store.save([pos("NVDA", stop_order_id=7), pos("MU", stop_order_id=8)])
        h.broker.held = {"NVDA": 9, "MU": 9}
        h.md.snapshots = {"MU": (102.0, [])}  # NVDA missing -> KeyError
        h.run()
        assert ("stop", "MU", 9, 100.0) in h.broker.calls
        assert "manage_skipped" in h.event_names()

    def test_manage_only_window_still_manages(self, tmp_path):
        h = Harness(tmp_path, at(10, 2))
        self.setup_position(h)
        h.md.snapshots = {"NVDA": (102.0, [])}
        assert h.run() == "manage_only"
        assert ("stop", "NVDA", 9, 100.0) in h.broker.calls
        assert h.spawned == []


class TestForceClose:
    def test_cancels_all_stops_sells_everything_and_clears_state(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.store.save([pos("NVDA", qty=9, stop_order_id=7), pos("MU", qty=3, stop_order_id=8)])
        h.broker.held = {"NVDA": 9, "MU": 3}
        assert h.run() == "force_close"
        assert h.broker.calls == [
            ("cancel", 7), ("order", "NVDA", "SELL", 9),
            ("cancel", 8), ("order", "MU", "SELL", 3),
        ]
        assert h.store.load() == [] and h.spawned == []
        assert h.event_names().count("force_close") == 2

    def test_whole_share_quantities_are_logged_as_integers(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.store.save([pos("NVDA", qty=9)])
        h.broker.held = {"NVDA": 9.0}  # the broker reports positions as floats
        h.run()
        assert h.trades.last_row()["size"] == "9"

    def test_sells_the_quantity_actually_held(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.store.save([pos("NVDA", qty=9)])
        h.broker.held = {"NVDA": 6}  # a partial was filled but the file is stale
        h.run()
        assert ("order", "NVDA", "SELL", 6) in h.broker.calls

    def test_no_new_entries_during_force_close(self, tmp_path):
        h = Harness(tmp_path, at(15, 55))
        h.results = {"NVDA": passing()}
        h.run()
        assert h.spawned == []


class TestEntryScan:
    def test_enters_on_passing_ticker_with_risk_based_size_and_stop(self, h):
        h.results = {"NVDA": passing(price=100.0, low=98.0)}
        h.run()
        # initial stop 98 * 0.99 = 97.02; R ~ 2.98 -> 83 by risk, 25 by 10% cap
        assert h.spawned == [("NVDA", "BUY", 25)]
        assert ("stop", "NVDA", 25, 97.02) in h.broker.calls
        (p,) = h.store.load()
        assert (p.symbol, p.qty, p.initial_stop, p.state) == ("NVDA", 25, 97.02, STATE_PRE_BREAKEVEN)
        assert p.entry_price == 100.1  # real fill price from trades.csv
        assert p.R == pytest.approx(100.1 - 97.02)
        assert p.stop_order_id > 100
        assert "entered" in h.event_names()

    def test_reads_watchlist_skipping_comment_lines(self, h):
        h.watchlist.write_text("# NVDA\nMU  # gap\n\nAAPL\n", encoding="utf-8")
        h.results = {"MU": failing("D1"), "AAPL": failing("I3")}
        h.run()
        skipped = [e["symbol"] for e in h.events() if e["event"] == "entry_skipped"]
        assert skipped == ["MU", "AAPL"]

    def test_skips_tickers_already_held_without_evaluating(self, h):
        h.broker.held = {"NVDA": 5}
        h.results = {}  # evaluating NVDA would KeyError
        h.run()
        assert h.spawned == [] and "entry_skipped" in h.event_names()

    def test_failed_filters_are_logged_with_reasons_and_not_traded(self, h):
        h.results = {"NVDA": failing("D1", "I3")}
        h.run()
        (e,) = [e for e in h.events() if e["event"] == "entry_skipped"]
        assert e["reasons"] == ["D1", "I3"] and h.spawned == []

    def test_size_below_one_share_is_skipped(self, h):
        h.results = {"NVDA": passing(price=3000.0, low=2900.0)}
        h.run()
        assert h.spawned == [] and "entry_skipped" in h.event_names()

    def test_daily_trade_cap_stops_scanning(self, h):
        for _ in range(5):
            h.trades.append({"timestamp_iso": "2026-10-08T15:00:00+00:00", "symbol": "X",
                             "side": "BUY", "size": 1, "fill_price": 1, "order_id": 1, "status": "Filled"})
        h.results = {"NVDA": passing()}
        h.run()
        assert h.spawned == [] and "max_trades_reached" in h.event_names()

    def test_max_concurrent_positions_stops_scanning(self, h):
        h.store.save([pos(f"S{i}", stop_order_id=10 + i) for i in range(5)])
        h.broker.held = {f"S{i}": 9 for i in range(5)}
        h.md.snapshots = {f"S{i}": (100.0, []) for i in range(5)}
        h.results = {"NVDA": passing()}
        h.run()
        assert h.spawned == [] and "max_positions_reached" in h.event_names()

    def test_stops_scanning_once_slots_fill_up(self, h):
        h.store.save([pos(f"S{i}", stop_order_id=10 + i) for i in range(4)])
        h.broker.held = {f"S{i}": 9 for i in range(4)}
        h.md.snapshots = {f"S{i}": (100.0, []) for i in range(4)}
        h.watchlist.write_text("AAA\nBBB\n", encoding="utf-8")
        h.results = {"AAA": passing(), "BBB": passing()}
        h.run()
        assert [s[0] for s in h.spawned] == ["AAA"]

    def test_data_error_on_one_ticker_does_not_abort_the_scan(self, h):
        h.watchlist.write_text("BAD\nNVDA\n", encoding="utf-8")
        h.md.fail = {"BAD"}
        h.results = {"NVDA": passing()}
        h.run()
        assert [s[0] for s in h.spawned] == ["NVDA"]
        assert "entry_error" in h.event_names()

    def test_subprocess_timeout_after_fill_still_gets_a_stop(self, h):
        h.buy_mode = "timeout_after_fill"
        h.results = {"NVDA": passing()}
        h.run()
        assert ("stop", "NVDA", 25, 97.02) in h.broker.calls
        assert len(h.store.load()) == 1

    def test_failed_buy_with_no_position_records_nothing(self, h):
        h.buy_mode = "nofill"
        h.results = {"NVDA": passing()}
        h.run()
        assert h.store.load() == [] and not any(c[0] == "stop" for c in h.broker.calls)
        assert "entry_failed" in h.event_names()

    def test_unprotectable_entry_is_sold_back(self, h):
        h.broker.stop_failures = 1
        h.results = {"NVDA": passing()}
        h.run()
        assert ("order", "NVDA", "SELL", 25) in h.broker.calls
        assert h.store.load() == []
        assert "entry_aborted_unprotected" in h.event_names()

    def test_state_is_saved_after_each_entry(self, h):
        h.watchlist.write_text("AAA\nBBB\n", encoding="utf-8")
        h.results = {"AAA": passing(), "BBB": passing()}
        h.run()
        assert [p.symbol for p in h.store.load()] == ["AAA", "BBB"]
