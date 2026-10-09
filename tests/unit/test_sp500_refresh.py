from types import SimpleNamespace

import pytest

from trading_bot.maintenance import sp500_refresh as refresh
from trading_bot.maintenance.sp500_refresh import (
    UniverseDiff,
    diff_universe,
    parse_constituents,
)

PAGE = """
<html><body>
<table id="constituents" class="wikitable sortable">
 <thead><tr><th>Symbol</th><th>Security</th></tr></thead>
 <tbody>
  <tr><td><a class="external text" href="https://www.nyse.com/quote/XNYS:MMM">MMM</a>
      </td><td><a href="/wiki/3M">3M</a></td></tr>
  <tr><td><a href="https://www.nyse.com/quote/XNYS:BRK.B">BRK.B</a></td><td>Berkshire</td></tr>
  <tr><td><a href="https://www.nasdaq.com/market-activity/stocks/aapl">AAPL</a></td><td>Apple</td></tr>
 </tbody>
</table>
<table id="changes"><tr><td><a>ZZZZ</a></td></tr></table>
</body></html>
"""


class TestParseConstituents:
    def test_reads_the_first_column_of_the_constituents_table_only(self):
        assert parse_constituents(PAGE) == ["AAPL", "BRK B", "MMM"]

    def test_class_shares_are_converted_to_the_ibkr_space_format(self):
        assert "BRK B" in parse_constituents(PAGE)

    def test_a_page_without_the_table_is_an_error(self):
        with pytest.raises(ValueError, match="constituents"):
            parse_constituents("<html><body>maintenance</body></html>")


class TestDiffUniverse:
    def test_reports_what_joined_and_what_left(self):
        diff = diff_universe(current=["A", "B", "C"], latest=["B", "C", "D", "E"])
        assert diff == UniverseDiff(added=["D", "E"], removed=["A"])

    def test_identical_lists_have_no_changes(self):
        assert not diff_universe(["A", "B"], ["B", "A"])

    def test_results_are_sorted(self):
        assert diff_universe([], ["Z", "M", "A"]).added == ["A", "M", "Z"]


def fetcher(text="", status=200):
    return lambda url, **kwargs: SimpleNamespace(
        text=text, status_code=status, raise_for_status=lambda: None if status < 400 else (_ for _ in ()).throw(RuntimeError(f"HTTP {status}"))
    )


class TestMain:
    def run(self, page, current):
        lines = []
        code = refresh.run(current=current, get=fetcher(page), out=lines.append)
        return code, "\n".join(lines)

    def test_in_sync_exits_zero(self):
        code, text = self.run(PAGE, ["AAPL", "BRK B", "MMM"])
        assert code == 0 and "up to date" in text.lower()

    def test_drift_exits_one_and_lists_both_directions(self):
        code, text = self.run(PAGE, ["AAPL", "OLD"])
        assert code == 1
        assert "+ BRK B" in text and "+ MMM" in text and "- OLD" in text

    def test_drift_tells_you_where_to_edit(self):
        _, text = self.run(PAGE, ["AAPL"])
        assert "sp500_tickers.py" in text

    def test_fetch_failure_exits_two_without_a_traceback(self):
        lines = []
        code = refresh.run(current=[], get=fetcher(status=503), out=lines.append)
        assert code == 2 and "503" in "\n".join(lines)

    def test_unreadable_page_exits_two(self):
        code, text = self.run("<html></html>", ["A"])
        assert code == 2 and "constituents" in text

    def test_sends_a_user_agent_because_wikipedia_blocks_anonymous_clients(self):
        seen = {}

        def get(url, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(text=PAGE, raise_for_status=lambda: None)

        refresh.run(current=[], get=get, out=lambda m: None)
        assert seen["headers"]["User-Agent"]
