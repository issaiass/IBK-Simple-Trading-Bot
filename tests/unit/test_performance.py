import csv
import json
from datetime import date, datetime

import pytest

from trading_bot.reporting.performance import (
    format_notification,
    pair_trades,
    read_trades,
    run,
    summarize,
    summarize_range,
)
from trading_bot.timeutil import ET
from trading_bot.trades_log import HEADER

TODAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 17, 0, tzinfo=ET)


def row(symbol, side, size, price, ts, status="Filled", order_id=1):
    return {"timestamp_iso": ts, "symbol": symbol, "side": side, "size": str(size),
            "fill_price": str(price), "order_id": str(order_id), "status": status}


def at(hhmm, day="2026-10-08"):
    """UTC timestamp string. 14:00Z is 10:00 ET."""
    return f"{day}T{hhmm}:00+00:00"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def roundtrip(symbol, buy, sell, qty=10, open_="14:00", close="15:00"):
    return [row(symbol, "BUY", qty, buy, at(open_)), row(symbol, "SELL", qty, sell, at(close))]


class TestPairing:
    def test_simple_round_trip(self):
        (t,) = pair_trades(roundtrip("NVDA", 100.0, 102.0))[0]
        assert t.symbol == "NVDA" and t.qty == 10
        assert (t.entry_price, t.exit_price) == (100.0, 102.0)
        assert t.pnl_usd == pytest.approx(20.0)
        assert t.pnl_pct == pytest.approx(2.0)
        assert t.hold_minutes == 60

    def test_partial_exits_form_one_trade(self):
        rows = [row("NVDA", "BUY", 9, 100.0, at("14:00")),
                row("NVDA", "SELL", 3, 105.0, at("14:30")),
                row("NVDA", "SELL", 6, 103.0, at("15:30"))]
        (t,) = pair_trades(rows)[0]
        assert t.qty == 9 and t.pnl_usd == pytest.approx(15 + 18)
        assert t.exit_price == pytest.approx((3 * 105 + 6 * 103) / 9)
        assert t.hold_minutes == 90  # entry to the final exit

    def test_fifo_across_two_buys(self):
        rows = [row("X", "BUY", 5, 100.0, at("14:00")),
                row("X", "BUY", 5, 110.0, at("14:10")),
                row("X", "SELL", 7, 120.0, at("15:00")),
                row("X", "SELL", 3, 120.0, at("15:10"))]
        first, second = pair_trades(rows)[0]
        assert first.pnl_usd == pytest.approx(5 * 20) and first.closed.strftime("%H:%M") == "11:00"
        assert second.pnl_usd == pytest.approx(5 * 10) and second.closed.strftime("%H:%M") == "11:10"

    def test_symbols_are_paired_independently(self):
        rows = roundtrip("A", 10, 11) + roundtrip("B", 20, 19)
        trades = {t.symbol: t.pnl_usd for t in pair_trades(rows)[0]}
        assert trades == {"A": pytest.approx(10.0), "B": pytest.approx(-10.0)}

    def test_open_and_partially_closed_entries_are_not_closed_trades(self):
        rows = [row("OPEN", "BUY", 10, 50.0, at("14:00")),
                row("HALF", "BUY", 10, 50.0, at("14:00")),
                row("HALF", "SELL", 4, 55.0, at("15:00"))]
        assert pair_trades(rows)[0] == []

    def test_rows_without_a_fill_price_are_ignored(self):
        rows = [row("PM", "BUY", 12, 0, at("14:00"), status="Submitted")] + roundtrip("PM", 200, 201, qty=12)
        trades, info = pair_trades(rows)
        assert len(trades) == 1 and info["ignored_rows"] == 1

    def test_sell_without_a_matching_buy_is_reported_not_paired(self):
        trades, info = pair_trades([row("ZZZ", "SELL", 5, 10.0, at("15:00"))])
        assert trades == [] and info["unmatched_sell_qty"] == 5

    def test_input_order_does_not_matter(self):
        rows = roundtrip("NVDA", 100.0, 102.0)[::-1]
        assert len(pair_trades(rows)[0]) == 1


class TestStopPriceColumn:
    def test_stop_price_on_the_buy_row_is_carried_to_the_closed_trade(self):
        rows = [{**row("NVDA", "BUY", 10, 100.0, at("14:00")), "stop_price": "97.5"},
                row("NVDA", "SELL", 10, 102.0, at("15:00"))]
        (t,) = pair_trades(rows)[0]
        assert t.stop_price == 97.5

    @pytest.mark.parametrize("value", ["", "0", "abc", None])
    def test_missing_or_unusable_stop_price_is_none(self, value):
        rows = [{**row("NVDA", "BUY", 10, 100.0, at("14:00")), "stop_price": value},
                row("NVDA", "SELL", 10, 102.0, at("15:00"))]
        (t,) = pair_trades(rows)[0]
        assert t.stop_price is None

    def test_trades_without_the_column_still_pair(self):
        (t,) = pair_trades(roundtrip("NVDA", 100.0, 102.0))[0]
        assert t.stop_price is None


class TestSummary:
    def trades(self, rows):
        return pair_trades(rows)[0]

    def test_aggregates(self):
        rows = (roundtrip("W1", 100, 110) + roundtrip("W2", 100, 104)   # +100, +40
                + roundtrip("L1", 100, 95))                              # -50
        s = summarize(self.trades(rows), TODAY)
        assert (s["total_trades"], s["wins"], s["losses"]) == (3, 2, 1)
        assert s["win_rate_pct"] == pytest.approx(66.7, abs=0.05)
        assert s["gross_pnl_usd"] == pytest.approx(90.0)
        assert s["largest_winner"] == {"symbol": "W1", "pnl_usd": 100.0}
        assert s["largest_loser"] == {"symbol": "L1", "pnl_usd": -50.0}
        assert s["avg_winner"] == pytest.approx(70.0) and s["avg_loser"] == pytest.approx(-50.0)
        assert s["profit_factor"] == pytest.approx(2.8)

    def test_no_losses_gives_infinite_profit_factor(self):
        s = summarize(self.trades(roundtrip("W", 100, 110)), TODAY)
        assert s["profit_factor"] == "inf" and s["largest_loser"] is None and s["avg_loser"] is None

    def test_zero_trades(self):
        s = summarize([], TODAY)
        assert s["total_trades"] == 0 and s["profit_factor"] == "n/a"
        assert s["win_rate_pct"] == 0.0 and s["gross_pnl_usd"] == 0.0
        assert s["largest_winner"] is None

    def test_breakeven_trade_is_neither_win_nor_loss(self):
        s = summarize(self.trades(roundtrip("E", 100, 100)), TODAY)
        assert (s["total_trades"], s["wins"], s["losses"], s["breakeven"]) == (1, 0, 0, 1)

    def test_only_trades_closed_today_in_eastern_time_count(self):
        rows = (roundtrip("TODAY", 100, 101)
                + [row("YDAY", "BUY", 10, 100, at("14:00", "2026-10-07")),
                   row("YDAY", "SELL", 10, 101, at("15:00", "2026-10-07"))]
                # bought yesterday, sold today: counts today
                + [row("CARRY", "BUY", 10, 100, at("19:00", "2026-10-07")),
                   row("CARRY", "SELL", 10, 103, at("14:30"))]
                # 02:00Z on Oct 9 is 22:00 ET on Oct 8: still today
                + [row("LATE", "BUY", 10, 100, at("23:00", "2026-10-08")),
                   row("LATE", "SELL", 10, 102, at("02:00", "2026-10-09"))])
        s = summarize(self.trades(rows), TODAY)
        assert sorted(t["symbol"] for t in s["trades"]) == ["CARRY", "LATE", "TODAY"]

    def test_trade_details_are_included(self):
        s = summarize(self.trades(roundtrip("NVDA", 100, 102)), TODAY)
        (t,) = s["trades"]
        assert t == {"symbol": "NVDA", "qty": 10, "entry_price": 100.0, "exit_price": 102.0,
                     "pnl_usd": 20.0, "pnl_pct": 2.0, "hold_minutes": 60}


class TestNotificationText:
    def build(self, rows):
        return format_notification(summarize(pair_trades(rows)[0], TODAY))

    def test_title_has_the_date(self):
        assert self.build([])[0] == "Daily Summary 2026-10-08"

    def test_zero_trades_message(self):
        assert self.build([])[1] == "No closed trades today."

    def test_body_format(self):
        rows = roundtrip("W1", 100, 110) + roundtrip("W2", 100, 104) + roundtrip("L1", 100, 95)
        assert self.build(rows)[1] == (
            "Trades: 3 (2W / 1L, 66.7%)\nP&L: $+90.00\nBest: W1 $+100.00\nWorst: L1 $-50.00\nPF: 2.80"
        )

    def test_infinite_profit_factor_is_shown_as_inf(self):
        assert self.build(roundtrip("W", 100, 110))[1].endswith("PF: inf")


class TestReadTrades:
    def test_missing_file_is_zero_trades_and_is_not_created(self, tmp_path):
        path = tmp_path / "trades.csv"
        assert read_trades(path) == [] and not path.exists()

    def test_reads_rows(self, tmp_path):
        path = tmp_path / "trades.csv"
        write_csv(path, roundtrip("NVDA", 100, 102))
        assert [r["side"] for r in read_trades(path)] == ["BUY", "SELL"]


class TestRun:
    def run_it(self, tmp_path, rows=None, send=True):
        path = tmp_path / "trades.csv"
        if rows is not None:
            write_csv(path, rows)
        out, sent = [], []
        code = run(path, NOW, notify=lambda t, b, p="default": sent.append((t, b, p)),
                   out=out.append, send=send)
        return code, json.loads(out[0]), sent, path

    def test_prints_json_and_sends_the_daily_summary(self, tmp_path):
        code, summary, sent, _ = self.run_it(tmp_path, roundtrip("NVDA", 100, 102))
        assert code == 0 and summary["total_trades"] == 1
        assert sent == [("Daily Summary 2026-10-08",
                         "Trades: 1 (1W / 0L, 100.0%)\nP&L: $+20.00\nBest: NVDA $+20.00\n"
                         "Worst: NVDA $+20.00\nPF: inf", "default")]

    def test_missing_trades_file_reports_no_closed_trades(self, tmp_path):
        code, summary, sent, path = self.run_it(tmp_path)
        assert code == 0 and summary["total_trades"] == 0
        assert sent[0][1] == "No closed trades today." and not path.exists()

    def test_never_modifies_trades_csv(self, tmp_path):
        path = tmp_path / "trades.csv"
        write_csv(path, roundtrip("NVDA", 100, 102))
        before = path.read_bytes()
        self.run_it(tmp_path, rows=None)
        assert path.read_bytes() == before

    def test_no_notify_flag_skips_the_message(self, tmp_path):
        _, _, sent, _ = self.run_it(tmp_path, roundtrip("NVDA", 100, 102), send=False)
        assert sent == []

    def test_a_failing_notifier_does_not_fail_the_run(self, tmp_path):
        path = tmp_path / "trades.csv"
        write_csv(path, roundtrip("NVDA", 100, 102))

        def broken(*a):
            raise RuntimeError("telegram is down")

        assert run(path, NOW, notify=broken, out=lambda m: None) == 0


class TestSummarizeRange:
    def trades(self):
        rows = (roundtrip("TODAY", 100, 102)
                + [row("D5", "BUY", 10, 100, at("14:00", "2026-10-03")), row("D5", "SELL", 10, 95, at("15:00", "2026-10-03"))]
                + [row("OLD", "BUY", 10, 100, at("14:00", "2026-08-01")), row("OLD", "SELL", 10, 110, at("15:00", "2026-08-01"))])
        return pair_trades(rows)[0]

    def test_a_start_date_includes_that_whole_day_and_everything_after(self):
        s = summarize_range(self.trades(), date(2026, 10, 2), TODAY)
        assert s["total_trades"] == 2 and s["gross_pnl_usd"] == pytest.approx(-30.0)
        assert (s["from_date"], s["to_date"]) == ("2026-10-02", "2026-10-08")

    def test_no_start_date_means_all_time(self):
        s = summarize_range(self.trades(), None, TODAY)
        assert s["total_trades"] == 3 and s["from_date"] is None

    def test_trades_after_the_end_date_are_excluded(self):
        assert summarize_range(self.trades(), None, date(2026, 10, 5))["total_trades"] == 2

    def test_a_single_day_matches_summarize(self):
        one = summarize(self.trades(), TODAY)
        rng = summarize_range(self.trades(), TODAY, TODAY)
        for key in ("total_trades", "wins", "losses", "gross_pnl_usd", "profit_factor", "win_rate_pct"):
            assert rng[key] == one[key]
