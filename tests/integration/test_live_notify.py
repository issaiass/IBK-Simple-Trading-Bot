"""Live: really sends Telegram messages using the credentials in .env.

Run: uv run pytest -m live_notify tests/integration/test_live_notify.py
notify() swallows errors by design, so success is judged by logs/notify_errors.log
not growing (HTTP 400s from bad Markdown would be logged there).
"""
import pytest

from trading_bot.notify import ERROR_LOG, notify

pytestmark = [pytest.mark.live, pytest.mark.live_notify]


def log_size() -> int:
    return ERROR_LOG.stat().st_size if ERROR_LOG.exists() else 0


@pytest.mark.parametrize("title, body, priority", [
    ("Test", "Hello from IBKR bot", "default"),
    ("TRAIL TEST", "stop $100.00 -> $104.99 (post_breakeven_no_partial)", "default"),
    ("STOP TEST", "exit $97.50, P&L $-22.50 [paper] `test`", "high"),
])
def test_message_is_delivered_without_errors(title, body, priority):
    before = log_size()
    notify(title, body, priority)
    assert log_size() == before, ERROR_LOG.read_text() if ERROR_LOG.exists() else ""
