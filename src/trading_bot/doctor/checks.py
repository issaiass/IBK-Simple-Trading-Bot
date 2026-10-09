"""Health checks behind `uv run doctor`: each returns a Check with the fix to try.

Every outside touch (settings, sockets, the IB session, the scheduler, the log) is
injected through `Environment`, so the checks run without TWS in tests.
"""
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from trading_bot.cycle.timegate import INACTIVE, time_gate
from trading_bot.settings import (
    LIVE_PORTS,
    PAPER_PORTS,
    SafetyError,
    Settings,
    check_account_matches_mode,
    check_mode_matches_port,
)

DOCTOR_CLIENT_ID = 90  # never the bot's own ids, so a running cycle is not kicked off
CONNECT_TIMEOUT_SECONDS = 4
STALE_AFTER = timedelta(minutes=15)  # three missed 5-minute cycles
PROBE_SYMBOL = "SPY"
DISABLED = "Disabled"
BROKER_CHECKS = ("TWS port", "API session", "Account", "Market data", "Order permission")


class Status(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


@dataclass(frozen=True)
class Environment:
    load_settings: Callable[[], Settings]
    probe: Callable[[str, int], bool]  # is anything listening on host:port
    ib_factory: Callable[[], Any]
    schedule_states: Callable[[], Mapping[str, str]]  # task name -> state
    last_heartbeat: Callable[[], datetime | None]
    rules: dict
    clock: Callable[[], datetime]


def check_settings(load: Callable[[], Settings]) -> tuple[Check, Settings | None]:
    try:
        settings = load()
        check_mode_matches_port(settings)
    except KeyError as exc:
        return Check("Settings", Status.FAIL, f"{exc.args[0]} is missing from .env",
                     "Copy .env.example to .env and fill in every value."), None
    except (SafetyError, ValueError) as exc:
        return Check("Settings", Status.FAIL, str(exc),
                     "Make PAPER_TRADING and IBKR_PORT agree (7497 TWS paper, 4002 Gateway paper)."), None
    mode = "paper" if settings.paper_trading else "LIVE"
    return Check("Settings", Status.OK, f"{mode} mode, {settings.host}:{settings.port}"), settings


def check_listening(settings: Settings, probe: Callable[[str, int], bool]) -> Check:
    if probe(settings.host, settings.port):
        return Check("TWS port", Status.OK, f"something is listening on port {settings.port}")
    others = sorted(p for p in PAPER_PORTS | LIVE_PORTS
                    if p != settings.port and probe(settings.host, p))
    if others:
        return Check("TWS port", Status.FAIL,
                     f"wrong API port: nothing on {settings.port}, but port {others[0]} is open",
                     f"Set IBKR_PORT={others[0]} in .env (and PAPER_TRADING to match), or change "
                     "the port in TWS: Edit > Global Configuration > API > Settings.")
    return Check("TWS port", Status.FAIL,
                 f"TWS / IB Gateway is not running (nothing on port {settings.port})",
                 "Start TWS (or IB Gateway) and log in to the paper account, then re-run.")


def check_api_session(settings: Settings, ib_factory: Callable[[], Any]) -> tuple[Check, Any]:
    ib = ib_factory()
    try:
        ib.connect(settings.host, settings.port, clientId=DOCTOR_CLIENT_ID,
                   timeout=CONNECT_TIMEOUT_SECONDS)
    except ConnectionRefusedError:
        return Check("API session", Status.FAIL, "connection refused",
                     "TWS is not accepting this connection: confirm the port and that TWS is "
                     "logged in."), None
    except Exception as exc:  # TimeoutError: the socket opened but the API never answered
        return Check("API session", Status.FAIL,
                     f"connected to the port but the API did not answer ({type(exc).__name__})",
                     "In TWS: Edit > Global Configuration > API > Settings: tick 'Enable ActiveX "
                     f"and Socket Clients' and add {settings.host} to 'Trusted IPs'. If a dialog "
                     "asks to accept the connection, click Accept. Also make sure no other app "
                     f"uses client id {DOCTOR_CLIENT_ID}."), None
    return Check("API session", Status.OK, f"handshake ok (client id {DOCTOR_CLIENT_ID})"), ib


def check_account(settings: Settings, ib: Any) -> Check:
    accounts = list(ib.managedAccounts())
    try:
        check_account_matches_mode(settings.paper_trading, accounts)
    except SafetyError as exc:
        wanted = "a paper (DU...) account" if settings.paper_trading else "a live account"
        return Check("Account", Status.FAIL, f"{exc} ({', '.join(accounts) or 'none'})",
                     f"Wrong account type: log TWS in with {wanted}, or set PAPER_TRADING to "
                     "match the account you use.")
    return Check("Account", Status.OK, ", ".join(accounts))


def _stock(symbol: str):
    from ib_async import Stock

    return Stock(symbol, "SMART", "USD")


def check_market_data(ib: Any) -> Check:
    try:
        contract = _stock(PROBE_SYMBOL)
        ib.qualifyContracts(contract)
        ib.reqMarketDataType(3)  # delayed is fine for paper, exactly as the bot asks
        ticker = ib.reqTickers(contract)[0]
        price = ticker.marketPrice()
        if math.isnan(price) or price <= 0:
            price = ticker.close
        if not math.isnan(price) and price > 0:
            return Check("Market data", Status.OK, f"{PROBE_SYMBOL} {price:.2f}")
        detail = f"no price for {PROBE_SYMBOL}"
    except Exception as exc:
        detail = f"price request failed ({type(exc).__name__}: {exc})"
    return Check("Market data", Status.WARN, detail,
                 "Missing market data subscription? Paper accounts get free delayed US data; "
                 "check Account Management > Market Data Subscriptions. It is also normal on a "
                 "weekend with no cached close.")


def check_order_permission(ib: Any) -> Check:
    """A what-if order: IBKR checks permissions and margin, and nothing is placed."""
    from ib_async import MarketOrder

    try:
        contract = _stock(PROBE_SYMBOL)
        ib.qualifyContracts(contract)
        order = MarketOrder("BUY", 1)
        order.tif = "DAY"
        state = ib.whatIfOrder(contract, order)
    except Exception as exc:
        return Check("Order permission", Status.FAIL, f"what-if order rejected ({exc})",
                     "Trading permissions not enabled? In Account Management > Settings > "
                     "Trading Permissions enable US Stocks. Also untick 'Read-Only API' in the "
                     "TWS API settings.")
    warning = getattr(state, "warningText", "")
    if warning:
        return Check("Order permission", Status.WARN, f"IBKR warns: {warning}",
                     "Review the account's buying power and permissions.")
    return Check("Order permission", Status.OK, "what-if order accepted (no order was placed)")


def check_schedule(states: Mapping[str, str] | None) -> Check:
    if states is None:
        return Check("Schedule", Status.SKIP, "could not read the scheduler")
    if not states:
        return Check("Schedule", Status.WARN, "no HT_* tasks are registered",
                     "Run: uv run setup-schedule")
    enabled = sum(1 for state in states.values() if state != DISABLED)
    if enabled == len(states):
        return Check("Schedule", Status.OK, f"{enabled} of {len(states)} tasks enabled")
    return Check("Schedule", Status.WARN, f"{enabled} of {len(states)} tasks enabled",
                 "Run: uv run enable-schedule   (uv run schedule-status shows each task)")


def check_heartbeat(
    last: datetime | None, now: datetime, rules: dict, *, schedule_enabled: bool
) -> Check:
    seen = "never" if last is None else f"{last:%Y-%m-%d %H:%M} ET"
    if time_gate(now, rules) in INACTIVE:
        return Check("Last cycle", Status.OK, f"market closed now; last cycle {seen}")
    if not schedule_enabled:
        return Check("Last cycle", Status.SKIP, f"schedule is off; last cycle {seen}")
    if last is not None and now - last <= STALE_AFTER:
        return Check("Last cycle", Status.OK, f"ran {int((now - last).total_seconds() // 60)} min ago")
    return Check("Last cycle", Status.WARN, f"the market is open but the last cycle was {seen}",
                 "Scheduled tasks not running? Check: the machine is asleep (power settings), you "
                 "are logged out of Windows (tasks run only while logged in), or Task Scheduler "
                 "permissions (run the task by hand and read its Last Run Result).")


def _skipped(names: tuple[str, ...], because: str) -> list[Check]:
    return [Check(name, Status.SKIP, because) for name in names]


def _broker_checks(settings: Settings, ib: Any) -> list[Check]:
    results = []
    for name, check in (("Account", lambda: check_account(settings, ib)),
                        ("Market data", lambda: check_market_data(ib)),
                        ("Order permission", lambda: check_order_permission(ib))):
        try:
            results.append(check())
        except Exception as exc:
            results.append(Check(name, Status.FAIL, f"check crashed: {exc!r}"))
    return results


def _broker_section(settings: Settings | None, env: Environment) -> list[Check]:
    if settings is None:
        return _skipped(BROKER_CHECKS, "needs valid settings")
    listening = check_listening(settings, env.probe)
    if listening.status is not Status.OK:
        return [listening, *_skipped(BROKER_CHECKS[1:], "TWS is not reachable")]
    session_check, ib = check_api_session(settings, env.ib_factory)
    if ib is None:
        return [listening, session_check, *_skipped(BROKER_CHECKS[2:], "no API session")]
    try:
        return [listening, session_check, *_broker_checks(settings, ib)]
    finally:
        ib.disconnect()


def run_doctor(env: Environment) -> list[Check]:
    settings_check, settings = check_settings(env.load_settings)
    results = [settings_check, *_broker_section(settings, env)]

    try:
        states = dict(env.schedule_states())
    except Exception:
        states = None
    results.append(check_schedule(states))

    try:
        last = env.last_heartbeat()
    except Exception:
        results.append(Check("Last cycle", Status.SKIP, "could not read the decision log"))
    else:
        enabled = states is None or any(state != DISABLED for state in states.values())
        results.append(check_heartbeat(last, env.clock(), env.rules, schedule_enabled=enabled))
    return results
