"""CLI: run one trading cycle (scheduled every 5 minutes).

The time gate runs before any heavy import, so off-hours runs exit immediately.
"""
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from trading_bot.config import CYCLE_ERROR_LOG, load_rules
from trading_bot.cycle.timegate import INACTIVE, time_gate
from trading_bot.settings import SafetyError
from trading_bot.timeutil import now_et, stamp

CONNECT_RETRY_SECONDS = 5


def connect_with_retry(
    factory: Callable, *args, sleep: Callable[[float], None] = time.sleep
):
    """Connect; on failure wait 5s and try once more (a second failure raises)."""
    try:
        return factory(*args)
    except SafetyError:
        raise  # a wrong account will not fix itself in 5 seconds
    except Exception:
        sleep(CONNECT_RETRY_SECONDS)
        return factory(*args)


def log_error(path: Path, when: datetime) -> None:
    """Append the current exception's traceback to the cycle error log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"--- {when.isoformat()} ---\n{traceback.format_exc()}\n")


def report_crash(exc: Exception, send: Callable | None = None) -> None:
    """Push a high-priority crash alert. Never raises."""
    try:
        from trading_bot.notify import notify, send_safely

        send_safely(send or notify, "Cycle CRASHED", str(exc)[:500], "high")
    except Exception:
        pass


def main() -> int:
    rules = load_rules()
    now = now_et()
    status = time_gate(now, rules)
    if status in INACTIVE:
        print(stamp(f"market {status}; nothing to do", now))
        return 0
    return _run_active(rules)


def _run_active(rules: dict) -> int:
    # heavy imports happen only when the market is actually open
    from trading_bot.bot import run_trade_process
    from trading_bot.broker.client import IBKRClient
    from trading_bot.config import DECISION_LOG_PATH, POSITIONS_PATH, TRADES_CSV, WATCHLIST_PATH
    from trading_bot.cycle.decision_log import DecisionLog
    from trading_bot.cycle.engine import CycleContext, run_cycle
    from trading_bot.cycle.market_data import YahooMarketData
    from trading_bot.cycle.positions import PositionStore
    from trading_bot.settings import SafetyError, Settings, check_mode_matches_port
    from trading_bot.trades_log import TradeLog

    broker = None
    try:
        settings = Settings.from_env()
        check_mode_matches_port(settings)
        broker = connect_with_retry(
            IBKRClient, settings.host, settings.port, settings.client_id, settings.paper_trading
        )
        status = run_cycle(CycleContext(
            settings=settings, rules=rules, broker=broker, market_data=YahooMarketData(),
            store=PositionStore(POSITIONS_PATH), trades=TradeLog(TRADES_CSV),
            log=DecisionLog(DECISION_LOG_PATH), watchlist_path=WATCHLIST_PATH,
            clock=now_et, runner=run_trade_process,
        ))
        print(stamp(f"cycle complete ({status})", now_et()))
        return 0
    except SafetyError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        log_error(CYCLE_ERROR_LOG, now_et())
        report_crash(exc)
        print(stamp(f"cycle failed: {exc!r} (see {CYCLE_ERROR_LOG.name})", now_et()), file=sys.stderr)
        return 1
    finally:
        if broker is not None:
            broker.disconnect()


if __name__ == "__main__":
    sys.exit(main())
