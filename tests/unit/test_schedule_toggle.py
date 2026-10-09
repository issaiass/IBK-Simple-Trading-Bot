import subprocess

import pytest

from trading_bot.scheduling.toggle import (
    UnknownTask,
    list_tasks,
    resolve_targets,
    schedule_status,
    set_enabled,
)

ALL = ["HT_Cycle", "HT_Dashboard", "HT_LogRotate"]


class FakeRun:
    """Stands in for subprocess.run; /change really flips the fake task state."""

    def __init__(self, states=None, fail_change=()):
        self.states = dict({n: "Ready" for n in ALL} if states is None else states)
        self.fail_change, self.calls = set(fail_change), []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if args[0].lower() == "powershell":
            out = "".join(f"{n},{s}\r\n" for n, s in self.states.items())
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
        assert args[:2] == ["schtasks", "/change"], args
        name, flag = args[3], args[4]
        if name in self.fail_change:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="ERROR: access denied")
        self.states[name] = "Disabled" if flag == "/disable" else "Ready"
        return subprocess.CompletedProcess(args, 0, stdout="SUCCESS", stderr="")

    def changes(self):
        return [c for c in self.calls if c[:2] == ["schtasks", "/change"]]


class Out:
    def __init__(self):
        self.lines = []

    def __call__(self, message=""):
        self.lines.append(str(message))

    @property
    def text(self):
        return "\n".join(self.lines)


def toggle(enabled, run, requested=None):
    out, err = Out(), Out()
    code = set_enabled(enabled, requested, run=run, out=out, err=err)
    return code, out, err


class TestListTasks:
    def test_maps_names_to_states(self):
        run = FakeRun({"HT_Cycle": "Disabled", "HT_Dashboard": "Ready"})
        assert list_tasks(run) == {"HT_Cycle": "Disabled", "HT_Dashboard": "Ready"}

    def test_no_tasks(self):
        assert list_tasks(FakeRun({})) == {}

    def test_queries_only_ht_tasks_through_powershell(self):
        run = FakeRun()
        list_tasks(run)
        assert run.calls[0][0].lower() == "powershell" and "HT_*" in run.calls[0][-1]


class TestResolveTargets:
    def test_none_means_every_task(self):
        assert resolve_targets(None, ALL) == ALL

    @pytest.mark.parametrize("requested", [["HT_Cycle"], ["cycle"], ["CYCLE"], ["ht_cycle"]])
    def test_accepts_the_name_with_or_without_prefix_in_any_case(self, requested):
        assert resolve_targets(requested, ALL) == ["HT_Cycle"]

    def test_unknown_name_is_an_error(self):
        with pytest.raises(UnknownTask, match="nope"):
            resolve_targets(["cycle", "nope"], ALL)


class TestDisable:
    def test_disables_only_the_requested_task(self):
        run = FakeRun()
        code, out, _ = toggle(False, run, ["cycle"])
        assert code == 0
        assert run.changes() == [["schtasks", "/change", "/tn", "HT_Cycle", "/disable"]]
        assert run.states["HT_Cycle"] == "Disabled" and run.states["HT_Dashboard"] == "Ready"
        assert "HT_Cycle" in out.text and "Disabled" in out.text

    def test_without_a_name_disables_everything(self):
        run = FakeRun()
        toggle(False, run)
        assert set(run.states.values()) == {"Disabled"}

    def test_is_idempotent(self):
        run = FakeRun()
        toggle(False, run, ["cycle"])
        code, _, _ = toggle(False, run, ["cycle"])
        assert code == 0 and run.states["HT_Cycle"] == "Disabled"

    def test_verifies_the_final_state_instead_of_trusting_the_exit_code(self):
        class Liar(FakeRun):
            def __call__(self, args, **kw):
                result = super().__call__(args, **kw)
                if args[:2] == ["schtasks", "/change"]:
                    self.states[args[3]] = "Ready"  # claims success, changed nothing
                return result

        code, _, err = toggle(False, Liar(), ["cycle"])
        assert code == 1 and "HT_Cycle" in err.text

    def test_a_failed_change_is_reported_and_the_others_still_change(self):
        run = FakeRun(fail_change={"HT_Cycle"})
        code, _, err = toggle(False, run)
        assert code == 1 and "access denied" in err.text
        assert run.states["HT_Dashboard"] == "Disabled" and run.states["HT_Cycle"] == "Ready"

    def test_unknown_task_changes_nothing(self):
        run = FakeRun()
        code, _, err = toggle(False, run, ["nope"])
        assert code == 2 and run.changes() == [] and "nope" in err.text

    def test_no_registered_tasks(self):
        code, out, _ = toggle(False, FakeRun({}))
        assert code == 0 and "No HT_* tasks" in out.text


class TestEnable:
    def test_enables_a_disabled_task(self):
        run = FakeRun({"HT_Cycle": "Disabled", "HT_Dashboard": "Ready", "HT_LogRotate": "Ready"})
        code, _, _ = toggle(True, run, ["cycle"])
        assert code == 0 and run.states["HT_Cycle"] == "Ready"
        assert run.changes() == [["schtasks", "/change", "/tn", "HT_Cycle", "/enable"]]

    def test_running_counts_as_enabled(self):
        run = FakeRun({"HT_Cycle": "Running"})
        code, _, _ = toggle(True, run)
        assert code == 0


class TestStatus:
    def test_lists_each_task_with_enabled_or_disabled(self):
        run = FakeRun({"HT_Cycle": "Disabled", "HT_Dashboard": "Ready"})
        out = Out()
        assert schedule_status(run=run, out=out) == 0
        assert "HT_Cycle" in out.text and "DISABLED" in out.text
        assert "HT_Dashboard" in out.text and "enabled" in out.text.lower()

    def test_summarises_when_everything_is_on(self):
        out = Out()
        schedule_status(run=FakeRun(), out=out)
        assert out.lines[-1] == "3 of 3 tasks enabled."

    def test_summarises_a_partial_state(self):
        out = Out()
        schedule_status(run=FakeRun({"HT_Cycle": "Disabled", "HT_Dashboard": "Ready"}), out=out)
        assert out.lines[-1] == "1 of 2 tasks enabled."

    def test_nothing_registered(self):
        out = Out()
        assert schedule_status(run=FakeRun({}), out=out) == 0
        assert "No HT_* tasks" in out.text
