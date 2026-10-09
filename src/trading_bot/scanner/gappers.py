"""Pure gapper logic: symbol mapping, gap percentage and selection."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot:
    symbol: str  # IBKR format, e.g. "BRK B"
    prior_close: float
    price: float


@dataclass(frozen=True)
class Gapper:
    symbol: str
    prior_close: float
    price: float
    gap_pct: float


def to_yahoo(symbol: str) -> str:
    """IBKR "BRK B" -> Yahoo "BRK-B"."""
    return symbol.replace(" ", "-")


def from_yahoo(symbol: str) -> str:
    """Yahoo "BRK-B" -> IBKR "BRK B"."""
    return symbol.replace("-", " ")


def gap_pct(prior_close: float, price: float) -> float:
    if prior_close <= 0:
        return 0.0
    return (price - prior_close) / prior_close * 100


def select_gappers(
    snapshots: list[Snapshot], min_gap_pct: float, min_price: float
) -> list[Gapper]:
    """Gap-ups of at least `min_gap_pct` priced at `min_price` or more, biggest first."""
    gappers = [
        Gapper(s.symbol, s.prior_close, s.price, gap_pct(s.prior_close, s.price))
        for s in snapshots
        if s.price >= min_price
    ]
    return sorted(
        (g for g in gappers if g.gap_pct >= min_gap_pct),
        key=lambda g: g.gap_pct,
        reverse=True,
    )
