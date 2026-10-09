import pytest
import requests

from trading_bot.notify import notify

TOKEN = "123456:SECRET-token_value"
CHAT = "424242"
TELEGRAM = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}
NTFY = {"NOTIFY_URL": "https://ntfy.example/topic"}


class Response:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} error")


class PostSpy:
    def __init__(self, status=200, error=None, fail_urls=()):
        self.calls, self.status, self.error, self.fail_urls = [], status, error, fail_urls

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error and any(f in url for f in self.fail_urls or [""]):
            raise self.error
        return Response(self.status)


@pytest.fixture
def log(tmp_path):
    return tmp_path / "logs" / "notify_errors.log"


def send(env, post, log, title="Test", body="Hello", priority="default"):
    return notify(title, body, priority, env=env, post=post, error_log=log)


class TestTelegram:
    def test_posts_markdown_message_with_five_second_timeout(self, log):
        post = PostSpy()
        send(TELEGRAM, post, log)
        ((url, kwargs),) = post.calls
        assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        assert kwargs["json"] == {"chat_id": CHAT, "text": "*Test*\nHello", "parse_mode": "Markdown"}
        assert kwargs["timeout"] == 5

    @pytest.mark.parametrize("env", [
        {"TELEGRAM_BOT_TOKEN": TOKEN},
        {"TELEGRAM_CHAT_ID": CHAT},
        {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": CHAT},
        {},
    ])
    def test_needs_both_token_and_chat_id(self, env, log):
        post = PostSpy()
        send(env, post, log)
        assert post.calls == []

    def test_markdown_special_characters_are_escaped(self, log):
        post = PostSpy()
        send(TELEGRAM, post, log, title="BE_NVDA *x*", body="post_breakeven `y` [z]")
        text = post.calls[0][1]["json"]["text"]
        assert text == "*BE\\_NVDA \\*x\\**\npost\\_breakeven \\`y\\` \\[z]"

    def test_token_is_never_sent_in_the_message_text(self, log):
        post = PostSpy()
        send(TELEGRAM, post, log, body=f"oops {TOKEN}")
        assert TOKEN not in post.calls[0][1]["json"]["text"]


class TestNtfy:
    def test_posts_body_with_title_and_priority_headers(self, log):
        post = PostSpy()
        send(NTFY, post, log, title="STOP NVDA", body="exit $97.50", priority="high")
        ((url, kwargs),) = post.calls
        assert url == "https://ntfy.example/topic"
        assert kwargs["data"] == b"exit $97.50"
        assert kwargs["headers"] == {"Title": "STOP NVDA", "Priority": "high"}
        assert kwargs["timeout"] == 5

    def test_default_priority(self, log):
        post = PostSpy()
        send(NTFY, post, log)
        assert post.calls[0][1]["headers"]["Priority"] == "default"


class TestChannels:
    def test_nothing_configured_sends_nothing(self, log):
        post = PostSpy()
        send({}, post, log)
        assert post.calls == [] and not log.exists()

    def test_both_channels_are_used_when_both_configured(self, log):
        post = PostSpy()
        send({**TELEGRAM, **NTFY}, post, log)
        assert len(post.calls) == 2

    def test_one_failing_channel_does_not_block_the_other(self, log):
        post = PostSpy(error=ConnectionError("down"), fail_urls=("telegram",))
        send({**TELEGRAM, **NTFY}, post, log)
        assert any("ntfy" in url for url, _ in post.calls)


class TestNeverRaises:
    @pytest.mark.parametrize("env", [TELEGRAM, NTFY, {**TELEGRAM, **NTFY}])
    def test_network_errors_are_swallowed_and_logged(self, env, log):
        post = PostSpy(error=requests.ConnectionError("no route"))
        send(env, post, log)  # must not raise
        assert "ConnectionError" in log.read_text()

    def test_http_error_status_is_logged(self, log):
        send(TELEGRAM, PostSpy(status=400), log)
        assert "400" in log.read_text()

    def test_token_is_scrubbed_from_logged_errors(self, log):
        # requests puts the full URL, token included, into its exception text
        error = requests.ConnectionError(f"HTTPSConnectionPool: /bot{TOKEN}/sendMessage failed")
        send(TELEGRAM, PostSpy(error=error), log)
        text = log.read_text()
        assert TOKEN not in text and "***" in text

    def test_log_lines_carry_a_timestamp_and_channel(self, log):
        send(TELEGRAM, PostSpy(error=RuntimeError("x")), log)
        line = log.read_text().splitlines()[0]
        assert "telegram" in line and line[:4].isdigit()

    def test_unwritable_log_does_not_raise(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("not a directory")
        send(TELEGRAM, PostSpy(error=RuntimeError("x")), blocker / "notify_errors.log")

    def test_default_call_with_no_environment_is_a_silent_noop(self):
        notify("Test", "Hello")  # conftest clears the env and blocks real POSTs
