from datetime import datetime

import pytest

from trading_bot.cycle import cli
from trading_bot.settings import SafetyError
from trading_bot.timeutil import ET


class TestConnectWithRetry:
    def test_returns_on_first_success_without_sleeping(self):
        sleeps = []
        assert cli.connect_with_retry(lambda a: ("conn", a), 7, sleep=sleeps.append) == ("conn", 7)
        assert sleeps == []

    def test_retries_once_after_five_seconds(self):
        attempts, sleeps = [], []

        def flaky():
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionRefusedError("TWS down")
            return "connected"

        assert cli.connect_with_retry(flaky, sleep=sleeps.append) == "connected"
        assert sleeps == [5] and len(attempts) == 2

    def test_second_failure_propagates(self):
        def down():
            raise ConnectionRefusedError("TWS down")

        with pytest.raises(ConnectionRefusedError):
            cli.connect_with_retry(down, sleep=lambda s: None)

    def test_a_safety_abort_is_never_retried(self):
        attempts, sleeps = [], []

        def wrong_account():
            attempts.append(1)
            raise SafetyError("ABORT: paper flag but live account")

        with pytest.raises(SafetyError):
            cli.connect_with_retry(wrong_account, sleep=sleeps.append)
        assert len(attempts) == 1 and sleeps == []


def test_log_error_appends_the_traceback(tmp_path):
    path = tmp_path / "logs" / "cycle_errors.log"
    when = datetime(2026, 10, 8, 11, 0, tzinfo=ET)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        cli.log_error(path, when)
    text = path.read_text()
    assert "RuntimeError: boom" in text and when.isoformat() in text


class TestCrashAlert:
    def test_sends_high_priority_alert_with_the_error(self):
        sent = []
        cli.report_crash(RuntimeError("TWS exploded"), send=lambda *a: sent.append(a))
        assert sent == [("Cycle CRASHED", "TWS exploded", "high")]

    def test_message_is_truncated_to_500_characters(self):
        sent = []
        cli.report_crash(RuntimeError("x" * 900), send=lambda *a: sent.append(a))
        assert len(sent[0][1]) == 500

    def test_a_failing_notifier_never_raises(self):
        def broken(*args):
            raise RuntimeError("telegram is down")

        cli.report_crash(RuntimeError("boom"), send=broken)


@pytest.mark.parametrize("day, hour, expected", [(10, 12, "weekend"), (8, 9, "too_early"), (8, 17, "closed")])
def test_inactive_hours_exit_0_without_touching_the_broker(monkeypatch, capsys, day, hour, expected):
    monkeypatch.setattr(cli, "now_et", lambda: datetime(2026, 10, day, hour, 0, tzinfo=ET))
    monkeypatch.setattr(cli, "_run_active", lambda rules: pytest.fail("must not run"))
    assert cli.main() == 0
    assert expected in capsys.readouterr().out
