"""The eleven Task Scheduler entries and the schtasks commands that create them."""
import re
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from pathlib import Path

from trading_bot.timeutil import ET

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
MAX_TR_LENGTH = 261  # schtasks rejects a /tr command longer than this
CYCLE_MINUTES = 5
PREFILTER_TIMES_ET = ["09:55", "10:25", "10:55", "11:25", "11:55", "12:25", "12:55"]
KEEP_AWAKE_COMMAND = "powercfg /change standby-timeout-ac 0"


@dataclass(frozen=True)
class TaskSpec:
    name: str
    et_time: str  # HH:MM in US Eastern
    kind: str  # "weekly" (Mon-Fri) or "minute" (repeating every few minutes)
    module: str | None = None  # python -m <module>
    raw_command: str | None = None  # a command run as-is


def build_tasks() -> list[TaskSpec]:
    prefilters = [
        TaskSpec(f"HT_Prefilter_{i:02d}", t, "weekly", "trading_bot.scanner.prefilter")
        for i, t in enumerate(PREFILTER_TIMES_ET, start=1)
    ]
    return [
        TaskSpec("HT_LogRotate", "09:25", "weekly", "trading_bot.maintenance.rotation"),
        TaskSpec("HT_KeepAwake", "09:30", "weekly", raw_command=KEEP_AWAKE_COMMAND),
        *prefilters,
        TaskSpec("HT_Cycle", "10:00", "minute", "trading_bot.cycle.cli"),
        TaskSpec("HT_Dashboard", "16:05", "weekly", "trading_bot.reporting.performance"),
    ]


@dataclass(frozen=True)
class LocalSlot:
    time: str  # HH:MM, machine-local
    day_shift: int  # local calendar day minus the Eastern day (0 or +1 in practice)
    date: date  # the local date of this slot


def to_local(et_time: str, on: date, local_tz: tzinfo | None = None) -> LocalSlot:
    """Convert an Eastern wall-clock time on `on` to the machine's local time.

    `local_tz=None` means the system timezone. DST of the given date is respected,
    so the result is only valid until either zone changes its clocks.
    """
    hour, minute = (int(part) for part in et_time.split(":"))
    local = datetime(on.year, on.month, on.day, hour, minute, tzinfo=ET).astimezone(local_tz)
    return LocalSlot(f"{local:%H:%M}", (local.date() - on).days, local.date())


def weekdays_for(day_shift: int) -> str:
    """Mon-Fri, moved by the number of days the local clock is ahead."""
    return ",".join(WEEKDAYS[(i + day_shift) % 7] for i in range(5))


def format_date(pattern: str, day: date) -> str:
    """Render `day` in a .NET short-date pattern such as M/d/yyyy or dd/MM/yyyy."""
    values = {
        "yyyy": f"{day.year:04d}", "yy": f"{day.year % 100:02d}",
        "MM": f"{day.month:02d}", "M": str(day.month),
        "dd": f"{day.day:02d}", "d": str(day.day),
    }
    return re.sub(r"yyyy|yy|MM|M|dd|d", lambda m: values[m.group()], pattern)


def task_command(spec: TaskSpec, venv_python: Path) -> str:
    if spec.raw_command:
        return spec.raw_command
    return f'"{venv_python}" -m {spec.module}'


def build_schtasks_args(
    spec: TaskSpec,
    venv_python: Path,
    on: date,
    date_pattern: str,
    local_tz: tzinfo | None = None,
) -> list[str]:
    """Arguments for `schtasks /create`. No /RL and no /RU: user context only."""
    command = task_command(spec, venv_python)
    if len(command) > MAX_TR_LENGTH:
        raise ValueError(f"{spec.name}: command is {len(command)} chars; schtasks allows {MAX_TR_LENGTH}")
    slot = to_local(spec.et_time, on, local_tz)
    args = ["schtasks", "/create", "/tn", spec.name, "/tr", command]
    if spec.kind == "minute":
        args += ["/sc", "MINUTE", "/mo", str(CYCLE_MINUTES),
                 "/sd", format_date(date_pattern, slot.date), "/st", slot.time]
    else:
        args += ["/sc", "WEEKLY", "/d", weekdays_for(slot.day_shift), "/st", slot.time]
    return args + ["/f"]
