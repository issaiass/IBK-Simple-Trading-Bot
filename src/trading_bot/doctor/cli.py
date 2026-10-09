"""`uv run doctor`: check the setup end to end and say how to fix what is wrong."""
import socket
import subprocess
import sys
from datetime import datetime

from trading_bot.doctor.checks import Check, Environment, Status, run_doctor

TAGS = {Status.OK: "[ OK ]", Status.WARN: "[WARN]", Status.FAIL: "[FAIL]", Status.SKIP: "[SKIP]"}
PROBE_TIMEOUT_SECONDS = 1.0


def exit_code(results: list[Check]) -> int:
    return 1 if any(c.status is Status.FAIL for c in results) else 0


def render(results: list[Check]) -> str:
    lines = []
    for check in results:
        lines.append(f"{TAGS[check.status]} {check.name:<17} {check.detail}")
        if check.fix and check.status in (Status.FAIL, Status.WARN):
            lines.append(f"       fix: {check.fix}")
    failed = sum(c.status is Status.FAIL for c in results)
    warned = sum(c.status is Status.WARN for c in results)
    passed = sum(c.status is Status.OK for c in results)
    lines.append("")
    lines.append(f"{failed} failed, {warned} warning{'s' if warned != 1 else ''}, {passed} ok.")
    return "\n".join(lines)


def tcp_probe(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _schedule_states() -> dict[str, str]:
    """HT_* task name -> Ready/Disabled, from whichever scheduler this OS uses."""
    if sys.platform == "win32":
        from trading_bot.scheduling.toggle import list_tasks

        return list_tasks()
    if sys.platform == "darwin":
        from trading_bot.scheduling.launchd import launchd_states

        return launchd_states()
    from trading_bot.scheduling import cron

    jobs = cron.parse_jobs(cron.read_crontab(subprocess.run))
    return {name: "Ready" if on else "Disabled" for name, on in jobs.items()}


def _last_heartbeat() -> datetime | None:
    from trading_bot.api.sources import DecisionLogReader
    from trading_bot.config import DECISION_LOG_PATH

    heartbeat = DecisionLogReader(DECISION_LOG_PATH).last_cycle()
    return datetime.fromisoformat(heartbeat["timestamp"]) if heartbeat else None


def main() -> int:
    from ib_async import IB

    from trading_bot.config import load_rules
    from trading_bot.settings import Settings
    from trading_bot.timeutil import now_et

    results = run_doctor(Environment(
        load_settings=Settings.from_env, probe=tcp_probe, ib_factory=IB,
        schedule_states=_schedule_states, last_heartbeat=_last_heartbeat,
        rules=load_rules(), clock=now_et,
    ))
    print(render(results))
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
