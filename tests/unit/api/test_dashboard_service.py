import csv
import json
from datetime import datetime, timedelta

import pytest

from trading_bot.api.service import DashboardService
from trading_bot.api.sources import DecisionLogReader
from trading_bot.cycle.positions import (
    STATE_BE_PARTIAL,
    STATE_PRE_BREAKEVEN,
    Position,
    PositionStore,
)
from trading_bot.timeutil import ET
from trading_bot.trades_log import HEADER

NOW = datetime(2026, 10, 8, 17, 0, tzinfo=ET)


def utc(hhmm, day="2026-10-08"):
    return f"{day}T{hhmm}:00+00:00"  # 14:00Z is 10:00 ET


def trade_rows(symbol, buy, sell, qty=10, open_="14:00", close="15:00", day="2026-10-08"):
    return [
        {"timestamp_iso": utc(open_, day), "symbol": symbol, "side": "BUY", "size": qty,
         "fill_price": buy, "order_id": 1, "status": "Filled"},
        {"timestamp_iso": utc(close, day), "symbol": symbol, "side": "SELL", "size": qty,
         "fill_price": sell, "order_id": 2, "status": "Filled"},
    ]


class FakePrices:
    def __init__(self, prices=None):
        self.prices, self.asked = prices or {}, []

    def latest(self, symbols):
        self.asked.append(list(symbols))
        return {s: self.prices[s] for s in symbols if s in self.prices}


class Env:
    def __init__(self, tmp_path, now=NOW, prices=None):
        self.trades_path = tmp_path / "trades.csv"
        self.positions = PositionStore(tmp_path / "open_positions.json")
        self.log_path = tmp_path / "safety-check-log.json"
        self.prices = FakePrices(prices)
        self.now = now

    def write_trades(self, rows):
        with self.trades_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows(rows)

    def write_log(self, events):
        self.log_path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    def service(self, **kw):
        return DashboardService(
            trades_path=self.trades_path, positions=self.positions,
            decision_log=DecisionLogReader(self.log_path), prices=self.prices,
            clock=lambda: self.now, **{"gate": lambda now: "ok", **kw},
        )

    def data(self, period="today", **kw):
        return self.service(**kw).dashboard(period)


def position(symbol="NVDA", **kw):
    base = dict(symbol=symbol, entry_price=100.0, entry_time_iso="2026-10-08T14:00:00+00:00",
                qty=9, initial_stop=98.0, stop_order_id=7, state=STATE_PRE_BREAKEVEN, R=2.0)
    return Position(**{**base, **kw})


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


class TestEmpty:
    def test_nothing_on_disk_gives_a_valid_empty_dashboard(self, env):
        d = env.data()
        assert d.generated_at == NOW.isoformat()
        assert d.summary.total_trades == 0 and d.summary.profit_factor == "n/a"
        assert (d.period, d.summary.from_date, d.summary.to_date) == ("today", "2026-10-08", "2026-10-08")
        assert d.cycle is None
        assert d.open_positions == [] and d.recent_trades == [] and d.equity_curve == []
        assert [b.count for b in d.r_histogram] == [0] * 7 and len(d.r_histogram) == 7
        assert d.warnings == []

    def test_nothing_on_disk_means_no_cycle_data_yet(self, env):
        s = env.data().status
        assert (s.bot_status, s.last_cycle_at, s.last_event) == ("NO_DATA", None, None)
        assert s.message == "no cycle data yet"


class TestSummary:
    def test_summary_counts_only_trades_closed_today(self, env):
        env.write_trades(trade_rows("NVDA", 100, 102) + trade_rows("OLD", 100, 90, day="2026-10-07"))
        t = env.data().summary
        assert (t.total_trades, t.wins, t.losses) == (1, 1, 0)
        assert t.gross_pnl_usd == pytest.approx(20.0) and t.win_rate_pct == 100.0
        assert t.profit_factor == "inf"
        assert t.largest_winner == {"symbol": "NVDA", "pnl_usd": 20.0}

    def test_numeric_profit_factor(self, env):
        env.write_trades(trade_rows("A", 100, 110) + trade_rows("B", 100, 95))
        assert env.data().summary.profit_factor == pytest.approx(2.0)


class TestRecentTrades:
    def test_newest_first_with_r_and_its_source(self, env):
        env.write_trades(trade_rows("EARLY", 100, 101, open_="14:00", close="14:30")
                         + trade_rows("LATE", 100, 102, open_="15:00", close="16:00"))
        late, early = env.data(period="all").recent_trades
        assert (late.symbol, early.symbol) == ("LATE", "EARLY")
        assert late.pnl_usd == pytest.approx(20.0) and late.exit_price == 102.0
        assert late.r_multiple == pytest.approx(2.0) and late.r_source == "proxy"
        assert late.closed_at.endswith("-04:00") and late.hold_minutes == 60

    def test_r_comes_from_the_decision_log_when_available(self, env):
        env.write_trades(trade_rows("NVDA", 100, 102))
        env.write_log([{"timestamp": "2026-10-08T10:00:20-04:00", "event": "entered",
                        "symbol": "NVDA", "stop": 98.0}])
        (t,) = env.data(period="all").recent_trades
        assert t.r_source == "decision_log" and t.r_multiple == pytest.approx(1.0)

    def test_limited_to_the_most_recent_twenty_by_default(self, env):
        rows = []
        for i in range(25):
            rows += trade_rows(f"S{i:02d}", 100, 101, open_=f"14:{i:02d}", close=f"15:{i:02d}")
        env.write_trades(rows)
        trades = env.data(period="all").recent_trades
        assert len(trades) == 20 and trades[0].symbol == "S24" and trades[-1].symbol == "S05"

    def test_limit_is_configurable(self, env):
        env.write_trades(trade_rows("A", 100, 101) + trade_rows("B", 100, 101, close="15:30"))
        assert len(env.data(recent_limit=1, period="all").recent_trades) == 1


class TestHistogramAndEquity:
    def test_histogram_follows_the_selected_period(self, env):
        env.write_trades(trade_rows("WIN", 100, 102)                          # proxy R = +2
                         + trade_rows("LOSS", 100, 98, day="2026-10-07"))     # proxy R = -2
        assert sum(b.count for b in env.data().r_histogram) == 1
        counts = {b.label: b.count for b in env.data(period="all").r_histogram}
        assert counts["+1R to +2R"] == 1 and counts["≤ -2R"] == 1 and sum(counts.values()) == 2

    def test_equity_curve_is_cumulative_in_closing_order(self, env):
        env.write_trades(trade_rows("A", 100, 102, close="15:00")      # +20
                         + trade_rows("B", 100, 99, open_="15:10", close="16:00")   # -10
                         + trade_rows("C", 100, 101, open_="16:10", close="17:00"))  # +10
        curve = env.data(period="all").equity_curve
        assert [p.pnl_usd for p in curve] == pytest.approx([20.0, -10.0, 10.0])
        assert [p.cumulative_pnl_usd for p in curve] == pytest.approx([20.0, 10.0, 20.0])
        assert curve[0].closed_at < curve[1].closed_at < curve[2].closed_at
        assert [p.symbol for p in curve] == ["A", "B", "C"]


class TestPeriods:
    @pytest.fixture
    def spread(self, env):
        env.write_trades(
            trade_rows("T", 100, 101)                          # today (Thu 10-08)
            + trade_rows("D3", 100, 102, day="2026-10-05")     # 3 days ago
            + trade_rows("D20", 100, 103, day="2026-09-18")    # 20 days ago
            + trade_rows("D90", 100, 104, day="2026-07-10")    # 90 days ago
        )
        return env

    @pytest.mark.parametrize("period, symbols, start", [
        ("today", {"T"}, "2026-10-08"),
        ("7d", {"T", "D3"}, "2026-10-02"),
        ("30d", {"T", "D3", "D20"}, "2026-09-09"),
        ("all", {"T", "D3", "D20", "D90"}, None),
    ])
    def test_every_section_is_limited_to_the_period(self, spread, period, symbols, start):
        d = spread.data(period=period)
        assert d.period == period
        assert {t.symbol for t in d.recent_trades} == symbols
        assert len(d.equity_curve) == len(symbols)
        assert sum(b.count for b in d.r_histogram) == len(symbols)
        assert d.summary.total_trades == len(symbols) and d.summary.from_date == start

    def test_unknown_period_is_rejected(self, env):
        from trading_bot.api.service import InvalidPeriod
        with pytest.raises(InvalidPeriod):
            env.data(period="year")

    def test_equity_curve_starts_from_zero_within_the_period(self, spread):
        assert [p.cumulative_pnl_usd for p in spread.data(period="today").equity_curve] == [10.0]


class TestPositionContext:
    def test_distances_target_and_holding_time(self, tmp_path):
        env = Env(tmp_path, prices={"NVDA": 103.0})
        env.positions.save([position()])  # entry 100, stop 98, R 2, opened 10:00 ET, now 17:00 ET
        (p,) = env.data().open_positions
        assert p.opened_at == "2026-10-08T14:00:00+00:00"
        assert p.hold_minutes == pytest.approx(420.0)
        assert p.target_price == pytest.approx(102.0)            # entry + 1R
        assert p.stop_distance_pct == pytest.approx(4.85, abs=0.01)   # (103-98)/103
        assert p.target_distance_pct == pytest.approx(-0.97, abs=0.01)  # already past +1R

    def test_without_a_price_the_distances_are_empty(self, tmp_path):
        env = Env(tmp_path)
        env.positions.save([position()])
        (p,) = env.data().open_positions
        assert p.stop_distance_pct is None and p.target_distance_pct is None
        assert p.target_price == pytest.approx(102.0)

    def test_an_unparseable_entry_time_leaves_holding_time_empty(self, tmp_path):
        env = Env(tmp_path)
        env.positions.save([position(entry_time_iso="garbage")])
        assert env.data().open_positions[0].hold_minutes is None


def cycle_event(name, **fields):
    return {"timestamp": "2026-10-08T12:55:01-04:00", "event": name, **fields}


class TestLastCycle:
    def log(self, env, *extra):
        env.write_log([cycle_event("cycle", status="ok"), *extra])

    def test_counts_entries_skips_and_lists_the_reasons(self, env):
        self.log(env,
                 cycle_event("entry_skipped", symbol="AAA", reasons=["gap too small", "rvol low"]),
                 cycle_event("entered", symbol="BBB", qty=5, entry_price=10, stop=9.5),
                 cycle_event("partial_sold", symbol="CCC", qty=2, price=11))
        c = env.data().cycle
        assert (c.gate, c.entries, c.skipped) == ("ok", 1, 1)
        assert [(s.symbol, s.reasons) for s in c.skips] == [("AAA", ["gap too small", "rvol low"])]
        assert [(a.event, a.symbol) for a in c.actions] == [("entered", "BBB"), ("partial_sold", "CCC")]

    def test_critical_and_failed_events_become_errors(self, env):
        self.log(env, cycle_event("stop_move_failed", symbol="X", error="boom"),
                 cycle_event("unprotected_position", symbol="Y", critical=True))
        assert [e.event for e in env.data().cycle.errors] == ["stop_move_failed", "unprotected_position"]

    def test_skips_are_capped_but_still_counted(self, env):
        self.log(env, *[cycle_event("entry_skipped", symbol=f"S{i}", reasons=["r"]) for i in range(25)])
        c = env.data().cycle
        assert c.skipped == 25 and len(c.skips) == 10

    def test_quiet_cycle_is_reported_with_zero_counts(self, env):
        self.log(env)
        c = env.data().cycle
        assert (c.at, c.entries, c.skipped, c.actions, c.skips, c.errors) == (
            "2026-10-08T12:55:01-04:00", 0, 0, [], [], [])


class TestOpenPositions:
    def test_unrealized_r_and_pnl_use_the_live_price_and_position_risk(self, tmp_path):
        env = Env(tmp_path, prices={"NVDA": 103.0})
        env.positions.save([position("NVDA", qty=9, R=2.0, stop_price=98.0)])
        (p,) = env.data().open_positions
        assert (p.symbol, p.qty, p.entry_price, p.stop_price) == ("NVDA", 9, 100.0, 98.0)
        assert p.current_price == 103.0
        assert p.unrealized_r == pytest.approx(1.5) and p.unrealized_pnl_usd == pytest.approx(27.0)
        assert p.state == STATE_PRE_BREAKEVEN and p.initial_stop == 98.0

    def test_missing_price_leaves_unrealized_values_empty(self, tmp_path):
        env = Env(tmp_path, prices={})
        env.positions.save([position("NVDA")])
        (p,) = env.data().open_positions
        assert p.current_price is None and p.unrealized_r is None and p.unrealized_pnl_usd is None

    def test_losing_position_has_negative_r(self, tmp_path):
        env = Env(tmp_path, prices={"NVDA": 99.0})
        env.positions.save([position("NVDA", R=2.0)])
        assert env.data().open_positions[0].unrealized_r == pytest.approx(-0.5)

    def test_zero_risk_position_does_not_divide_by_zero(self, tmp_path):
        env = Env(tmp_path, prices={"NVDA": 101.0})
        env.positions.save([position("NVDA", R=0.0)])
        assert env.data().open_positions[0].unrealized_r is None

    def test_prices_are_requested_once_for_all_symbols(self, tmp_path):
        env = Env(tmp_path, prices={"A": 1.0, "B": 2.0})
        env.positions.save([position("A"), position("B", state=STATE_BE_PARTIAL, stop_price=100.0)])
        env.data()
        assert env.prices.asked == [["A", "B"]]

    def test_no_positions_means_no_price_lookup(self, env):
        env.data()
        assert env.prices.asked == []

    def test_a_corrupt_positions_file_degrades_to_a_warning(self, env):
        env.positions.path.write_text("{broken", encoding="utf-8")
        d = env.data()
        assert d.open_positions == [] and any("open_positions.json" in w for w in d.warnings)

    def test_a_failing_price_provider_degrades_gracefully(self, tmp_path):
        class Broken:
            def latest(self, symbols):
                raise RuntimeError("yahoo down")

        env = Env(tmp_path)
        env.prices = Broken()
        env.positions.save([position("NVDA")])
        d = env.data()
        assert d.open_positions[0].current_price is None
        assert any("price" in w.lower() for w in d.warnings)


class TestGate:
    @pytest.mark.parametrize("gate", ["weekend", "too_early", "closed", "manage_only", "force_close", "ok"])
    def test_status_carries_the_market_state_from_the_clock(self, env, gate):
        assert env.data(gate=lambda now: gate).status.gate == gate

    def test_the_gate_is_asked_with_the_current_time(self, env):
        seen = []
        env.data(gate=lambda now: seen.append(now) or "ok")
        assert seen == [NOW]


class TestStatus:
    def heartbeat(self, minutes_ago, **extra):
        return {"timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(), "event": "cycle",
                "status": "ok", **extra}

    def test_recent_heartbeat_is_active(self, env):
        env.write_log([self.heartbeat(3)])
        s = env.data().status
        assert s.bot_status == "ACTIVE" and s.last_event == "cycle"
        assert s.last_cycle_at == (NOW - timedelta(minutes=3)).isoformat()
        assert "3 min ago" in s.message

    def test_stale_heartbeat_is_idle(self, env):
        env.write_log([self.heartbeat(45)])
        s = env.data().status
        assert s.bot_status == "IDLE" and "45 min ago" in s.message

    def test_boundary_is_ten_minutes(self, env):
        env.write_log([self.heartbeat(10)])
        assert env.data().status.bot_status == "ACTIVE"
        env.write_log([self.heartbeat(11)])
        assert env.data().status.bot_status == "IDLE"

    def test_last_event_name_is_reported_alongside(self, env):
        env.write_log([self.heartbeat(2),
                       {"timestamp": (NOW - timedelta(minutes=1)).isoformat(), "event": "entered",
                        "symbol": "NVDA", "stop": 97.0}])
        assert env.data().status.last_event == "entered"

    def test_log_without_a_heartbeat_has_no_last_cycle(self, env):
        env.write_log([{"timestamp": NOW.isoformat(), "event": "max_trades_reached"}])
        s = env.data().status
        assert s.bot_status == "NO_DATA" and s.last_cycle_at is None
        assert s.last_event == "max_trades_reached"


class TestPaperProgress:
    """How far the paper run is toward the recommended two weeks."""

    def test_no_trades_yet_means_day_zero(self, env):
        p = env.data().paper
        assert (p.paper_mode, p.first_trade_date, p.days_traded) == (True, None, 0)
        assert (p.target_days, p.days_remaining, p.reached) == (14, 14, False)

    def test_counts_calendar_days_from_the_first_trade_inclusive(self, env):
        env.write_trades(trade_rows("NVDA", 100, 101, day="2026-10-03"))
        p = env.data().paper
        assert p.first_trade_date == "2026-10-03" and p.days_traded == 6  # Oct 3..8
        assert p.days_remaining == 8 and not p.reached

    def test_an_open_buy_with_no_sell_still_starts_the_clock(self, env):
        env.write_trades(trade_rows("NVDA", 100, 101, day="2026-10-08")[:1])
        assert env.data().paper.days_traded == 1

    def test_reaches_the_target_after_fourteen_days(self, env):
        env.write_trades(trade_rows("NVDA", 100, 101, day="2026-09-25"))  # Sep 25..Oct 8 = 14
        p = env.data().paper
        assert p.days_traded == 14 and p.reached and p.days_remaining == 0

    def test_more_than_fourteen_days_stays_reached(self, env):
        env.write_trades(trade_rows("NVDA", 100, 101, day="2026-08-01"))
        p = env.data().paper
        assert p.reached and p.days_remaining == 0 and p.days_traded > 14

    def test_it_covers_all_history_whatever_period_is_shown(self, env):
        env.write_trades(trade_rows("NVDA", 100, 101, day="2026-10-03"))
        assert env.data("today").paper == env.data("all").paper

    def test_live_mode_is_passed_through(self, env):
        assert env.data(paper_mode=False).paper.paper_mode is False

    def test_rows_with_a_garbled_timestamp_are_ignored(self, env):
        rows = trade_rows("NVDA", 100, 101, day="2026-10-06")
        rows[0]["timestamp_iso"] = "not-a-date"
        env.write_trades(rows)
        assert env.data().paper.first_trade_date == "2026-10-06"
