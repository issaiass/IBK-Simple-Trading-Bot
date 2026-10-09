"""Where the dashboard's data comes from: the decision log and live prices."""
import json
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from trading_bot.reporting.rmultiple import StopRecord

TAIL_BYTES = 256 * 1024  # enough for the most recent events without reading a 5 MB log


def _parse_lines(lines) -> Iterator[dict]:
    """JSON objects from log lines; blank, corrupt or truncated lines are skipped."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


class DecisionLogReader:
    """Read-only view of safety-check-log.json (one JSON object per line)."""

    def __init__(self, path: Path):
        self.path = path
        self._cache_key: tuple[int, int] | None = None
        self._cache: list[StopRecord] = []

    def _tail_events(self) -> list[dict]:
        try:
            with self.path.open("rb") as f:
                size = f.seek(0, 2)
                f.seek(max(0, size - TAIL_BYTES))
                raw = f.read().decode("utf-8", errors="ignore")
        except OSError:
            return []
        lines = raw.splitlines()
        if size > TAIL_BYTES:
            lines = lines[1:]  # the first line of a tail is usually cut in half
        return list(_parse_lines(lines))

    def last_event(self) -> dict | None:
        events = self._tail_events()
        return events[-1] if events else None

    def last_cycle(self) -> dict | None:
        """The newest "cycle" heartbeat the bot wrote."""
        for event in reversed(self._tail_events()):
            if event.get("event") == "cycle":
                return event
        return None

    def last_cycle_events(self) -> tuple[dict | None, list[dict]]:
        """The newest heartbeat and the events the bot logged after it, in that same run."""
        events = self._tail_events()
        for index in range(len(events) - 1, -1, -1):
            if events[index].get("event") == "cycle":
                return events[index], events[index + 1 :]
        return None, []

    def entered_stops(self) -> list[StopRecord]:
        """Initial stops from "entered" events, for computing R-multiples."""
        try:
            stat = self.path.stat()
        except OSError:
            return []
        key = (stat.st_mtime_ns, stat.st_size)
        if key == self._cache_key:
            return self._cache
        records = []
        with self.path.open(encoding="utf-8", errors="ignore") as f:
            for event in _parse_lines(f):
                stop = event.get("stop")
                if event.get("event") != "entered" or isinstance(stop, bool):
                    continue
                if not isinstance(stop, (int, float)) or stop <= 0:
                    continue
                try:
                    when = datetime.fromisoformat(event["timestamp"])
                except (KeyError, ValueError, TypeError):
                    continue
                records.append(StopRecord(str(event.get("symbol", "")), when, float(stop)))
        self._cache_key, self._cache = key, records
        return records


class CachedPriceProvider:
    """Latest prices with a short cache, so a polling dashboard doesn't hammer the source."""

    def __init__(
        self,
        fetch: Callable[[str], float],
        ttl_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch, self._ttl, self._clock = fetch, ttl_seconds, clock
        self._cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, fetched at)

    def latest(self, symbols: list[str]) -> dict[str, float]:
        """Prices for the symbols that could be fetched; failures are left out."""
        now = self._clock()
        prices = {}
        for symbol in symbols:
            cached = self._cache.get(symbol)
            if cached and now - cached[1] < self._ttl:
                prices[symbol] = cached[0]
                continue
            try:
                price = self._fetch(symbol)
            except Exception:
                continue  # not cached, so the next poll retries
            self._cache[symbol] = (price, now)
            prices[symbol] = price
        return prices


def yahoo_price(symbol: str) -> float:
    """Latest regular-session price from Yahoo (imported lazily: it is heavy)."""
    from trading_bot.cycle.market_data import YahooMarketData
    from trading_bot.timeutil import now_et

    price, _lows = YahooMarketData().position_snapshot(symbol, now_et().date())
    return price
