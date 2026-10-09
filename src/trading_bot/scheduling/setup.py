"""Register the eleven HT_* tasks with Windows Task Scheduler (idempotent)."""
import csv
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, tzinfo
from pathlib import Path

from trading_bot.config import SCHEDULE_STATE_PATH, VENV_PYTHON
from trading_bot.scheduling.powercfg import QUERY_STANDBY, parse_ac_standby_minutes
from trading_bot.scheduling.state import ScheduleState
from trading_bot.scheduling.tasks import build_schtasks_args, build_tasks, to_local
from trading_bot.timeutil import now_et

TASK_PREFIX = "HT_"
DEFAULT_DATE_PATTERN = "M/d/yyyy"
DATE_PATTERN_COMMAND = ["powershell", "-NoProfile", "-Command",
                        "(Get-Culture).DateTimeFormat.ShortDatePattern"]


def run_command(run: Callable, args: list[str], input_text: str | None = None):
    # errors="replace": Windows tools print localized text in the OEM code page, and a
    # strict decode would crash the reader thread and lose the whole output
    extra = {} if input_text is None else {"input": input_text}
    return run(args, check=False, capture_output=True, text=True, errors="replace", **extra)


def parse_task_rows(csv_text: str) -> list[tuple[str, str, str]]:
    """(name, next run, status) for every HT_* task in `schtasks /query /fo CSV`."""
    rows = []
    for row in csv.reader(csv_text.splitlines()):
        if len(row) >= 3 and row[0].lstrip("\\").startswith(TASK_PREFIX):
            rows.append((row[0].lstrip("\\"), row[1], row[2]))
    return rows


def detect_date_pattern(run: Callable) -> str:
    """The locale's short date pattern; schtasks rejects a mismatched /sd."""
    try:
        pattern = run_command(run, DATE_PATTERN_COMMAND).stdout.strip()
    except OSError:
        pattern = ""
    return pattern or DEFAULT_DATE_PATTERN


def setup_schedule(
    *,
    run: Callable = subprocess.run,
    which: Callable = shutil.which,
    venv_py: Path = VENV_PYTHON,
    state_path: Path = SCHEDULE_STATE_PATH,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    if not venv_py.exists():
        err(f"STOP: {venv_py} not found. Create the venv first (uv sync).")
        return 1
    if not which("schtasks"):
        err("STOP: schtasks not found; Task Scheduler setup needs Windows.")
        return 1

    today = (now or now_et()).date()
    pattern = detect_date_pattern(run)

    # remember the power setting the keep-awake task will override
    minutes = parse_ac_standby_minutes(run_command(run, QUERY_STANDBY).stdout)
    if minutes is not None:
        ScheduleState(state_path).record_original_standby(minutes)

    tasks = build_tasks()
    created = 0
    for spec in tasks:
        args = build_schtasks_args(spec, venv_py, today, pattern, local_tz)
        result = run_command(run, args)
        if result.returncode:
            err(f"FAILED {spec.name}: {(result.stderr or result.stdout).strip()}")
            continue
        created += 1
        slot = to_local(spec.et_time, today, local_tz)
        out(f"OK    {spec.name:<18} {slot.time} local  ({spec.et_time} ET)")

    rows = parse_task_rows(run_command(run, ["schtasks", "/query", "/fo", "CSV", "/nh"]).stdout)
    out(f"\n{'TASK':<18} {'NEXT RUN':<24} STATUS")
    for name, next_run, status in rows:
        out(f"{name:<18} {next_run:<24} {status}")

    out("\nNOTE: times were converted using today's daylight-saving rules. Re-run this "
        "setup after the US clocks change (March and November) or when your own do.")
    if created == len(tasks):
        out(f"SCHEDULED: {created} tasks created. The bot will fire on its own starting "
            "next market open. Watch Telegram.")
        return 0
    out(f"SCHEDULED: {created} of {len(tasks)} tasks created; fix the errors above and re-run.")
    return 1


def main() -> int:
    if sys.platform == "darwin":
        from trading_bot.scheduling import launchd

        return launchd.setup_main()
    if sys.platform != "win32":  # Linux and other POSIX systems use cron
        from trading_bot.scheduling import cron

        return cron.setup_main()
    return setup_schedule()


if __name__ == "__main__":
    sys.exit(main())
