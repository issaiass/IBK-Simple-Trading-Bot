import pytest

from trading_bot.api.server import ApiSettings, build_service, paper_mode_from
from trading_bot.api.service import DashboardService


class TestApiSettings:
    def test_defaults_bind_to_localhost_only(self):
        s = ApiSettings.from_env({})
        assert (s.host, s.port) == ("127.0.0.1", 8000)

    def test_reads_host_and_port_from_the_environment(self):
        s = ApiSettings.from_env({"DASHBOARD_API_HOST": "0.0.0.0", "DASHBOARD_API_PORT": "9000"})
        assert (s.host, s.port) == ("0.0.0.0", 9000)

    @pytest.mark.parametrize("port", ["abc", "0", "70000", "-1"])
    def test_rejects_an_invalid_port(self, port):
        with pytest.raises(ValueError, match="DASHBOARD_API_PORT"):
            ApiSettings.from_env({"DASHBOARD_API_PORT": port})


def test_build_service_wires_the_real_files_without_touching_the_network():
    assert isinstance(build_service(), DashboardService)


class TestPaperModeFromEnv:
    def test_defaults_to_paper_when_unset(self):
        assert paper_mode_from({}) is True

    @pytest.mark.parametrize("raw, expected", [("true", True), (" TRUE ", True), ("false", False), ("False", False)])
    def test_reads_the_same_flag_the_bot_does(self, raw, expected):
        assert paper_mode_from({"PAPER_TRADING": raw}) is expected
