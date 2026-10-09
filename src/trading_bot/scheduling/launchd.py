"""macOS (launchd) backend for the scheduled bot.

Each job is one LaunchAgent plist in ~/Library/LaunchAgents named
com.tradingbot.HT_<Name>.plist, so other agents are never touched. Disabling a job
unloads it and marks it disabled with `launchctl disable`, which survives a reboot;
enabling reverses both. The plist stays in place, so enable/disable round-trips.

Times are converted from US Eastern to the machine's local time, so they drift by
an hour when only one of the two zones changes its clocks: re-run setup-schedule
after daylight-saving changes. The Windows keep-awake task has no launchd equivalent.
"""
import os
import plistlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from pathlib import Path

from trading_bot.config import LOG_DIR, VENV_PYTHON
from trading_bot.scheduling.setup import run_command
from trading_bot.scheduling.tasks import CYCLE_MINUTES, build_tasks, to_local
from trading_bot.scheduling.toggle import UnknownTask, parse_task_args, resolve_targets
from trading_bot.timeutil import now_et

LABEL_PREFIX = "com.tradingbot."
AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
BUSINESS_DAYS = 5
DISABLED_LINE_VALUES = {"disabled", "true"}  # print-disabled wording differs between macOS versions


@dataclass(frozen=True)
class LaunchdJob:
    name: str
    label: str
    plist: dict
    et_time: str = ""

    @property
    def filename(self) -> str:
        return f"{self.label}.plist"


def weekdays(day_shift: int) -> list[int]:
    """launchd weekdays (0 = Sunday) for Mon-Fri moved by `day_shift` days."""
    return [(day + 1 + day_shift) % 7 for day in range(BUSINESS_DAYS)]


def build_jobs(
    venv_py: Path, logs_dir: Path, on: date, local_tz: tzinfo | None = None
) -> list[LaunchdJob]:
    """The scheduled jobs (all but keep-awake, which is Windows-only)."""
    log = str(logs_dir / "launchd.log")
    jobs = []
    for spec in build_tasks():
        if spec.raw_command:
            continue
        label = f"{LABEL_PREFIX}{spec.name}"
        plist = {
            "Label": label,
            "ProgramArguments": [str(venv_py), "-m", spec.module],
            "WorkingDirectory": str(logs_dir.parent),
            "StandardOutPath": log,
            "StandardErrorPath": log,
        }
        if spec.kind == "minute":
            plist["StartInterval"] = CYCLE_MINUTES * 60
        else:
            slot = to_local(spec.et_time, on, local_tz)
            hour, minute = (int(part) for part in slot.time.split(":"))
            plist["StartCalendarInterval"] = [
                {"Hour": hour, "Minute": minute, "Weekday": day}
                for day in weekdays(slot.day_shift)
            ]
        jobs.append(LaunchdJob(spec.name, label, plist, spec.et_time))
    return jobs


def plist_bytes(job: LaunchdJob) -> bytes:
    return plistlib.dumps(job.plist)


def parse_disabled(output: str) -> set[str]:
    """Labels listed as disabled in `launchctl print-disabled` output."""
    disabled = set()
    for line in output.splitlines():
        label, arrow, value = line.strip().partition(" => ")
        if arrow and value.strip().lower() in DISABLED_LINE_VALUES:
            disabled.add(label.strip().strip('"'))
    return disabled


def _domain(uid: int | None) -> str:
    return f"gui/{os.getuid() if uid is None else uid}"


def installed_jobs(agents_dir: Path) -> dict[str, str]:
    """name -> label for our plists on disk, in schedule order."""
    found = {}
    for path in sorted(agents_dir.glob(f"{LABEL_PREFIX}HT_*.plist")):
        label = path.stem
        found[label.removeprefix(LABEL_PREFIX)] = label
    return found


def _is_loaded(run: Callable, domain: str, label: str) -> bool:
    return run_command(run, ["launchctl", "print", f"{domain}/{label}"]).returncode == 0


def _disabled_labels(run: Callable, domain: str) -> set[str]:
    return parse_disabled(run_command(run, ["launchctl", "print-disabled", domain]).stdout or "")


def _load(run: Callable, domain: str, label: str, path: Path):
    """Enable, replace any loaded copy, and bootstrap. Returns the bootstrap result."""
    run_command(run, ["launchctl", "bootout", f"{domain}/{label}"])  # not loaded is fine
    run_command(run, ["launchctl", "enable", f"{domain}/{label}"])
    return run_command(run, ["launchctl", "bootstrap", domain, str(path)])


def _unload(run: Callable, domain: str, label: str) -> None:
    run_command(run, ["launchctl", "bootout", f"{domain}/{label}"])  # not loaded is fine


def launchd_states(
    *, run: Callable = subprocess.run, agents_dir: Path = AGENTS_DIR, uid: int | None = None
) -> dict[str, str]:
    """HT_* name -> Ready/Disabled (also used by `doctor`)."""
    jobs = installed_jobs(agents_dir)
    if not jobs:
        return {}
    disabled = _disabled_labels(run, _domain(uid))
    return {name: "Disabled" if label in disabled else "Ready" for name, label in jobs.items()}


def setup_launchd(
    *,
    run: Callable = subprocess.run,
    which: Callable = shutil.which,
    venv_py: Path = VENV_PYTHON,
    logs_dir: Path = LOG_DIR,
    agents_dir: Path = AGENTS_DIR,
    uid: int | None = None,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    if not venv_py.exists():
        err(f"STOP: {venv_py} not found. Create the venv first (uv sync).")
        return 1
    if not which("launchctl"):
        err("STOP: launchctl not found; launchd setup needs macOS.")
        return 1

    domain = _domain(uid)
    jobs = build_jobs(venv_py, logs_dir, (now or now_et()).date(), local_tz)
    agents_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)  # launchd will not create the log's folder

    created = 0
    for job in jobs:
        path = agents_dir / job.filename
        path.write_bytes(plist_bytes(job))
        result = _load(run, domain, job.label, path)
        if result.returncode or not _is_loaded(run, domain, job.label):
            err(f"FAILED {job.name}: {(result.stderr or result.stdout or 'not loaded').strip()}")
            continue
        created += 1
        out(f"OK    {job.name:<18} ({job.et_time} ET)")

    out("\nNOTE: times were converted using today's daylight-saving rules. Re-run this "
        "setup after the US clocks change (March and November) or when your own do.")
    out("NOTE: there is no keep-awake job on macOS; stop the Mac from going to sleep yourself "
        "(System Settings > Battery / Energy: prevent automatic sleeping, or run `caffeinate -s`). "
        "Output goes to logs/launchd.log.")
    if created == len(jobs):
        out(f"SCHEDULED: {created} launchd agents installed. The bot will fire on its own "
            "starting next market open. Watch Telegram.")
        return 0
    out(f"SCHEDULED: {created} of {len(jobs)} agents installed; fix the errors above and re-run.")
    return 1


def cleanup_launchd(
    *,
    run: Callable = subprocess.run,
    agents_dir: Path = AGENTS_DIR,
    uid: int | None = None,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    jobs = installed_jobs(agents_dir)
    if not jobs:
        out("Nothing to clean.")
        return 0
    domain = _domain(uid)
    failed = 0
    for label in jobs.values():
        _unload(run, domain, label)
        run_command(run, ["launchctl", "enable", f"{domain}/{label}"])  # clear the disabled override
        try:
            (agents_dir / f"{label}.plist").unlink()
        except OSError as exc:
            failed += 1
            err(f"FAILED to delete {label}: {exc}")
    out(f"CLEANUP DONE: {len(jobs) - failed} agents removed.")
    return 1 if failed else 0


def set_enabled_launchd(
    enabled: bool,
    requested: Sequence[str] | None = None,
    *,
    run: Callable = subprocess.run,
    agents_dir: Path = AGENTS_DIR,
    uid: int | None = None,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    """Enable/disable agents, then read launchd back to verify. 2 = unknown name."""
    existing = installed_jobs(agents_dir)
    if not existing:
        out("No HT_* tasks registered.")
        return 0
    try:
        targets = resolve_targets(requested, list(existing))
    except UnknownTask as exc:
        err(str(exc))
        return 2

    domain = _domain(uid)
    for name in targets:
        label = existing[name]
        if enabled:
            _load(run, domain, label, agents_dir / f"{label}.plist")
        else:
            _unload(run, domain, label)
            run_command(run, ["launchctl", "disable", f"{domain}/{label}"])

    disabled = _disabled_labels(run, domain)
    failed = False
    for name in targets:
        label = existing[name]
        is_on = label not in disabled and _is_loaded(run, domain, label)
        out(f"{name:<18} {'Ready' if is_on else 'Disabled'}")
        if is_on is not enabled:
            err(f"{name} is not {'enabled' if enabled else 'disabled'} after the update")
            failed = True
    return 1 if failed else 0


def status_launchd(
    *,
    run: Callable = subprocess.run,
    agents_dir: Path = AGENTS_DIR,
    uid: int | None = None,
    out: Callable = print,
) -> int:
    states = launchd_states(run=run, agents_dir=agents_dir, uid=uid)
    if not states:
        out("No HT_* tasks registered.")
        return 0
    for name, state in states.items():
        out(f"{name:<18} {state:<9} {'DISABLED' if state == 'Disabled' else 'enabled'}")
    on = sum(1 for state in states.values() if state != "Disabled")
    out(f"{on} of {len(states)} tasks enabled.")
    return 0


def setup_main() -> int:
    return setup_launchd()


def cleanup_main() -> int:
    return cleanup_launchd()


def status_main() -> int:
    return status_launchd()


def disable_main(argv: Sequence[str] | None = None) -> int:
    return set_enabled_launchd(False, parse_task_args("Disable scheduled bot agents", argv))


def enable_main(argv: Sequence[str] | None = None) -> int:
    return set_enabled_launchd(True, parse_task_args("Enable scheduled bot agents", argv))
