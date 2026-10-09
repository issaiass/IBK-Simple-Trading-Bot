"""Compare the hardcoded S&P 500 list with Wikipedia's current one (read-only).

    uv run refresh-sp500

Prints the symbols that joined and left, and where to edit them. Exit code: 0 in sync,
1 the lists differ, 2 the page could not be fetched or read. Nothing is written.
"""
import sys
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser

import requests

from trading_bot.sp500_tickers import SP500_TICKERS

SOURCE_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
TABLE_ID = "constituents"
USER_AGENT = "trading-bot-universe-check/0.1 (personal paper-trading project)"
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class UniverseDiff:
    added: list[str]
    removed: list[str]

    def __bool__(self) -> bool:
        return bool(self.added or self.removed)


class _ConstituentsParser(HTMLParser):
    """Collects the text of the first cell of every row in the constituents table."""

    def __init__(self) -> None:
        super().__init__()
        self.symbols: list[str] = []
        self.found = False
        self._in_table = 0
        self._cell = -1  # index of the current cell within the row; -1 outside a row
        self._text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if dict(attrs).get("id") == TABLE_ID:
                self.found, self._in_table = True, 1
            elif self._in_table:
                self._in_table += 1
        elif self._in_table and tag == "tr":
            self._cell = -1
        elif self._in_table and tag in ("td", "th"):
            self._cell += 1
            self._text = ""

    def handle_endtag(self, tag):
        if tag == "table" and self._in_table:
            self._in_table -= 1
        elif self._in_table and tag == "td" and self._cell == 0 and self._text.strip():
            self.symbols.append(self._text.strip())

    def handle_data(self, data):
        if self._in_table and self._cell == 0:
            self._text += data


def parse_constituents(html: str) -> list[str]:
    """Sorted symbols in IBKR format (class shares use a space: BRK.B -> BRK B)."""
    parser = _ConstituentsParser()
    parser.feed(html)
    if not parser.found or not parser.symbols:
        raise ValueError(f"no '{TABLE_ID}' table found in the page")
    return sorted(symbol.replace(".", " ").replace("-", " ") for symbol in parser.symbols)


def diff_universe(current: list[str], latest: list[str]) -> UniverseDiff:
    return UniverseDiff(
        added=sorted(set(latest) - set(current)),
        removed=sorted(set(current) - set(latest)),
    )


def run(
    *,
    current: list[str] = SP500_TICKERS,
    get: Callable = requests.get,
    out: Callable[[str], None] = print,
) -> int:
    try:
        response = get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        latest = parse_constituents(response.text)
    except Exception as exc:
        out(f"Could not read the current S&P 500 list: {exc}")
        return 2

    diff = diff_universe(current, latest)
    if not diff:
        out(f"Up to date: {len(current)} symbols match Wikipedia.")
        return 0
    out(f"{len(diff.added)} joined, {len(diff.removed)} left (Wikipedia has {len(latest)}, you have {len(current)}):")
    out("\n".join([*(f"+ {s}" for s in diff.added), *(f"- {s}" for s in diff.removed)]))
    out("Edit src/trading_bot/sp500_tickers.py (keep it sorted) and update its date note.")
    return 1


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
