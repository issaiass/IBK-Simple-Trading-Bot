from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from trading_bot.doctor import checks
from trading_bot.doctor.checks import Check, Environment, Status, run_doctor
from trading_bot.doctor.cli import exit_code, render
from trading_bot.settings import Settings
from trading_bot.timeutil import ET

ENV = {
    "IBKR_HOST": "127.0.0.1", "IBKR_PORT": "7497", "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3", "PAPER_TRADING": "true", "PORTFOLIO_VALUE_USD": "25000",
    "MAX_TRADE_SIZE_USD": "2500", "MAX_TRADES_PER_DAY": "5", "MAX_RISK_PER_TRADE_PCT": "1.0",
}
SETTINGS = Settings.from_env(ENV)
RULES = {"time_filter": {"earliest_entry_et": "10:05", "latest_entry_et": "15:30",
                         "force_close_et": "15:51"}}
MARKET_HOURS = datetime(2026, 10, 8, 11, 0, tzinfo=ET)  # a Thursday
SUNDAY = datetime(2026, 10, 11, 11, 0, tzinfo=ET)


class FakeIB:
    def __init__(self, accounts=("DU1234567",), price=101.5, what_if=None, connect_error=None):
        self.accounts, self.price, self.connect_error = list(accounts), price, connect_error
        self.what_if = what_if if what_if is not None else SimpleNamespace(warningText="")
        self.events = []

    def connect(self, host, port, clientId, timeout=4, **kwargs):
        self.events.append(("connect", host, port, clientId))
        if self.connect_error:
            raise self.connect_error

    def managedAccounts(self):
        return self.accounts

    def qualifyContracts(self, contract):
        return [contract]

    def reqMarketDataType(self, kind):
        self.events.append(("data_type", kind))

    def reqTickers(self, contract):
        return [SimpleNamespace(marketPrice=lambda: self.price, close=float("nan"))]

    def whatIfOrder(self, contract, order):
        self.what_if_orders = [*getattr(self, "what_if_orders", []), order]
        if isinstance(self.what_if, Exception):
            raise self.what_if
        return self.what_if

    def disconnect(self):
        self.events.append(("disconnect",))


def environment(ib=None, **overrides):
    ib = ib or FakeIB()
    values = dict(
        load_settings=lambda: SETTINGS,
        probe=lambda host, port: port == 7497,
        ib_factory=lambda: ib,
        schedule_states=lambda: {f"HT_{n}": "Ready" for n in range(11)},
        last_heartbeat=lambda: MARKET_HOURS - timedelta(minutes=3),
        rules=RULES,
        clock=lambda: MARKET_HOURS,
    )
    values.update(overrides)
    return Environment(**values), ib


def by_name(results):
    return {c.name: c for c in results}


class TestSettings:
    def test_valid_settings_are_ok(self):
        check, settings = checks.check_settings(lambda: SETTINGS)
        assert check.status is Status.OK and settings is SETTINGS

    def test_a_missing_value_is_named_with_the_fix(self):
        def load():
            raise KeyError("IBKR_PORT")

        check, settings = checks.check_settings(load)
        assert check.status is Status.FAIL and settings is None
        assert "IBKR_PORT" in check.detail and ".env.example" in check.fix

    def test_a_flag_that_contradicts_the_port_fails(self):
        live_port = Settings.from_env({**ENV, "IBKR_PORT": "7496"})
        check, _ = checks.check_settings(lambda: live_port)
        assert check.status is Status.FAIL and "paper flag but live port" in check.detail


class TestListening:
    def test_an_open_port_is_ok(self):
        assert checks.check_listening(SETTINGS, lambda h, p: True).status is Status.OK

    def test_nothing_listening_means_tws_is_not_running(self):
        check = checks.check_listening(SETTINGS, lambda h, p: False)
        assert check.status is Status.FAIL
        assert "not running" in check.detail.lower() and "TWS" in check.fix

    def test_another_known_port_open_means_the_wrong_port_is_configured(self):
        check = checks.check_listening(SETTINGS, lambda h, p: p == 4002)
        assert check.status is Status.FAIL
        assert "wrong" in check.detail.lower() and "4002" in check.detail and "IBKR_PORT" in check.fix


class TestApiSession:
    def test_connects_with_its_own_client_id(self):
        ib = FakeIB()
        check, session = checks.check_api_session(SETTINGS, lambda: ib)
        assert check.status is Status.OK and session is ib
        client_id = ib.events[0][3]
        assert client_id not in (SETTINGS.client_id, SETTINGS.exec_client_id)

    def test_a_silent_handshake_points_at_api_settings_and_trusted_ips(self):
        check, session = checks.check_api_session(SETTINGS, lambda: FakeIB(connect_error=TimeoutError()))
        assert check.status is Status.FAIL and session is None
        for needle in ("Enable ActiveX and Socket Clients", "Trusted IPs", "127.0.0.1"):
            assert needle in check.fix

    def test_a_refused_connection_is_reported_as_such(self):
        check, _ = checks.check_api_session(SETTINGS, lambda: FakeIB(connect_error=ConnectionRefusedError()))
        assert check.status is Status.FAIL and "refused" in check.detail.lower()


class TestAccount:
    def test_a_paper_account_with_the_paper_flag_is_ok(self):
        check = checks.check_account(SETTINGS, FakeIB())
        assert check.status is Status.OK and "DU1234567" in check.detail

    def test_a_live_account_with_the_paper_flag_fails(self):
        check = checks.check_account(SETTINGS, FakeIB(accounts=["U7654321"]))
        assert check.status is Status.FAIL and "live account" in check.detail
        assert "paper" in check.fix.lower()


class TestMarketData:
    def test_a_price_means_data_flows(self):
        assert checks.check_market_data(FakeIB(price=412.3)).status is Status.OK

    def test_no_price_warns_about_the_subscription(self):
        check = checks.check_market_data(FakeIB(price=float("nan")))
        assert check.status is Status.WARN and "subscription" in check.fix.lower()

    def test_asks_for_delayed_data_like_the_bot_does(self):
        ib = FakeIB()
        checks.check_market_data(ib)
        assert ("data_type", 3) in ib.events


class TestOrderPermission:
    def test_an_accepted_what_if_is_ok_and_places_nothing(self):
        check = checks.check_order_permission(FakeIB())
        assert check.status is Status.OK and "no order" in check.detail.lower()

    def test_the_what_if_order_states_its_time_in_force_so_ibkr_adds_no_notice(self):
        ib = FakeIB()
        checks.check_order_permission(ib)
        assert ib.what_if_orders[0].tif == "DAY"

    def test_a_rejected_what_if_means_permissions_are_missing(self):
        check = checks.check_order_permission(FakeIB(what_if=RuntimeError("Error 201: no permission")))
        assert check.status is Status.FAIL and "Trading permissions" in check.fix

    def test_a_broker_warning_is_surfaced(self):
        warned = SimpleNamespace(warningText="Insufficient margin")
        check = checks.check_order_permission(FakeIB(what_if=warned))
        assert check.status is Status.WARN and "Insufficient margin" in check.detail


class TestSchedule:
    def test_everything_enabled_is_ok(self):
        states = {f"HT_{n}": "Ready" for n in range(11)}
        assert checks.check_schedule(states).status is Status.OK

    def test_some_disabled_warns_with_the_count(self):
        states = {"HT_A": "Ready", "HT_B": "Disabled", "HT_C": "Disabled"}
        check = checks.check_schedule(states)
        assert check.status is Status.WARN and "1 of 3" in check.detail

    def test_all_off_is_a_warning_not_an_error(self):
        check = checks.check_schedule({"HT_A": "Disabled", "HT_B": "Disabled"})
        assert check.status is Status.WARN and "enable-schedule" in check.fix

    def test_nothing_registered_points_at_setup(self):
        check = checks.check_schedule({})
        assert check.status is Status.WARN and "setup-schedule" in check.fix

    def test_an_unreadable_scheduler_is_skipped(self):
        assert checks.check_schedule(None).status is Status.SKIP


class TestHeartbeat:
    def beat(self, minutes_ago, now=MARKET_HOURS, enabled=True):
        when = None if minutes_ago is None else now - timedelta(minutes=minutes_ago)
        return checks.check_heartbeat(when, now, RULES, schedule_enabled=enabled)

    def test_a_recent_cycle_during_market_hours_is_ok(self):
        assert self.beat(4).status is Status.OK

    def test_a_stale_cycle_during_market_hours_lists_the_usual_causes(self):
        check = self.beat(45)
        assert check.status is Status.WARN
        for cause in ("asleep", "logged out", "permission"):
            assert cause in check.fix.lower()

    def test_no_cycle_ever_during_market_hours_warns(self):
        assert self.beat(None).status is Status.WARN

    def test_outside_market_hours_a_stale_cycle_is_fine(self):
        check = self.beat(60 * 20, now=SUNDAY)
        assert check.status is Status.OK and "market" in check.detail.lower()

    def test_a_disabled_schedule_explains_the_silence(self):
        assert self.beat(45, enabled=False).status is Status.SKIP


class TestRunDoctor:
    def test_a_healthy_setup_passes_every_check(self):
        env, ib = environment()
        results = run_doctor(env)
        assert [c.status for c in results] == [Status.OK] * len(results)
        assert exit_code(results) == 0
        assert ("disconnect",) in ib.events

    def test_without_tws_the_broker_checks_are_skipped_but_the_schedule_still_runs(self):
        env, _ = environment(probe=lambda h, p: False)
        named = by_name(run_doctor(env))
        assert named["TWS port"].status is Status.FAIL
        for skipped in ("API session", "Account", "Market data", "Order permission"):
            assert named[skipped].status is Status.SKIP
        assert named["Schedule"].status is Status.OK

    def test_a_failed_handshake_skips_what_needs_a_session(self):
        env, _ = environment(ib=FakeIB(connect_error=TimeoutError()))
        named = by_name(run_doctor(env))
        assert named["API session"].status is Status.FAIL
        assert named["Account"].status is Status.SKIP

    def test_invalid_settings_stop_everything_after_them(self):
        def load():
            raise KeyError("IBKR_HOST")

        env, _ = environment(load_settings=load)
        results = run_doctor(env)
        assert results[0].status is Status.FAIL
        assert all(c.status is Status.SKIP for c in results[1:6])

    def test_the_session_is_closed_even_when_a_check_blows_up(self):
        class Exploding(FakeIB):
            def managedAccounts(self):
                raise RuntimeError("boom")

        ib = Exploding()
        env, _ = environment(ib=ib)
        results = run_doctor(env)
        assert by_name(results)["Account"].status is Status.FAIL
        assert ("disconnect",) in ib.events

    def test_schedule_and_heartbeat_readers_that_fail_are_skipped_not_fatal(self):
        def broken():
            raise OSError("cannot read")

        env, _ = environment(schedule_states=broken, last_heartbeat=broken)
        named = by_name(run_doctor(env))
        assert named["Schedule"].status is Status.SKIP
        assert named["Last cycle"].status is Status.SKIP


class TestReport:
    def test_failures_set_the_exit_code_but_warnings_do_not(self):
        warn = Check("a", Status.WARN, "d")
        fail = Check("b", Status.FAIL, "d", "fix")
        assert exit_code([warn]) == 0
        assert exit_code([warn, fail]) == 1

    def test_each_line_shows_the_status_detail_and_the_fix(self):
        text = render([Check("TWS port", Status.FAIL, "nothing on 7497", "Start TWS")])
        assert "FAIL" in text and "TWS port" in text and "nothing on 7497" in text
        assert "Start TWS" in text

    def test_the_summary_counts_problems(self):
        text = render([Check("a", Status.OK, "d"), Check("b", Status.WARN, "d", "f"),
                       Check("c", Status.FAIL, "d", "f")])
        assert "1 failed" in text and "1 warning" in text


@pytest.mark.parametrize("status", list(Status))
def test_every_status_renders(status):
    assert render([Check("x", status, "detail", "fix")])
