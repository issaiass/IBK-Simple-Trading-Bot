"""Pluggable indicators for the optional `custom_filters` list in rules.json.

Adding one is a decorated function: it takes a close-price Series plus keyword
params and returns the latest value (or None when there is too little data).
Then a rules.json entry can use it by name, with no change to filters.py:

    {"name": "X1_rsi", "indicator": "rsi", "source": "intraday",
     "params": {"period": 14}, "op": ">=", "value": 50}

`source` is "daily" (closes of prior days) or "intraday" (today's regular-session bars).
"""
import operator
from collections.abc import Callable, Mapping, Sequence

import pandas as pd

Indicator = Callable[..., float | None]
REGISTRY: dict[str, Indicator] = {}
OPERATORS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}


class UnknownIndicator(KeyError):
    """rules.json names an indicator that is not registered."""

    def __str__(self) -> str:  # KeyError would quote the whole message
        return str(self.args[0])


def indicator(name: str) -> Callable[[Indicator], Indicator]:
    def register(function: Indicator) -> Indicator:
        REGISTRY[name] = function
        return function

    return register


def get_indicator(name: str) -> Indicator:
    if name not in REGISTRY:
        raise UnknownIndicator(f"unknown indicator {name!r}; available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[name]


@indicator("rsi")
def rsi(close: pd.Series, period: int = 14) -> float | None:
    """Wilder's relative strength index of the last bar."""
    if len(close) < period + 1:
        return None
    change = close.diff().dropna()
    gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    loss = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    if gain == 0 and loss == 0:
        return 50.0
    if loss == 0:
        return 100.0
    return float(100 - 100 / (1 + gain / loss))


@indicator("macd_hist")
def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> float | None:
    """MACD histogram (MACD line minus its signal line) of the last bar."""
    if len(close) < slow + signal - 1:
        return None
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    return float((line - line.ewm(span=signal, adjust=False).mean()).iloc[-1])


def compare(value: float | None, op: str, threshold: float) -> bool:
    if op not in OPERATORS:
        raise ValueError(f"unknown operator {op!r}; use one of {', '.join(OPERATORS)}")
    return value is not None and bool(OPERATORS[op](value, threshold))


def evaluate_custom_filters(
    specs: Sequence[Mapping], sources: Mapping[str, pd.Series]
) -> dict[str, bool]:
    """name -> passed for each spec. Missing data fails closed; bad config raises."""
    checks = {}
    for spec in specs:
        if spec["source"] not in sources:
            raise ValueError(f"unknown source {spec['source']!r}; use one of {', '.join(sources)}")
        value = get_indicator(spec["indicator"])(sources[spec["source"]], **spec.get("params", {}))
        checks[spec["name"]] = compare(value, spec["op"], spec["value"])
    return checks
