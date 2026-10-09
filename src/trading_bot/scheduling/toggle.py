"""Pause and resume the scheduled bot without deleting it.

    schedule-status                      which HT_* tasks are enabled
    disable-schedule [--task cycle]      stop them firing (all of them, or just the named ones)
    enable-schedule  [--task cycle]      let them fire again

Unlike cleanup-schedule this keeps the tasks and the power setting untouched.
"""
import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

from trading_bot.scheduling.setup import TASK_PREFIX, run_command

# State is read through PowerShell: schtasks prints it in the local language
# ("Listo"), while the ScheduledTask State enum is always English.
LIST_COMMAND = [
    "powershell", "-NoProfile", "-Command",
    "Get-ScheduledTask -TaskName 'HT_*' -ErrorAction SilentlyContinue "
    "| ForEach-Object { $_.TaskName + ',' + $_.State }",
]
DISABLED = "Disabled"


class UnknownTask(Exception):
    """A requested task name matches no registered HT_* task."""


def list_tasks(run: Callable = subprocess.run) -> dict[str, str]:
    """HT_* task name -> State (Ready, Running, Disabled...)."""
    output = run_command(run, LIST_COMMAND).stdout or ""
    states = {}
    for line in output.splitlines():
        name, _, state = line.strip().partition(",")
        if name.startswith(TASK_PREFIX):
            states[name] = state
    return states


def resolve_targets(requested: Sequence[str] | None, existing: Sequence[str]) -> list[str]:
    """Task names to change. Accepts 'cycle', 'HT_Cycle', any case; None means all."""
    if not requested:
        return list(existing)
    by_key = {name.lower(): name for name in existing}
    resolved, unknown = [], []
    for item in requested:
        key = item.lower()
        match = by_key.get(key) or by_key.get(TASK_PREFIX.lower() + key)
        if match:
            resolved.append(match)
        else:
            unknown.append(item)
    if unknown:
        raise UnknownTask(f"no such task: {', '.join(unknown)} (have: {', '.join(existing)})")
    return resolved


def set_enabled(
    enabled: bool,
    requested: Sequence[str] | None = None,
    *,
    run: Callable = subprocess.run,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    """Enable or disable tasks, then read the real state back to verify it.

    Returns 0 on success, 1 if any task did not reach the wanted state, 2 for an
    unknown task name (nothing is changed in that case).
    """
    existing = list_tasks(run)
    if not existing:
        out("No HT_* tasks registered.")
        return 0
    try:
        targets = resolve_targets(requested, list(existing))
    except UnknownTask as exc:
        err(str(exc))
        return 2

    flag = "/enable" if enabled else "/disable"
    failed = set()
    for name in targets:
        result = run_command(run, ["schtasks", "/change", "/tn", name, flag])
        if result.returncode:
            failed.add(name)
            err(f"FAILED {name}: {(result.stderr or result.stdout).strip()}")

    # trust the scheduler's real state, not the exit code
    final = list_tasks(run)
    for name in targets:
        state = final.get(name, "missing")
        out(f"{name:<18} {state}")
        if state == "missing" or (state != DISABLED) != enabled:
            if name not in failed:
                err(f"{name} is {state}, expected {'enabled' if enabled else 'disabled'}")
            failed.add(name)
    return 1 if failed else 0


def schedule_status(
    *, run: Callable = subprocess.run, out: Callable = print
) -> int:
    states = list_tasks(run)
    if not states:
        out("No HT_* tasks registered.")
        return 0
    for name, state in states.items():
        out(f"{name:<18} {state:<9} {'DISABLED' if state == DISABLED else 'enabled'}")
    on = sum(1 for state in states.values() if state != DISABLED)
    out(f"{on} of {len(states)} tasks enabled.")
    return 0


def parse_task_args(description: str, argv: Sequence[str] | None) -> list[str] | None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--task", action="append", metavar="NAME",
                        help="task to change, e.g. cycle or HT_Cycle (repeatable; default: all)")
    return parser.parse_args(argv).task


def disable_main(argv: Sequence[str] | None = None) -> int:
    if sys.platform == "darwin":
        from trading_bot.scheduling import launchd

        return launchd.disable_main(argv)
    if sys.platform != "win32":  # Linux and other POSIX systems use cron
        from trading_bot.scheduling import cron

        return cron.disable_main(argv)
    return set_enabled(False, parse_task_args("Disable scheduled bot tasks", argv))


def enable_main(argv: Sequence[str] | None = None) -> int:
    if sys.platform == "darwin":
        from trading_bot.scheduling import launchd

        return launchd.enable_main(argv)
    if sys.platform != "win32":
        from trading_bot.scheduling import cron

        return cron.enable_main(argv)
    return set_enabled(True, parse_task_args("Enable scheduled bot tasks", argv))


def status_main() -> int:
    if sys.platform == "darwin":
        from trading_bot.scheduling import launchd

        return launchd.status_main()
    if sys.platform != "win32":
        from trading_bot.scheduling import cron

        return cron.status_main()
    return schedule_status()


if __name__ == "__main__":
    sys.exit(status_main())
