from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_bot.scheduling.tasks import (
    build_schtasks_args,
    build_tasks,
    format_date,
    task_command,
    to_local,
    weekdays_for,
)

PY = Path("C:/bots/trading bot/.venv/Scripts/python.exe")  # note the space
OCT = date(2026, 10, 8)    # US on daylight time (EDT)
DEC = date(2026, 12, 8)    # US on standard time (EST)
MAR = date(2026, 3, 20)    # US already on daylight time, Europe not yet
NY, LA, TOKYO, LONDON = (ZoneInfo(z) for z in
                         ("America/New_York", "America/Los_Angeles", "Asia/Tokyo", "Europe/London"))
PANAMA = ZoneInfo("America/Panama")  # UTC-5 all year, like this machine


class TestTaskList:
    def test_eleven_tasks_with_the_documented_names(self):
        names = [t.name for t in build_tasks()]
        assert names == (
            ["HT_LogRotate", "HT_KeepAwake"]
            + [f"HT_Prefilter_{i:02d}" for i in range(1, 8)]
            + ["HT_Cycle", "HT_Dashboard"]
        )

    def test_times_in_eastern(self):
        times = {t.name: t.et_time for t in build_tasks()}
        assert times["HT_LogRotate"] == "09:25" and times["HT_KeepAwake"] == "09:30"
        assert times["HT_Cycle"] == "10:00" and times["HT_Dashboard"] == "16:05"
        assert [times[f"HT_Prefilter_{i:02d}"] for i in range(1, 8)] == [
            "09:55", "10:25", "10:55", "11:25", "11:55", "12:25", "12:55"]

    def test_cycle_is_the_only_minute_task_and_keep_awake_the_only_raw_one(self):
        tasks = {t.name: t for t in build_tasks()}
        assert [n for n, t in tasks.items() if t.kind == "minute"] == ["HT_Cycle"]
        assert [n for n, t in tasks.items() if t.raw_command] == ["HT_KeepAwake"]
        assert tasks["HT_KeepAwake"].raw_command == "powercfg /change standby-timeout-ac 0"

    def test_each_task_runs_the_matching_module(self):
        modules = {t.name: t.module for t in build_tasks()}
        assert modules["HT_LogRotate"] == "trading_bot.maintenance.rotation"
        assert modules["HT_Cycle"] == "trading_bot.cycle.cli"
        assert modules["HT_Dashboard"] == "trading_bot.reporting.performance"
        assert modules["HT_Prefilter_03"] == "trading_bot.scanner.prefilter"


class TestToLocal:
    @pytest.mark.parametrize("tz, on, et_time, expected", [
        (NY, OCT, "09:30", "09:30"),
        (LA, OCT, "09:30", "06:30"),
        (LONDON, OCT, "09:30", "14:30"),      # BST
        (LONDON, DEC, "09:30", "14:30"),      # GMT: ET is also 5h behind -> same
        (LONDON, MAR, "09:30", "13:30"),      # US on EDT, UK still on GMT
        (PANAMA, OCT, "09:30", "08:30"),      # fixed UTC-5 vs EDT
        (PANAMA, DEC, "09:30", "09:30"),      # fixed UTC-5 vs EST
    ])
    def test_time_conversion_follows_the_dst_of_that_date(self, tz, on, et_time, expected):
        assert to_local(et_time, on, tz).time == expected

    def test_same_zone_has_no_day_shift(self):
        slot = to_local("16:05", OCT, NY)
        assert slot.day_shift == 0 and slot.date == OCT

    def test_zone_far_east_rolls_into_the_next_day(self):
        slot = to_local("16:05", OCT, TOKYO)  # 05:05 JST the next day
        assert (slot.time, slot.day_shift, slot.date) == ("05:05", 1, date(2026, 10, 9))

    def test_zone_far_east_same_day_for_morning_tasks(self):
        slot = to_local("09:30", OCT, TOKYO)
        assert (slot.time, slot.day_shift) == ("22:30", 0)

    def test_default_uses_the_machine_timezone_without_error(self):
        assert to_local("09:30", OCT).time[2] == ":"


class TestWeekdays:
    def test_no_shift(self):
        assert weekdays_for(0) == "MON,TUE,WED,THU,FRI"

    def test_shift_forward_when_local_day_is_later(self):
        assert weekdays_for(1) == "TUE,WED,THU,FRI,SAT"

    def test_shift_backward(self):
        assert weekdays_for(-1) == "SUN,MON,TUE,WED,THU"


class TestFormatDate:
    @pytest.mark.parametrize("pattern, expected", [
        ("M/d/yyyy", "10/8/2026"),
        ("MM/dd/yyyy", "10/08/2026"),
        ("dd/MM/yyyy", "08/10/2026"),
        ("yyyy/MM/dd", "2026/10/08"),
        ("yyyy-MM-dd", "2026-10-08"),
        ("d.M.yyyy", "8.10.2026"),
        ("dd.MM.yy", "08.10.26"),
    ])
    def test_matches_the_locale_pattern(self, pattern, expected):
        assert format_date(pattern, OCT) == expected


class TestCommands:
    def test_python_task_command_quotes_a_path_with_spaces(self):
        spec = next(t for t in build_tasks() if t.name == "HT_Cycle")
        assert task_command(spec, PY) == f'"{PY}" -m trading_bot.cycle.cli'

    def test_raw_command_is_used_as_is(self):
        spec = next(t for t in build_tasks() if t.name == "HT_KeepAwake")
        assert task_command(spec, PY) == "powercfg /change standby-timeout-ac 0"

    def test_weekly_task(self):
        spec = next(t for t in build_tasks() if t.name == "HT_LogRotate")
        args = build_schtasks_args(spec, PY, OCT, "MM/dd/yyyy", LA)
        assert args == [
            "schtasks", "/create", "/tn", "HT_LogRotate",
            "/tr", f'"{PY}" -m trading_bot.maintenance.rotation',
            "/sc", "WEEKLY", "/d", "MON,TUE,WED,THU,FRI", "/st", "06:25", "/f",
        ]

    def test_minute_task_has_interval_start_date_and_time(self):
        spec = next(t for t in build_tasks() if t.name == "HT_Cycle")
        args = build_schtasks_args(spec, PY, OCT, "dd/MM/yyyy", LA)
        assert args == [
            "schtasks", "/create", "/tn", "HT_Cycle",
            "/tr", f'"{PY}" -m trading_bot.cycle.cli',
            "/sc", "MINUTE", "/mo", "5", "/sd", "08/10/2026", "/st", "07:00", "/f",
        ]

    def test_start_date_is_the_local_date_of_the_converted_start(self):
        spec = next(t for t in build_tasks() if t.name == "HT_Cycle")
        args = build_schtasks_args(spec, PY, OCT, "yyyy/MM/dd", TOKYO)  # 10:00 ET = 23:00 JST, same day
        assert args[args.index("/sd") + 1] == "2026/10/08"

    def test_weekdays_follow_the_local_day_shift(self):
        spec = next(t for t in build_tasks() if t.name == "HT_Dashboard")  # 16:05 ET
        args = build_schtasks_args(spec, PY, OCT, "MM/dd/yyyy", TOKYO)
        assert args[args.index("/d") + 1] == "TUE,WED,THU,FRI,SAT"
        assert args[args.index("/st") + 1] == "05:05"

    def test_force_overwrite_and_no_elevation_or_system_account(self):
        for spec in build_tasks():
            args = build_schtasks_args(spec, PY, OCT, "MM/dd/yyyy", LA)
            assert args[-1] == "/f"
            assert not {"/rl", "/ru", "highest", "system"} & {a.lower() for a in args}

    def test_every_task_builds_for_every_zone(self):
        for tz in (NY, LA, TOKYO, LONDON, PANAMA):
            assert len([build_schtasks_args(s, PY, OCT, "M/d/yyyy", tz) for s in build_tasks()]) == 11

    def test_overlong_command_is_rejected_because_schtasks_caps_it_at_261(self):
        spec = next(t for t in build_tasks() if t.name == "HT_Cycle")
        with pytest.raises(ValueError, match="261"):
            build_schtasks_args(spec, Path("C:/" + "x" * 300 + "/python.exe"), OCT, "M/d/yyyy", NY)
