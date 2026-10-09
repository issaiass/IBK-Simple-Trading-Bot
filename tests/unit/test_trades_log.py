from datetime import date, datetime, timezone

import pytest

from trading_bot.timeutil import ET
from trading_bot.trades_log import HEADER, TradeLog, TradeLogLocked

TODAY = date(2026, 10, 8)


def row(side="BUY", ts="2026-10-08T15:00:00+00:00", status="Filled"):
    return {
        "timestamp_iso": ts, "symbol": "NVDA", "side": side, "size": 5,
        "fill_price": 100.0, "order_id": 1, "status": status,
    }


@pytest.fixture
def log(tmp_path):
    return TradeLog(tmp_path / "trades.csv")


def test_header_created_when_missing(log):
    log.ensure_header()
    assert log.path.read_text().splitlines() == [",".join(HEADER)]


def test_existing_file_is_not_overwritten(log):
    log.append(row())
    log.ensure_header()
    assert len(log.path.read_text().splitlines()) == 2


def test_append_and_last_row(log):
    log.append(row(status="Submitted"))
    log.append(row(status="Filled"))
    assert log.last_row()["status"] == "Filled"


def test_last_row_empty_log_is_none(log):
    log.ensure_header()
    assert log.last_row() is None


def test_counts_only_todays_buys(log):
    log.append(row("BUY"))
    log.append(row("BUY"))
    log.append(row("SELL"))
    log.append(row("BUY", ts="2026-10-07T15:00:00+00:00"))
    assert log.count_buys_on(TODAY) == 2


def test_count_uses_eastern_date_not_utc(log):
    # 02:00 UTC on Oct 9 is 22:00 ET on Oct 8
    log.append(row("BUY", ts="2026-10-09T02:00:00+00:00"))
    assert log.count_buys_on(TODAY) == 1
    assert log.count_buys_on(date(2026, 10, 9)) == 0


def test_count_on_missing_file_creates_header_and_returns_zero(log):
    assert log.count_buys_on(TODAY) == 0
    assert log.path.exists()


def test_locked_file_retries_once_then_succeeds(log, monkeypatch):
    calls = {"n": 0}
    real = log._write_row

    def flaky(r):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("locked")
        real(r)

    sleeps = []
    monkeypatch.setattr(log, "_write_row", flaky)
    log._sleep = sleeps.append
    log.append(row())
    assert calls["n"] == 2 and sleeps == [1]


def test_locked_file_gives_up_after_one_retry(log, monkeypatch):
    def always_locked(r):
        raise PermissionError("locked")

    monkeypatch.setattr(log, "_write_row", always_locked)
    log._sleep = lambda s: None
    with pytest.raises(TradeLogLocked):
        log.append(row())


def test_utc_timestamp_helper_is_timezone_aware():
    assert datetime.now(timezone.utc).astimezone(ET).tzinfo is not None
