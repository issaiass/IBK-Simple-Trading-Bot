import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_bot.scheduling.cleanup import cleanup_schedule
from trading_bot.scheduling.powercfg import parse_ac_standby_minutes
from trading_bot.scheduling.setup import parse_task_rows, setup_schedule
from trading_bot.timeutil import ET

NOW = datetime(2026, 10, 8, 13, 0, tzinfo=ET)
LA = ZoneInfo("America/Los_Angeles")

# real powercfg /query output, English and Spanish: AC line first, then DC
POWERCFG_EN = """\
    Minimum Possible Setting: 0x00000000
    Maximum Possible Setting: 0xffffffff
    Current AC Power Setting Index: 0x00000708
    Current DC Power Setting Index: 0x00000258
"""
POWERCFG_ES = """\
      Mínima configuración posible: 0x00000000
      Máxima configuración posible: 0xffffffff
    Índice de configuración de corriente alterna actual: 0x00000000
    Índice de configuración de corriente continua actual: 0x00000000
"""


def csv_for(*names):
    return "".join(f'"\\{n}","10/9/2026 8:30:00","Ready"\n' for n in names)


class FakeRun:
    """Stands in for subprocess.run, dispatching on the command."""

    def __init__(self, date_pattern="MM/dd/yyyy", powercfg=POWERCFG_ES, tasks=(), fail=()):
        self.calls, self.date_pattern, self.powercfg = [], date_pattern, powercfg
        self.tasks, self.fail = list(tasks), set(fail)

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        head = args[0].lower()
        out, code, err = "", 0, ""
        if head == "powershell":
            out = self.date_pattern + "\r\n"
        elif head == "powercfg" and args[1] == "/query":
            out = self.powercfg
        elif head == "schtasks" and args[1] == "/create":
            if args[3] in self.fail:
                code, err = 1, f"ERROR: invalid for {args[3]}"
            elif args[3] not in self.tasks:  # /f overwrites: same name, same single task
                self.tasks.append(args[3])
        elif head == "schtasks" and args[1] == "/query":
            out = csv_for(*self.tasks, "Microsoft\\Other")
        elif head == "schtasks" and args[1] == "/delete":
            name = args[3].lstrip("\\")
            if name in self.fail:
                code, err = 1, "ERROR: access denied"
            else:
                self.tasks = [t for t in self.tasks if t != name]
        return subprocess.CompletedProcess(args, code, stdout=out, stderr=err)

    def commands(self, *prefix):
        return [c for c in self.calls if [x.lower() for x in c[: len(prefix)]] == list(prefix)]


@pytest.fixture
def venv(tmp_path):
    py = tmp_path / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


@pytest.fixture
def state(tmp_path):
    return tmp_path / "schedule_state.json"


class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, message=""):
        self.lines.append(str(message))

    @property
    def text(self):
        return "\n".join(self.lines)


def do_setup(run, venv, state, which=lambda name: "C:/Windows/system32/schtasks.exe"):
    out, err = Out(), Out()
    code = setup_schedule(run=run, which=which, venv_py=venv, state_path=state,
                          now=NOW, local_tz=LA, out=out, err=err)
    return code, out, err


class TestPowercfgParsing:
    def test_english_ac_value_in_minutes(self):
        assert parse_ac_standby_minutes(POWERCFG_EN) == 30

    def test_spanish_output_gives_zero(self):
        assert parse_ac_standby_minutes(POWERCFG_ES) == 0

    def test_garbage_gives_none(self):
        assert parse_ac_standby_minutes("nothing useful") is None


class TestRealSubprocessOutput:
    """Windows tools print in the OEM code page; a plain text=True read would crash."""

    UNDECODABLE = "import sys; sys.stdout.buffer.write(b'\\x8d\\xa2 0x00000708 0x00000258\\n')"

    def test_undecodable_bytes_do_not_lose_the_output(self):
        from trading_bot.scheduling.setup import run_command

        result = run_command(subprocess.run, [sys.executable, "-c", self.UNDECODABLE])
        assert result.stdout is not None
        assert parse_ac_standby_minutes(result.stdout) == 30

    def test_parser_tolerates_missing_output(self):
        assert parse_ac_standby_minutes(None) is None
        assert parse_ac_standby_minutes("") is None


class TestParseTaskRows:
    def test_extracts_name_next_run_and_status(self):
        rows = parse_task_rows(csv_for("HT_Cycle", "HT_Dashboard"))
        assert rows == [("HT_Cycle", "10/9/2026 8:30:00", "Ready"),
                        ("HT_Dashboard", "10/9/2026 8:30:00", "Ready")]

    def test_ignores_other_tasks_and_header_rows(self):
        text = '"TaskName","Next Run Time","Status"\n' + csv_for("Microsoft\\Other", "HT_Cycle")
        assert [r[0] for r in parse_task_rows(text)] == ["HT_Cycle"]


class TestSetup:
    def test_registers_all_eleven_tasks(self, venv, state):
        run = FakeRun()
        code, out, _ = do_setup(run, venv, state)
        assert code == 0 and len(run.commands("schtasks", "/create")) == 11
        assert out.lines[-1].startswith("SCHEDULED: 11 tasks created.")
        assert out.lines[-1].endswith("Watch Telegram.")

    def test_uses_the_machines_date_format_for_the_cycle_start(self, venv, state):
        run = FakeRun(date_pattern="dd/MM/yyyy")
        do_setup(run, venv, state)
        cycle = next(c for c in run.commands("schtasks", "/create") if c[3] == "HT_Cycle")
        assert cycle[cycle.index("/sd") + 1] == "08/10/2026"

    def test_falls_back_to_the_us_date_format_when_detection_fails(self, venv, state):
        run = FakeRun(date_pattern="")
        do_setup(run, venv, state)
        cycle = next(c for c in run.commands("schtasks", "/create") if c[3] == "HT_Cycle")
        assert cycle[cycle.index("/sd") + 1] == "10/8/2026"

    def test_a_failing_task_is_reported_and_the_rest_still_register(self, venv, state):
        run = FakeRun(fail={"HT_Prefilter_03"})
        code, out, err = do_setup(run, venv, state)
        assert code == 1 and len(run.commands("schtasks", "/create")) == 11
        assert "HT_Prefilter_03" in err.text and "invalid" in err.text
        assert "10 of 11" in out.lines[-1] and "SCHEDULED: 11" not in out.text

    def test_prints_a_table_of_the_registered_tasks(self, venv, state):
        _, out, _ = do_setup(FakeRun(), venv, state)
        assert "HT_Cycle" in out.text and "Ready" in out.text
        assert "Microsoft" not in out.text

    def test_missing_virtualenv_stops_before_registering_anything(self, tmp_path, state):
        run = FakeRun()
        code, _, err = do_setup(run, tmp_path / "nope" / "python.exe", state)
        assert code == 1 and "venv" in err.text.lower() and run.commands("schtasks", "/create") == []

    def test_missing_schtasks_stops_before_registering_anything(self, venv, state):
        run = FakeRun()
        code, _, err = do_setup(run, venv, state, which=lambda name: None)
        assert code == 1 and "schtasks" in err.text and run.calls == []

    def test_records_the_original_standby_timeout(self, venv, state):
        do_setup(FakeRun(powercfg=POWERCFG_EN), venv, state)
        assert json.loads(state.read_text())["original_standby_timeout_ac_minutes"] == 30

    def test_rerun_never_overwrites_the_recorded_original(self, venv, state):
        do_setup(FakeRun(powercfg=POWERCFG_EN), venv, state)
        do_setup(FakeRun(powercfg=POWERCFG_ES), venv, state)  # now reads 0 (keep-awake ran)
        assert json.loads(state.read_text())["original_standby_timeout_ac_minutes"] == 30

    def test_setup_itself_never_changes_power_settings(self, venv, state):
        run = FakeRun()
        do_setup(run, venv, state)
        assert run.commands("powercfg", "/change") == []

    def test_is_idempotent_all_tasks_are_force_overwritten(self, venv, state):
        run = FakeRun()
        do_setup(run, venv, state)
        do_setup(run, venv, state)
        creates = run.commands("schtasks", "/create")
        assert len(creates) == 22 and all(c[-1] == "/f" for c in creates)
        assert len(run.tasks) == 11  # the second run overwrote, it did not add

    def test_warns_to_rerun_after_daylight_saving_changes(self, venv, state):
        _, out, _ = do_setup(FakeRun(), venv, state)
        assert "daylight" in out.text.lower()


class TestCleanup:
    def do_cleanup(self, run, state):
        out, err = Out(), Out()
        code = cleanup_schedule(run=run, state_path=state, out=out, err=err)
        return code, out, err

    def test_deletes_every_ht_task_and_nothing_else(self, state):
        run = FakeRun(tasks=["HT_Cycle", "HT_LogRotate", "OtherApp"])
        code, out, _ = self.do_cleanup(run, state)
        deleted = [c[3].lstrip("\\") for c in run.commands("schtasks", "/delete")]
        assert code == 0 and sorted(deleted) == ["HT_Cycle", "HT_LogRotate"]
        assert all(c[-1] == "/f" for c in run.commands("schtasks", "/delete"))
        assert out.lines[-1] == "CLEANUP DONE: 2 tasks deleted; default power settings restored."

    def test_restores_the_recorded_original_power_setting(self, state):
        state.write_text(json.dumps({"original_standby_timeout_ac_minutes": 0}))
        run = FakeRun(tasks=["HT_Cycle"])
        self.do_cleanup(run, state)
        assert run.commands("powercfg", "/change") == [["powercfg", "/change", "standby-timeout-ac", "0"]]
        assert not state.exists()

    def test_falls_back_to_30_minutes_when_nothing_was_recorded(self, state):
        run = FakeRun(tasks=["HT_Cycle"])
        self.do_cleanup(run, state)
        assert run.commands("powercfg", "/change") == [["powercfg", "/change", "standby-timeout-ac", "30"]]

    def test_nothing_to_clean(self, state):
        run = FakeRun(tasks=[])
        code, out, _ = self.do_cleanup(run, state)
        assert code == 0 and out.lines[-1] == "Nothing to clean."
        assert run.commands("schtasks", "/delete") == [] and run.commands("powercfg", "/change") == []

    def test_leftover_state_is_still_restored_when_no_tasks_remain(self, state):
        state.write_text(json.dumps({"original_standby_timeout_ac_minutes": 15}))
        run = FakeRun(tasks=[])
        code, out, _ = self.do_cleanup(run, state)
        assert code == 0
        assert run.commands("powercfg", "/change") == [["powercfg", "/change", "standby-timeout-ac", "15"]]
        assert not state.exists()

    def test_a_failed_delete_is_reported_and_the_rest_continue(self, state):
        run = FakeRun(tasks=["HT_Cycle", "HT_Dashboard"], fail={"HT_Cycle"})
        code, out, err = self.do_cleanup(run, state)
        assert code == 1 and "HT_Cycle" in err.text
        assert "1 tasks deleted" in out.lines[-1]

    def test_is_idempotent(self, state):
        run = FakeRun(tasks=["HT_Cycle"])
        self.do_cleanup(run, state)
        code, out, _ = self.do_cleanup(run, state)
        assert code == 0 and out.lines[-1] == "Nothing to clean."
