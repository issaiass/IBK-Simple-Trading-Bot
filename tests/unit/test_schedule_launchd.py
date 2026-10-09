import plistlib
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_bot.scheduling import cleanup, cron, launchd, setup, toggle
from trading_bot.scheduling.launchd import build_jobs, parse_disabled
from trading_bot.timeutil import ET

PY = Path("/Users/me/trading bot/.venv/bin/python")  # note the space
LOGS = Path("/Users/me/trading bot/logs")
OCT = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 13, 0, tzinfo=ET)
LA, TOKYO = ZoneInfo("America/Los_Angeles"), ZoneInfo("Asia/Tokyo")
UID = 501
JOB_NAMES = (["HT_LogRotate"] + [f"HT_Prefilter_{i:02d}" for i in range(1, 8)]
             + ["HT_Cycle", "HT_Dashboard"])


def jobs(tz=LA):
    return build_jobs(PY, LOGS, OCT, tz)


def job(name, tz=LA):
    return next(j for j in jobs(tz) if j.name == name)


class TestBuildJobs:
    def test_ten_jobs_keep_awake_is_windows_only(self):
        assert [j.name for j in jobs()] == JOB_NAMES

    def test_labels_are_namespaced_and_match_the_plist(self):
        for j in jobs():
            assert j.label == f"com.tradingbot.{j.name}" and j.plist["Label"] == j.label

    def test_runs_the_module_with_the_venv_python(self):
        assert job("HT_Cycle").plist["ProgramArguments"] == [str(PY), "-m", "trading_bot.cycle.cli"]
        assert job("HT_Dashboard").plist["ProgramArguments"][2] == "trading_bot.reporting.performance"

    def test_the_cycle_repeats_every_five_minutes_all_day(self):
        plist = job("HT_Cycle").plist
        assert plist["StartInterval"] == 300 and "StartCalendarInterval" not in plist

    def test_weekly_jobs_fire_monday_to_friday_at_local_time(self):
        slots = job("HT_LogRotate").plist["StartCalendarInterval"]  # 09:25 ET = 06:25 in LA
        assert slots == [{"Hour": 6, "Minute": 25, "Weekday": d} for d in (1, 2, 3, 4, 5)]

    def test_a_zone_ahead_of_new_york_shifts_the_weekdays(self):
        slots = job("HT_Dashboard", TOKYO).plist["StartCalendarInterval"]  # 05:05 the next day
        assert [s["Weekday"] for s in slots] == [2, 3, 4, 5, 6]
        assert slots[0]["Hour"] == 5 and slots[0]["Minute"] == 5

    def test_weekdays_stay_within_launchds_zero_to_six_range(self):
        slots = job("HT_Dashboard", ZoneInfo("Pacific/Honolulu")).plist["StartCalendarInterval"]
        assert slots[0]["Weekday"] in (1, 2)  # same day; never negative
        assert all(0 <= s["Weekday"] <= 6 for s in slots)

    def test_output_goes_to_the_launchd_log(self):
        plist = job("HT_Cycle").plist
        expected = str(LOGS / "launchd.log")
        assert plist["StandardOutPath"] == plist["StandardErrorPath"] == expected

    def test_working_directory_is_the_project_root(self):
        assert job("HT_Cycle").plist["WorkingDirectory"] == str(LOGS.parent)

    def test_plists_serialise_to_valid_xml(self):
        data = launchd.plist_bytes(job("HT_Cycle"))
        assert plistlib.loads(data)["Label"] == "com.tradingbot.HT_Cycle"


class TestParseDisabled:
    OUTPUT = '''disabled services = {
\t"com.apple.thing" => disabled
\t"com.tradingbot.HT_Cycle" => disabled
\t"com.tradingbot.HT_Dashboard" => enabled
\t"com.tradingbot.HT_LogRotate" => true
\t"com.other.app" => false
}'''

    def test_collects_only_disabled_labels(self):
        assert parse_disabled(self.OUTPUT) == {
            "com.apple.thing", "com.tradingbot.HT_Cycle", "com.tradingbot.HT_LogRotate"}

    def test_empty_output(self):
        assert parse_disabled("") == set()


class FakeLaunchctl:
    """launchctl behind subprocess.run: a set of loaded labels and a set of disabled ones."""

    def __init__(self, bootstrap_rc=0):
        self.loaded, self.disabled, self.calls, self.bootstrap_rc = set(), set(), [], bootstrap_rc

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        verb, rest = args[1], args[2:]
        done = lambda rc=0, out="", err="": subprocess.CompletedProcess(args, rc, stdout=out, stderr=err)
        if verb == "bootstrap":
            label = plistlib.loads(Path(rest[1]).read_bytes())["Label"]
            if self.bootstrap_rc:
                return done(self.bootstrap_rc, err="Bootstrap failed: 5: Input/output error")
            if label in self.loaded:
                return done(5, err="already loaded")
            self.loaded.add(label)
            return done()
        if verb == "bootout":
            label = rest[0].rsplit("/", 1)[1]
            if label not in self.loaded:
                return done(3, err="No such process")
            self.loaded.discard(label)
            return done()
        if verb in ("enable", "disable"):
            label = rest[0].rsplit("/", 1)[1]
            (self.disabled.discard if verb == "enable" else self.disabled.add)(label)
            return done()
        if verb == "print-disabled":
            body = "".join(f'\t"{l}" => disabled\n' for l in sorted(self.disabled))
            return done(out="disabled services = {\n" + body + "}\n")
        if verb == "print":
            return done(0 if rest[0].rsplit("/", 1)[1] in self.loaded else 113)
        raise AssertionError(f"unexpected command {args}")

    def verbs(self):
        return [c[1] for c in self.calls]


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
def agents(tmp_path):
    return tmp_path / "LaunchAgents"


def do_setup(launchctl, venv, agents, which=lambda name: "/bin/launchctl"):
    out, err = Out(), Out()
    code = launchd.setup_launchd(
        run=launchctl, which=which, venv_py=venv, logs_dir=venv.parents[2] / "logs",
        agents_dir=agents, uid=UID, now=NOW, local_tz=LA, out=out, err=err)
    return code, out, err


class TestSetup:
    def test_writes_and_loads_ten_agents(self, venv, agents):
        ctl = FakeLaunchctl()
        code, out, _ = do_setup(ctl, venv, agents)
        assert code == 0
        assert len(list(agents.glob("com.tradingbot.HT_*.plist"))) == 10
        assert len(ctl.loaded) == 10 and "SCHEDULED: 10" in out.text

    def test_rerun_replaces_instead_of_failing_on_already_loaded(self, venv, agents):
        ctl = FakeLaunchctl()
        do_setup(ctl, venv, agents)
        code, _, err = do_setup(ctl, venv, agents)
        assert code == 0 and err.lines == [] and len(ctl.loaded) == 10

    def test_a_bootstrap_failure_is_reported_and_fails_the_run(self, venv, agents):
        code, _, err = do_setup(FakeLaunchctl(bootstrap_rc=5), venv, agents)
        assert code == 1 and "FAILED" in err.text

    def test_missing_virtualenv_stops_before_writing_anything(self, tmp_path, agents):
        code, _, err = do_setup(FakeLaunchctl(), tmp_path / "nope" / "python", agents)
        assert code == 1 and "uv sync" in err.text and not agents.exists()

    def test_missing_launchctl_stops(self, venv, agents):
        code, _, err = do_setup(FakeLaunchctl(), venv, agents, which=lambda name: None)
        assert code == 1 and "launchctl" in err.text

    def test_a_previously_disabled_job_is_enabled_again_by_setup(self, venv, agents):
        ctl = FakeLaunchctl()
        ctl.disabled.add("com.tradingbot.HT_Cycle")
        do_setup(ctl, venv, agents)
        assert "com.tradingbot.HT_Cycle" in ctl.loaded and not ctl.disabled

    def test_says_keep_awake_is_not_included_and_to_rerun_after_dst(self, venv, agents):
        _, out, _ = do_setup(FakeLaunchctl(), venv, agents)
        assert "daylight-saving" in out.text and "sleep" in out.text.lower()


def installed(venv, agents):
    ctl = FakeLaunchctl()
    do_setup(ctl, venv, agents)
    ctl.calls.clear()
    return ctl


class TestCleanup:
    def test_unloads_and_removes_every_agent(self, venv, agents):
        ctl = installed(venv, agents)
        out, err = Out(), Out()
        code = launchd.cleanup_launchd(run=ctl, agents_dir=agents, uid=UID, out=out, err=err)
        assert code == 0 and not ctl.loaded and not list(agents.glob("*.plist"))
        assert "10" in out.text

    def test_leaves_other_launch_agents_alone(self, venv, agents):
        ctl = installed(venv, agents)
        other = agents / "com.someone.else.plist"
        other.write_bytes(plistlib.dumps({"Label": "com.someone.else"}))
        launchd.cleanup_launchd(run=ctl, agents_dir=agents, uid=UID, out=Out(), err=Out())
        assert other.exists()

    def test_nothing_to_clean(self, agents):
        out = Out()
        assert launchd.cleanup_launchd(run=FakeLaunchctl(), agents_dir=agents, uid=UID,
                                       out=out, err=Out()) == 0
        assert "Nothing to clean" in out.text


def toggle_jobs(ctl, agents, enabled, names=None):
    out, err = Out(), Out()
    code = launchd.set_enabled_launchd(enabled, names, run=ctl, agents_dir=agents, uid=UID,
                                       out=out, err=err)
    return code, out, err


class TestToggle:
    def test_disable_unloads_and_marks_the_named_job_disabled(self, venv, agents):
        ctl = installed(venv, agents)
        code, out, _ = toggle_jobs(ctl, agents, False, ["cycle"])
        assert code == 0
        assert "com.tradingbot.HT_Cycle" not in ctl.loaded and len(ctl.loaded) == 9
        assert "com.tradingbot.HT_Cycle" in ctl.disabled
        assert "HT_Cycle" in out.text and "Disabled" in out.text

    def test_enable_restores_the_job(self, venv, agents):
        ctl = installed(venv, agents)
        toggle_jobs(ctl, agents, False, ["cycle"])
        code, _, _ = toggle_jobs(ctl, agents, True, ["cycle"])
        assert code == 0 and len(ctl.loaded) == 10 and not ctl.disabled

    def test_no_name_means_all_jobs(self, venv, agents):
        ctl = installed(venv, agents)
        toggle_jobs(ctl, agents, False)
        assert not ctl.loaded and len(ctl.disabled) == 10

    def test_disabling_twice_is_fine(self, venv, agents):
        ctl = installed(venv, agents)
        toggle_jobs(ctl, agents, False, ["cycle"])
        assert toggle_jobs(ctl, agents, False, ["cycle"])[0] == 0

    def test_unknown_name_changes_nothing(self, venv, agents):
        ctl = installed(venv, agents)
        code, _, err = toggle_jobs(ctl, agents, False, ["nope"])
        assert code == 2 and "no such task" in err.text and len(ctl.loaded) == 10

    def test_nothing_installed(self, agents):
        code, out, _ = toggle_jobs(FakeLaunchctl(), agents, False)
        assert code == 0 and "No HT_* tasks registered" in out.text

    def test_status_lists_state_and_counts(self, venv, agents):
        ctl = installed(venv, agents)
        toggle_jobs(ctl, agents, False, ["cycle"])
        out = Out()
        assert launchd.status_launchd(run=ctl, agents_dir=agents, uid=UID, out=out) == 0
        assert "9 of 10 tasks enabled" in out.text and "DISABLED" in out.text

    def test_states_feed_the_doctor(self, venv, agents):
        ctl = installed(venv, agents)
        toggle_jobs(ctl, agents, False, ["cycle"])
        states = launchd.launchd_states(run=ctl, agents_dir=agents, uid=UID)
        assert states["HT_Cycle"] == "Disabled" and states["HT_Dashboard"] == "Ready"


class TestPlatformDispatch:
    def test_macos_uses_launchd_while_linux_keeps_cron(self, monkeypatch):
        for name, value in (("setup_main", 31), ("cleanup_main", 32), ("status_main", 33),
                            ("disable_main", 34), ("enable_main", 35)):
            monkeypatch.setattr(launchd, name, lambda *a, _v=value: _v)
        monkeypatch.setattr(sys, "platform", "darwin")
        assert (setup.main(), cleanup.main(), toggle.status_main()) == (31, 32, 33)
        assert (toggle.disable_main([]), toggle.enable_main([])) == (34, 35)

        monkeypatch.setattr(cron, "setup_main", lambda: 41)
        monkeypatch.setattr(sys, "platform", "linux")
        assert setup.main() == 41
