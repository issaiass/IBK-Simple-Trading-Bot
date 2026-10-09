"""watchlist.txt: one symbol per line."""
from pathlib import Path

from trading_bot.scanner.gappers import Gapper


def write_watchlist(path: Path, gappers: list[Gapper]) -> None:
    """Replace the file atomically so readers never see a half-written list."""
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("".join(f"{g.symbol}\n" for g in gappers), encoding="utf-8")
    temp.replace(path)


def read_watchlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    symbols = (
        line.split("#")[0].strip()  # drop comments, incl. "AAPL  # gap +3.45% ..."
        for line in path.read_text(encoding="utf-8").splitlines()
    )
    return [s for s in symbols if s]
