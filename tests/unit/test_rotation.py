import csv
import os
from datetime import date, datetime, timedelta

import pytest

from trading_bot.maintenance import rotation
from trading_bot.maintenance.rotation import format_report, rotate
from trading_bot.timeutil import ET
from trading_bot.trades_log import HEADER

NOW = datetime(2026, 10, 8, 13, 0, tzinfo=ET)
TODAY = NOW.date()


def touch(path, text="x", day=TODAY, hour=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = datetime(day.year, day.month, day.day, hour, 0, tzinfo=ET).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def trade_row(ts_day, symbol="NVDA", side="BUY"):
    return {"timestamp_iso": f"{ts_day.isoformat()}T15:00:00+00:00", "symbol": symbol,
            "side": side, "size": "10", "fill_price": "100", "order_id": "1", "status": "Filled"}


def write_trades(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def env(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    return {"logs_dir": logs, "trades_path": tmp_path / "trades.csv",
            "safety_log_path": tmp_path / "safety-check-log.json", "now": NOW}


def go(env, **kw):
    return rotate(**env, **kw)


class TestLogFiles:
    def test_old_logs_move_to_a_dated_archive_folder(self, env):
        yesterday = TODAY - timedelta(days=1)
        old_log = touch(env["logs_dir"] / "cycle_errors.log", day=yesterday)
        old_jsonl = touch(env["logs_dir"] / "safety_log.jsonl", day=date(2026, 9, 1))
        report = go(env)
        archive = env["logs_dir"] / "archive"
        assert (archive / "2026-10-07" / "cycle_errors.log").read_text() == "x"
        assert (archive / "2026-09-01" / "safety_log.jsonl").exists()
        assert not old_log.exists() and not old_jsonl.exists()
        assert len(report.moved) == 2

    def test_todays_logs_stay_in_place(self, env):
        today_log = touch(env["logs_dir"] / "notify_errors.log", day=TODAY)
        assert go(env).moved == [] and today_log.exists()

    def test_other_file_types_and_folders_are_left_alone(self, env):
        yesterday = TODAY - timedelta(days=1)
        keep = touch(env["logs_dir"] / "notes.txt", day=yesterday)
        sub = touch(env["logs_dir"] / "cycle-test-runs" / "old.log", day=yesterday)
        go(env)
        assert keep.exists() and sub.exists()

    def test_never_overwrites_an_existing_archive_file(self, env):
        yesterday = TODAY - timedelta(days=1)
        archived = touch(env["logs_dir"] / "archive" / "2026-10-07" / "cycle_errors.log", "first", yesterday)
        touch(env["logs_dir"] / "cycle_errors.log", "second", yesterday)
        go(env)
        assert archived.read_text() == "first"
        contents = sorted(p.read_text() for p in archived.parent.iterdir())
        assert contents == ["first", "second"]

    def test_a_locked_file_is_skipped_without_raising(self, env, monkeypatch):
        yesterday = TODAY - timedelta(days=1)
        locked = touch(env["logs_dir"] / "locked.log", day=yesterday)
        other = touch(env["logs_dir"] / "free.log", day=yesterday)
        real = os.replace

        def replace(src, dst):
            if str(src).endswith("locked.log"):
                raise PermissionError("in use by another process")
            return real(src, dst)

        monkeypatch.setattr(rotation.os, "replace", replace)
        report = go(env)
        assert locked.exists() and not other.exists()
        assert [p.name for p, _ in report.skipped] == ["locked.log"]

    def test_missing_logs_directory_is_fine(self, env):
        env["logs_dir"].rmdir()
        assert go(env).moved == []


class TestTradesCsv:
    def test_rows_older_than_90_days_are_archived(self, env):
        old, boundary, recent = (TODAY - timedelta(days=d) for d in (91, 90, 5))
        write_trades(env["trades_path"], [trade_row(old, "OLD"), trade_row(boundary, "EDGE"),
                                          trade_row(recent, "NEW")])
        report = go(env)
        assert [r["symbol"] for r in read_rows(env["trades_path"])] == ["EDGE", "NEW"]
        archive = env["logs_dir"] / "archive" / "trades_20261008.csv"
        assert [r["symbol"] for r in read_rows(archive)] == ["OLD"]
        assert archive in report.moved

    def test_archive_keeps_the_csv_header(self, env):
        write_trades(env["trades_path"], [trade_row(TODAY - timedelta(days=200))])
        go(env)
        header = (env["logs_dir"] / "archive" / "trades_20261008.csv").read_text().splitlines()[0]
        assert header == ",".join(HEADER)

    def test_same_day_rerun_appends_instead_of_overwriting(self, env):
        archive = env["logs_dir"] / "archive" / "trades_20261008.csv"
        write_trades(env["trades_path"], [trade_row(TODAY - timedelta(days=200), "A")])
        go(env)
        write_trades(env["trades_path"], [trade_row(TODAY - timedelta(days=150), "B")])
        go(env)
        assert [r["symbol"] for r in read_rows(archive)] == ["A", "B"]

    def test_nothing_old_leaves_the_file_untouched(self, env):
        write_trades(env["trades_path"], [trade_row(TODAY - timedelta(days=3))])
        before = env["trades_path"].read_bytes()
        report = go(env)
        assert env["trades_path"].read_bytes() == before and report.moved == []
        assert not (env["logs_dir"] / "archive").exists()

    def test_missing_trades_file_is_fine(self, env):
        assert go(env).moved == [] and not env["trades_path"].exists()

    def test_unparseable_timestamps_are_kept_not_lost(self, env):
        bad = {**trade_row(TODAY), "timestamp_iso": "garbage"}
        write_trades(env["trades_path"], [bad, trade_row(TODAY - timedelta(days=200))])
        go(env)
        assert [r["timestamp_iso"] for r in read_rows(env["trades_path"])] == ["garbage"]

    def test_a_locked_trades_file_is_skipped_and_nothing_is_lost(self, env, monkeypatch):
        write_trades(env["trades_path"], [trade_row(TODAY - timedelta(days=200), "OLD")])
        before = env["trades_path"].read_bytes()
        real = os.replace

        def replace(src, dst):
            if str(dst).endswith("trades.csv"):
                raise PermissionError("locked")
            return real(src, dst)

        monkeypatch.setattr(rotation.os, "replace", replace)
        report = go(env)
        assert env["trades_path"].read_bytes() == before
        assert [p.name for p, _ in report.skipped] == ["trades.csv"]
        # the archive was rolled back, so a retry can't duplicate rows
        assert not (env["logs_dir"] / "archive" / "trades_20261008.csv").exists()
        assert not env["trades_path"].with_suffix(".csv.tmp").exists()


class TestSafetyLog:
    def test_oversized_log_is_archived_with_a_date_prefix(self, env):
        env["safety_log_path"].write_text("x" * 100, encoding="utf-8")
        report = go(env, max_bytes=50)
        archived = env["logs_dir"] / "archive" / "2026-10-08_safety-check-log.json"
        assert archived.read_text() == "x" * 100
        assert not env["safety_log_path"].exists()  # fresh start: the logger recreates it
        assert archived in report.moved

    def test_small_log_is_left_alone(self, env):
        env["safety_log_path"].write_text("x" * 10, encoding="utf-8")
        assert go(env, max_bytes=50).moved == [] and env["safety_log_path"].exists()

    def test_default_threshold_is_5_mb(self):
        assert rotation.SAFETY_LOG_MAX_BYTES == 5 * 1024 * 1024

    def test_repeat_archive_same_day_does_not_overwrite(self, env):
        for text in ("a" * 100, "b" * 100):
            env["safety_log_path"].write_text(text, encoding="utf-8")
            go(env, max_bytes=50)
        archived = sorted((env["logs_dir"] / "archive").iterdir())
        assert sorted(p.read_text()[0] for p in archived) == ["a", "b"]


class TestReport:
    def test_message(self):
        report = rotation.RotationReport(moved=[1, 2, 3], skipped=[])
        assert format_report(report) == "Rotated 3 files to logs/archive/"

    def test_nothing_to_do(self, env):
        assert format_report(go(env)) == "Rotated 0 files to logs/archive/"


def test_main_exits_zero_when_there_is_nothing_to_do(env, monkeypatch, capsys):
    monkeypatch.setattr(rotation, "LOG_DIR", env["logs_dir"])
    monkeypatch.setattr(rotation, "TRADES_CSV", env["trades_path"])
    monkeypatch.setattr(rotation, "DECISION_LOG_PATH", env["safety_log_path"])
    assert rotation.main() == 0
    assert "Rotated 0 files to logs/archive/" in capsys.readouterr().out
