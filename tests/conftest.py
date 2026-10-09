"""Test-wide safety net: no test may ever send a real notification.

notify() loads the real .env (Telegram credentials) when imported, so without this
a unit test that reaches an un-injected notify() would message the user's phone.
"""
import pytest
import requests

NOTIFY_ENV = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NOTIFY_URL")


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch, request):
    if request.node.get_closest_marker("live_notify"):
        return  # the one explicit live Telegram test opts out
    for name in NOTIFY_ENV:
        monkeypatch.delenv(name, raising=False)

    def blocked(*args, **kwargs):
        raise AssertionError(f"unit tests must not make HTTP POSTs: {args[:1]}")

    monkeypatch.setattr(requests, "post", blocked)
