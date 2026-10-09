"""Delete every HT_* task and restore the power setting setup recorded."""
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from trading_bot.config import SCHEDULE_STATE_PATH
from trading_bot.scheduling.setup import parse_task_rows, run_command
from trading_bot.scheduling.state import DEFAULT_STANDBY_MINUTES, ScheduleState


def cleanup_schedule(
    *,
    run: Callable = subprocess.run,
    state_path: Path = SCHEDULE_STATE_PATH,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    state = ScheduleState(state_path)
    names = [row[0] for row in parse_task_rows(
        run_command(run, ["schtasks", "/query", "/fo", "CSV", "/nh"]).stdout)]
    if not names and not state.exists():
        out("Nothing to clean.")
        return 0

    deleted = failed = 0
    for name in names:
        result = run_command(run, ["schtasks", "/delete", "/tn", name, "/f"])
        if result.returncode:
            failed += 1
            err(f"FAILED to delete {name}: {(result.stderr or result.stdout).strip()}")
        else:
            deleted += 1

    minutes = state.original_standby()
    if minutes is None:
        minutes = DEFAULT_STANDBY_MINUTES
    result = run_command(run, ["powercfg", "/change", "standby-timeout-ac", str(minutes)])
    if result.returncode:
        err(f"FAILED to restore the power setting: {(result.stderr or result.stdout).strip()}")
        failed += 1
    else:
        state.clear()

    suffix = f" ({failed} failed)" if failed else ""
    out(f"CLEANUP DONE: {deleted} tasks deleted; default power settings restored.{suffix}")
    return 1 if failed else 0


def main() -> int:
    if sys.platform == "darwin":
        from trading_bot.scheduling import launchd

        return launchd.cleanup_main()
    if sys.platform != "win32":  # Linux and other POSIX systems use cron
        from trading_bot.scheduling import cron

        return cron.cleanup_main()
    return cleanup_schedule()


if __name__ == "__main__":
    sys.exit(main())
