"""Fire-and-forget push notifications: Telegram, with an optional ntfy fallback.

notify() never raises and never prints credentials. Failures go to
logs/notify_errors.log with every secret scrubbed out.
"""
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from trading_bot.config import LOG_DIR, PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

ERROR_LOG = LOG_DIR / "notify_errors.log"
TIMEOUT_SECONDS = 5
MARKDOWN_SPECIALS = "_*`["  # legacy Telegram Markdown; unescaped, these break parsing


def _escape(text: str) -> str:
    for char in MARKDOWN_SPECIALS:
        text = text.replace(char, "\\" + char)
    return text


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def _log_failure(path: Path, channel: str, exc: Exception, secrets: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now(timezone.utc).isoformat()} {channel}: {type(exc).__name__}: {exc}"
        with path.open("a", encoding="utf-8") as f:
            f.write(_scrub(line, secrets) + "\n")
    except Exception:
        pass  # logging must never break the caller either


def notify(
    title: str,
    body: str,
    priority: str = "default",
    *,
    env: Mapping[str, str] | None = None,
    post: Callable | None = None,
    error_log: Path | None = None,
) -> None:
    """Send `title`/`body` to every configured channel. Never raises."""
    try:
        env = os.environ if env is None else env
        post = post or requests.post
        error_log = error_log or ERROR_LOG
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = env.get("TELEGRAM_CHAT_ID", "")
        ntfy_url = env.get("NOTIFY_URL", "")
        secrets = [s for s in (token, ntfy_url) if s]

        if token and chat_id:
            try:
                text = f"*{_escape(_scrub(title, secrets))}*\n{_escape(_scrub(body, secrets))}"
                response = post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=TIMEOUT_SECONDS,
                )
                response.raise_for_status()
            except Exception as exc:
                _log_failure(error_log, "telegram", exc, secrets)

        if ntfy_url:
            try:
                response = post(
                    ntfy_url,
                    data=body.encode("utf-8"),
                    headers={"Title": title, "Priority": priority},
                    timeout=TIMEOUT_SECONDS,
                )
                response.raise_for_status()
            except Exception as exc:
                _log_failure(error_log, "ntfy", exc, secrets)
    except Exception:
        pass


def send_safely(
    send: Callable[[str, str, str], None], title: str, body: str, priority: str = "default"
) -> None:
    """Call any notifier so that its failure can never reach trading logic."""
    try:
        send(title, body, priority)
    except Exception:
        pass
