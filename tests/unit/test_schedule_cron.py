import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_bot.scheduling import cleanup, cron, setup, toggle
from trading_bot.scheduling.cron import (
    BEGIN,
    END,
    apply_block,
    build_jobs,
    dow_field,
    parse_jobs,
    set_jobs_enabled,
    strip_block,
)
from trading_bot.timeutil import ET

PY = Path("/opt/trading bot/.venv/bin/python")  # note the space
LOGS = Path("/opt/trading bot/logs")
OCT = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 13, 0, tzinfo=ET)
LA, TOKYO, NY = (ZoneInfo(z) for z in ("America/Los_Angeles", "Asia/Tokyo", "America/New_York"))
USER_LINES = "MAILTO=me@example.com\n0 3 * * * /usr/bin/backup --all  # my own job\n"
FIELD = re.compile(r"[\d*/,\-]+")

JOB_NAMES = (["HT_LogRotate"] + [f"HT_Prefilter_{i:02d}" for i in range(1, 8)]
             + ["HT_Cycle", "HT_Dashboard"])


def jobs(tz=LA):
    return build_jobs(PY, LOGS, OCT, tz)


class TestDowField:
    @pytest.mark.parametrize("shift, expected", [
        (0, "1-5"), (1, "2-6"), (-1, "0-4"), (2, "0,3,4,5,6"),
    ])
    def test_weekday_range_follows_the_local_day_shift(self, shift, expected):
        assert dow_field(shift) == expected


class TestBuildJobs:
    def test_ten_jobs_keep_awake_is_windows_only(self):
        assert [j.name for j in jobs()] == JOB_NAMES

    def test_every_schedule_is_five_valid_fields(self):
        for tz in (LA, TOKYO, NY):
            for job in jobs(tz):
                fields = job.schedule.split()
                assert len(fields) == 5 and all(FIELD.fullmatch(f) for f in fields), job

    def test_cycle_runs_every_five_minutes_all_day(self):
        cycle = next(j for j in jobs() if j.name == "HT_Cycle")
        assert cycle.schedule == "*/5 * * * *"

    def test_weekly_jobs_use_local_time_converted_from_eastern(self):
        by_name = {j.name: j.schedule for j in jobs(LA)}   # LA is ET minus 3h in October
        assert by_name["HT_LogRotate"] == "25 6 * * 1-5"      # 09:25 ET
        assert by_name["HT_Prefilter_01"] == "55 6 * * 1-5"   # 09:55 ET
        assert by_name["HT_Prefilter_07"] == "55 9 * * 1-5"   # 12:55 ET
        assert by_name["HT_Dashboard"] == "5 13 * * 1-5"      # 16:05 ET

    def test_a_zone_ahead_of_new_york_shifts_the_weekday(self):
        dashboard = next(j for j in jobs(TOKYO) if j.name == "HT_Dashboard")  # 05:05 next day
        assert dashboard.schedule == "5 5 * * 2-6"

    def test_command_runs_the_module_and_appends_to_the_cron_log(self):
        rotate = next(j for j in jobs() if j.name == "HT_LogRotate")
        assert rotate.command == (
            "'/opt/trading bot/.venv/bin/python' -m trading_bot.maintenance.rotation"
            " >> '/opt/trading bot/logs/cron.log' 2>&1"
        )

    def test_each_job_runs_the_matching_module(self):
        modules = {j.name: j.command.split(" -m ")[1].split()[0] for j in jobs()}
        assert modules["HT_Cycle"] == "trading_bot.cycle.cli"
        assert modules["HT_Dashboard"] == "trading_bot.reporting.performance"
        assert modules["HT_Prefilter_04"] == "trading_bot.scanner.prefilter"

    def test_percent_signs_are_escaped_because_cron_treats_them_as_newlines(self):
        job = build_jobs(Path("/opt/100%/python"), LOGS, OCT, LA)[0]
        assert "100\\%" in job.command and "100%/" not in job.command


class TestBlockEditing:
    def block(self, tz=LA):
        return apply_block("", jobs(tz))

    def test_block_is_delimited_and_ends_with_a_newline(self):
        text = self.block()
        lines = text.splitlines()
        assert lines[0] == BEGIN and lines[-1] == END and text.endswith("\n")
        assert len(lines) == 10 + 2

    def test_each_job_line_carries_its_name_as_a_trailing_comment(self):
        lines = self.block().splitlines()[1:-1]
        assert [line.rsplit("# ", 1)[1] for line in lines] == JOB_NAMES

    def test_user_entries_are_preserved(self):
        text = apply_block(USER_LINES, jobs())
        assert text.startswith(USER_LINES) and BEGIN in text

    def test_applying_twice_is_idempotent(self):
        once = apply_block(USER_LINES, jobs())
        assert apply_block(once, jobs()) == once

    def test_reapplying_replaces_stale_jobs(self):
        old = apply_block(USER_LINES, jobs(LA))
        new = apply_block(old, jobs(NY))
        assert new.count(BEGIN) == 1 and "25 9 * * 1-5" in new and "25 6 * * 1-5" not in new

    def test_strip_block_removes_only_the_block(self):
        text = apply_block(USER_LINES, jobs())
        assert strip_block(text) == USER_LINES

    def test_strip_block_on_text_without_a_block_is_unchanged(self):
        assert strip_block(USER_LINES) == USER_LINES and strip_block("") == ""

    def test_parse_jobs_reports_enabled_state(self):
        assert parse_jobs(apply_block(USER_LINES, jobs())) == dict.fromkeys(JOB_NAMES, True)

    def test_parse_jobs_ignores_lines_outside_the_block(self):
        stray = "5 5 * * * /bin/x  # HT_Cycle\n"
        assert parse_jobs(stray) == {}

    def test_disabling_comments_out_only_the_named_jobs(self):
        text = set_jobs_enabled(apply_block(USER_LINES, jobs()), ["HT_Cycle"], False)
        states = parse_jobs(text)
        assert states["HT_Cycle"] is False and sum(states.values()) == 9
        assert "#off# */5 * * * *" in text and text.startswith(USER_LINES)

    def test_disable_and_enable_round_trip_to_the_exact_original(self):
        original = apply_block(USER_LINES, jobs())
        off = set_jobs_enabled(original, ["HT_Cycle", "HT_Dashboard"], False)
        assert set_jobs_enabled(off, ["HT_Cycle", "HT_Dashboard"], True) == original

    def test_toggling_is_idempotent(self):
        text = set_jobs_enabled(apply_block("", jobs()), ["HT_Cycle"], False)
        assert set_jobs_enabled(text, ["HT_Cycle"], False) == text


class FakeCrontab:
    """A user crontab behind the crontab command."""

    def __init__(self, text=None, list_error=None, write_rc=0):
        self.text, self.list_error, self.write_rc = text, list_error, write_rc  # text None = none
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if args == ["crontab", "-l"]:
            if self.list_error:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr=self.list_error)
            if self.text is None:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="no crontab for denys")
            return subprocess.CompletedProcess(args, 0, stdout=self.text, stderr="")
        if args == ["crontab", "-"]:
            if self.write_rc:
                return subprocess.CompletedProcess(args, self.write_rc, stdout="", stderr="bad minute")
            self.text = kwargs["input"]
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args == ["crontab", "-r"]:
            self.text = None
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command {args}")

    def writes(self):
        return [c for c in self.calls if c in (["crontab", "-"], ["crontab", "-r"])]


class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, message=""):
        self.lines.append(str(message))

    @property
    def text(self):
        return "\n".join(self.lines)


@pytest.fixture
def venv(tmp_path):
    py = tmp_path / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


@pytest.fixture
def backup(tmp_path):
    return tmp_path / "schedule_crontab.backup"


def do_setup(crontab, venv, backup, which=lambda name: "/usr/bin/crontab"):
    out, err = Out(), Out()
    code = cron.setup_cron(run=crontab, which=which, venv_py=venv, logs_dir=venv.parents[2] / "logs",
                           backup_path=backup, now=NOW, local_tz=LA, out=out, err=err)
    return code, out, err


class TestSetupCron:
    def test_installs_the_ten_jobs(self, venv, backup):
        crontab = FakeCrontab()
        code, out, _ = do_setup(crontab, venv, backup)
        assert code == 0 and list(parse_jobs(crontab.text)) == JOB_NAMES
        assert out.lines[-1].startswith("SCHEDULED: 10 cron jobs installed.")

    def test_user_crontab_entries_survive(self, venv, backup):
        crontab = FakeCrontab(USER_LINES)
        do_setup(crontab, venv, backup)
        assert crontab.text.startswith(USER_LINES)

    def test_creates_the_logs_directory_cron_redirects_into(self, venv, backup):
        do_setup(FakeCrontab(), venv, backup)
        assert (venv.parents[2] / "logs").is_dir()

    def test_backs_up_the_pristine_crontab_before_writing(self, venv, backup):
        crontab = FakeCrontab(USER_LINES)
        do_setup(crontab, venv, backup)
        assert backup.read_text() == USER_LINES

    def test_rerun_keeps_the_first_pristine_backup(self, venv, backup):
        crontab = FakeCrontab(USER_LINES)
        do_setup(crontab, venv, backup)
        do_setup(crontab, venv, backup)
        assert backup.read_text() == USER_LINES and crontab.text.count(BEGIN) == 1

    def test_is_idempotent(self, venv, backup):
        crontab = FakeCrontab()
        do_setup(crontab, venv, backup)
        first = crontab.text
        do_setup(crontab, venv, backup)
        assert crontab.text == first

    def test_unexpected_crontab_read_error_aborts_without_writing(self, venv, backup):
        crontab = FakeCrontab(list_error="crontab: permission denied")
        code, _, err = do_setup(crontab, venv, backup)
        assert code == 1 and crontab.writes() == [] and "permission denied" in err.text

    def test_rejected_write_is_reported(self, venv, backup):
        code, _, err = do_setup(FakeCrontab(write_rc=1), venv, backup)
        assert code == 1 and "bad minute" in err.text

    def test_verifies_by_reading_the_crontab_back(self, venv, backup):
        class Lossy(FakeCrontab):
            def __call__(self, args, **kw):
                result = super().__call__(args, **kw)
                if args == ["crontab", "-"]:
                    self.text = strip_block(self.text)  # silently dropped
                return result

        code, _, err = do_setup(Lossy(), venv, backup)
        assert code == 1 and "verify" in err.text.lower()

    def test_missing_virtualenv_stops_before_touching_the_crontab(self, tmp_path, backup):
        crontab = FakeCrontab()
        code, _, err = do_setup(crontab, tmp_path / "nope" / "python", backup)
        assert code == 1 and "venv" in err.text.lower() and crontab.calls == []

    def test_missing_crontab_command_stops(self, venv, backup):
        crontab = FakeCrontab()
        code, _, err = do_setup(crontab, venv, backup, which=lambda name: None)
        assert code == 1 and "cron" in err.text.lower() and crontab.calls == []

    def test_says_keep_awake_is_not_included_and_to_rerun_after_dst(self, venv, backup):
        _, out, _ = do_setup(FakeCrontab(), venv, backup)
        assert "keep-awake" in out.text.lower() and "daylight" in out.text.lower()


class TestCleanupCron:
    def run_cleanup(self, crontab):
        out, err = Out(), Out()
        return cron.cleanup_cron(run=crontab, out=out, err=err), out, err

    def test_removes_the_block_and_keeps_user_entries(self):
        crontab = FakeCrontab(apply_block(USER_LINES, jobs()))
        code, out, _ = self.run_cleanup(crontab)
        assert code == 0 and crontab.text == USER_LINES
        assert out.lines[-1] == "CLEANUP DONE: 10 jobs removed."

    def test_removes_the_crontab_entirely_when_nothing_else_is_left(self):
        crontab = FakeCrontab(apply_block("", jobs()))
        self.run_cleanup(crontab)
        assert crontab.text is None and crontab.writes() == [["crontab", "-r"]]

    def test_nothing_to_clean(self):
        for text in (None, USER_LINES):
            crontab = FakeCrontab(text)
            code, out, _ = self.run_cleanup(crontab)
            assert code == 0 and out.lines[-1] == "Nothing to clean." and crontab.writes() == []

    def test_is_idempotent(self):
        crontab = FakeCrontab(apply_block(USER_LINES, jobs()))
        self.run_cleanup(crontab)
        code, out, _ = self.run_cleanup(crontab)
        assert code == 0 and out.lines[-1] == "Nothing to clean."


class TestToggleCron:
    def toggle(self, enabled, crontab, requested=None):
        out, err = Out(), Out()
        return cron.set_enabled_cron(enabled, requested, run=crontab, out=out, err=err), out, err

    def installed(self):
        return FakeCrontab(apply_block(USER_LINES, jobs()))

    def test_disables_only_the_cycle(self):
        crontab = self.installed()
        code, out, _ = self.toggle(False, crontab, ["cycle"])
        states = parse_jobs(crontab.text)
        assert code == 0 and states["HT_Cycle"] is False and sum(states.values()) == 9
        assert "HT_Cycle" in out.text and crontab.text.startswith(USER_LINES)

    def test_enable_restores_the_original_crontab_exactly(self):
        crontab = self.installed()
        original = crontab.text
        self.toggle(False, crontab, ["cycle"])
        self.toggle(True, crontab, ["cycle"])
        assert crontab.text == original

    def test_no_name_means_all_jobs(self):
        crontab = self.installed()
        self.toggle(False, crontab)
        assert not any(parse_jobs(crontab.text).values())

    def test_unknown_name_writes_nothing(self):
        crontab = self.installed()
        code, _, err = self.toggle(False, crontab, ["nope"])
        assert code == 2 and crontab.writes() == [] and "nope" in err.text

    def test_nothing_installed(self):
        code, out, _ = self.toggle(False, FakeCrontab(USER_LINES))
        assert code == 0 and "No HT_* tasks" in out.text

    def test_rejected_write_is_reported(self):
        crontab = self.installed()
        crontab.write_rc = 1
        code, _, err = self.toggle(False, crontab, ["cycle"])
        assert code == 1 and "bad minute" in err.text

    def test_status_lists_state_and_counts(self):
        crontab = self.installed()
        self.toggle(False, crontab, ["cycle"])
        out = Out()
        assert cron.status_cron(run=crontab, out=out) == 0
        assert "HT_Cycle" in out.text and "DISABLED" in out.text
        assert out.lines[-1] == "9 of 10 tasks enabled."


class TestPlatformDispatch:
    """The same console commands pick the Windows or the cron backend."""

    def test_linux_uses_cron(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(cron, "setup_main", lambda: 11)
        monkeypatch.setattr(cron, "cleanup_main", lambda: 12)
        monkeypatch.setattr(cron, "status_main", lambda: 13)
        monkeypatch.setattr(cron, "disable_main", lambda argv=None: 14)
        monkeypatch.setattr(cron, "enable_main", lambda argv=None: 15)
        assert (setup.main(), cleanup.main(), toggle.status_main()) == (11, 12, 13)
        assert (toggle.disable_main([]), toggle.enable_main([])) == (14, 15)

    def test_windows_keeps_using_task_scheduler(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(setup, "setup_schedule", lambda: 21)
        monkeypatch.setattr(cleanup, "cleanup_schedule", lambda: 22)
        monkeypatch.setattr(toggle, "schedule_status", lambda: 23)
        monkeypatch.setattr(toggle, "set_enabled", lambda enabled, requested=None: 24 if not enabled else 25)
        assert (setup.main(), cleanup.main(), toggle.status_main()) == (21, 22, 23)
        assert (toggle.disable_main([]), toggle.enable_main([])) == (24, 25)

    def test_default_venv_python_matches_the_platform(self):
        from trading_bot.config import VENV_PYTHON, venv_python_path

        assert venv_python_path("win32", Path("/p")) == Path("/p/.venv/Scripts/python.exe")
        assert venv_python_path("linux", Path("/p")) == Path("/p/.venv/bin/python")
        assert VENV_PYTHON.name in ("python", "python.exe")
