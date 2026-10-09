"""Linux (cron) backend for the scheduled bot.

Everything this module installs sits between two marker lines in the user's own
crontab; every other crontab entry is left untouched. Jobs are disabled by
commenting them out with a "#off# " prefix, so enable/disable round-trips exactly.

Times are converted from US Eastern to the machine's local time, so they drift by
an hour when only one of the two zones changes its clocks: re-run setup-schedule
after daylight-saving changes. The Windows keep-awake task has no cron equivalent.
"""
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from pathlib import Path

from trading_bot.config import CRONTAB_BACKUP_PATH, LOG_DIR, VENV_PYTHON
from trading_bot.scheduling.setup import run_command
from trading_bot.scheduling.tasks import CYCLE_MINUTES, build_tasks, to_local
from trading_bot.scheduling.toggle import UnknownTask, parse_task_args, resolve_targets
from trading_bot.timeutil import now_et

BEGIN = "# >>> trading-bot schedule (managed by setup-schedule; do not edit inside) >>>"
END = "# <<< trading-bot schedule <<<"
OFF = "#off# "
NAME = re.compile(r"#\s*(HT_\w+)\s*$")


class CrontabError(Exception):
    """The crontab could not be read or written."""


@dataclass(frozen=True)
class CronJob:
    name: str
    schedule: str  # the five cron time fields
    command: str
    et_time: str = ""

    def line(self) -> str:
        return f"{self.schedule} {self.command}  # {self.name}"


def dow_field(day_shift: int) -> str:
    """Cron day-of-week (0=Sunday) for Mon-Fri moved by `day_shift` days."""
    days = sorted({(d + day_shift) % 7 for d in range(1, 6)})
    if days[-1] - days[0] == len(days) - 1:
        return f"{days[0]}-{days[-1]}"
    return ",".join(str(d) for d in days)


def _command(venv_py: Path, module: str, logs_dir: Path) -> str:
    python = shlex.quote(venv_py.as_posix())
    log = shlex.quote((logs_dir / "cron.log").as_posix())
    return f"{python} -m {module} >> {log} 2>&1".replace("%", "\\%")  # % is a newline in cron


def build_jobs(
    venv_py: Path, logs_dir: Path, on: date, local_tz: tzinfo | None = None
) -> list[CronJob]:
    """The scheduled jobs (all but keep-awake, which is Windows-only)."""
    jobs = []
    for spec in build_tasks():
        if spec.raw_command:
            continue
        if spec.kind == "minute":
            schedule = f"*/{CYCLE_MINUTES} * * * *"
        else:
            slot = to_local(spec.et_time, on, local_tz)
            hour, minute = (int(part) for part in slot.time.split(":"))
            schedule = f"{minute} {hour} * * {dow_field(slot.day_shift)}"
        jobs.append(CronJob(spec.name, schedule, _command(venv_py, spec.module, logs_dir),
                            spec.et_time))
    return jobs


def _block_bounds(lines: list[str]) -> tuple[int, int] | None:
    starts = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    if not starts:
        return None
    ends = [i for i, line in enumerate(lines) if line.strip() == END and i > starts[0]]
    if not ends:
        raise ValueError("the managed crontab block has no end marker; fix it by hand")
    return starts[0], ends[0]


def strip_block(text: str) -> str:
    """The crontab without our managed block."""
    lines = text.splitlines(keepends=True)
    bounds = _block_bounds(lines)
    if bounds is None:
        return text
    start, end = bounds
    return "".join(lines[:start] + lines[end + 1:])


def apply_block(text: str, jobs: Sequence[CronJob]) -> str:
    """The crontab with our block (re)written after the user's own entries."""
    base = strip_block(text)
    if base and not base.endswith("\n"):
        base += "\n"
    body = "".join(job.line() + "\n" for job in jobs)
    return f"{base}{BEGIN}\n{body}{END}\n"


def _block_lines(text: str) -> tuple[list[str], tuple[int, int] | None]:
    lines = text.splitlines(keepends=True)
    return lines, _block_bounds(lines)


def parse_jobs(text: str) -> dict[str, bool]:
    """name -> enabled for the jobs inside the managed block."""
    lines, bounds = _block_lines(text)
    if bounds is None:
        return {}
    states = {}
    for line in lines[bounds[0] + 1:bounds[1]]:
        match = NAME.search(line.strip())
        if match:
            states[match.group(1)] = not line.startswith(OFF)
    return states


def set_jobs_enabled(text: str, names: Sequence[str], enabled: bool) -> str:
    """Comment out (or restore) the named jobs inside the managed block."""
    lines, bounds = _block_lines(text)
    if bounds is None:
        return text
    wanted = set(names)
    for i in range(bounds[0] + 1, bounds[1]):
        match = NAME.search(lines[i].strip())
        if not match or match.group(1) not in wanted:
            continue
        on = not lines[i].startswith(OFF)
        if enabled and not on:
            lines[i] = lines[i][len(OFF):]
        elif not enabled and on:
            lines[i] = OFF + lines[i]
    return "".join(lines)


def read_crontab(run: Callable) -> str:
    """The user's crontab; "" if there is none. Any other failure raises."""
    result = run_command(run, ["crontab", "-l"])
    if result.returncode == 0:
        return result.stdout or ""
    if "no crontab" in (result.stderr or "").lower():
        return ""
    raise CrontabError((result.stderr or result.stdout or "crontab -l failed").strip())


def write_crontab(run: Callable, text: str) -> None:
    result = (run_command(run, ["crontab", "-r"]) if not text.strip()
              else run_command(run, ["crontab", "-"], input_text=text))
    if result.returncode:
        raise CrontabError((result.stderr or result.stdout or "crontab write failed").strip())


def setup_cron(
    *,
    run: Callable = subprocess.run,
    which: Callable = shutil.which,
    venv_py: Path = VENV_PYTHON,
    logs_dir: Path = LOG_DIR,
    backup_path: Path = CRONTAB_BACKUP_PATH,
    now: datetime | None = None,
    local_tz: tzinfo | None = None,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    if not venv_py.exists():
        err(f"STOP: {venv_py} not found. Create the venv first (uv sync).")
        return 1
    if not which("crontab"):
        err("STOP: crontab not found. Install cron (e.g. sudo apt install cron) and make "
            "sure its service is running.")
        return 1
    try:
        current = read_crontab(run)
        pristine = strip_block(current)
    except (CrontabError, ValueError) as exc:
        err(f"STOP: could not read the current crontab: {exc}")
        return 1

    jobs = build_jobs(venv_py, logs_dir, (now or now_et()).date(), local_tz)
    if pristine.strip() and not backup_path.exists():
        backup_path.write_text(pristine, encoding="utf-8")
    logs_dir.mkdir(parents=True, exist_ok=True)  # cron's shell redirect needs it to exist

    try:
        write_crontab(run, apply_block(current, jobs))
        installed = parse_jobs(read_crontab(run))
    except CrontabError as exc:
        err(f"FAILED to install the crontab: {exc}")
        return 1
    if list(installed) != [job.name for job in jobs]:
        err("Could not verify the installed crontab (jobs missing after writing).")
        return 1

    for job in jobs:
        out(f"OK    {job.name:<18} {job.schedule:<16} ({job.et_time} ET)")
    out("\nNOTE: times were converted using today's daylight-saving rules. Re-run this "
        "setup after the US clocks change (March and November) or when your own do.")
    out("NOTE: there is no keep-awake job on Linux; stop the machine from suspending "
        "yourself if it is a laptop. Make sure the cron service is running. Output goes "
        "to logs/cron.log.")
    out(f"SCHEDULED: {len(jobs)} cron jobs installed. The bot will fire on its own starting "
        "next market open. Watch Telegram.")
    return 0


def cleanup_cron(
    *,
    run: Callable = subprocess.run,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    try:
        current = read_crontab(run)
        jobs = parse_jobs(current)
        if not jobs:
            out("Nothing to clean.")
            return 0
        write_crontab(run, strip_block(current))
    except (CrontabError, ValueError) as exc:
        err(f"FAILED: {exc}")
        return 1
    out(f"CLEANUP DONE: {len(jobs)} jobs removed.")
    return 0


def set_enabled_cron(
    enabled: bool,
    requested: Sequence[str] | None = None,
    *,
    run: Callable = subprocess.run,
    out: Callable = print,
    err: Callable = lambda m: print(m, file=sys.stderr),
) -> int:
    """Enable/disable jobs, then read the crontab back to verify. 2 = unknown name."""
    try:
        current = read_crontab(run)
        existing = parse_jobs(current)
    except (CrontabError, ValueError) as exc:
        err(f"FAILED: {exc}")
        return 1
    if not existing:
        out("No HT_* tasks registered.")
        return 0
    try:
        targets = resolve_targets(requested, list(existing))
    except UnknownTask as exc:
        err(str(exc))
        return 2

    updated = set_jobs_enabled(current, targets, enabled)
    try:
        if updated != current:
            write_crontab(run, updated)
        final = parse_jobs(read_crontab(run))
    except CrontabError as exc:
        err(f"FAILED to update the crontab: {exc}")
        return 1

    failed = False
    for name in targets:
        out(f"{name:<18} {'Ready' if final.get(name) else 'Disabled'}")
        if final.get(name) is not enabled:
            err(f"{name} is not {'enabled' if enabled else 'disabled'} after the update")
            failed = True
    return 1 if failed else 0


def status_cron(*, run: Callable = subprocess.run, out: Callable = print) -> int:
    try:
        states = parse_jobs(read_crontab(run))
    except (CrontabError, ValueError) as exc:
        out(f"Could not read the crontab: {exc}")
        return 1
    if not states:
        out("No HT_* tasks registered.")
        return 0
    for name, on in states.items():
        out(f"{name:<18} {'Ready' if on else 'Disabled':<9} {'enabled' if on else 'DISABLED'}")
    out(f"{sum(states.values())} of {len(states)} tasks enabled.")
    return 0


def setup_main() -> int:
    return setup_cron()


def cleanup_main() -> int:
    return cleanup_cron()


def status_main() -> int:
    return status_cron()


def disable_main(argv: Sequence[str] | None = None) -> int:
    return set_enabled_cron(False, parse_task_args("Disable scheduled bot jobs", argv))


def enable_main(argv: Sequence[str] | None = None) -> int:
    return set_enabled_cron(True, parse_task_args("Enable scheduled bot jobs", argv))
