from dataclasses import asdict

import pytest
from starlette.testclient import TestClient

from trading_bot.api.app import create_app
from trading_bot.api.schemas import (
    DashboardData,
    EquityPoint,
    OpenPositionData,
    PaperProgressData,
    RBucket,
    StatusData,
    SummaryData,
    TradeData,
)


def sample() -> DashboardData:
    return DashboardData(
        generated_at="2026-10-08T13:00:00-04:00",
        period="today",
        cycle=None,
        paper=PaperProgressData(True, "2026-10-03", 6, 14, 8, False),
        status=StatusData("ACTIVE", "2026-10-08T12:58:00-04:00", "cycle", "last cycle 2 min ago", "ok"),
        summary=SummaryData(from_date="2026-10-08", to_date="2026-10-08", total_trades=1, wins=1, losses=0, breakeven=0,
                          win_rate_pct=100.0, gross_pnl_usd=20.0, profit_factor="inf",
                          largest_winner={"symbol": "NVDA", "pnl_usd": 20.0}, largest_loser=None,
                          avg_winner=20.0, avg_loser=None),
        r_histogram=[RBucket("≤ -2R", None, -2, 0), RBucket("> +3R", 3, None, 1)],
        open_positions=[OpenPositionData("NVDA", 9, 100.0, 98.0, 98.0, "pre_breakeven",
                                         103.0, 1.5, 27.0, "2026-10-08T10:00:00-04:00", 420.0, 102.0, 4.85, -0.97)],
        recent_trades=[TradeData("NVDA", 10, 100.0, 102.0, 20.0, 2.0, 2.0, "proxy",
                                 "2026-10-08T10:00:00-04:00", "2026-10-08T11:00:00-04:00", 60.0)],
        equity_curve=[EquityPoint("2026-10-08T11:00:00-04:00", "NVDA", 20.0, 20.0)],
        warnings=[],
    )


class FakeService:
    def __init__(self, data=None, error=None):
        self.data, self.error, self.calls, self.periods = data or sample(), error, 0, []

    def dashboard(self, period="today"):
        self.periods.append(period)
        self.calls += 1
        if self.error:
            raise self.error
        return self.data


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture
def client(service):
    return TestClient(create_app(service))


class TestHealth:
    def test_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200 and r.json() == {"status": "ok"}


class TestDashboardEndpoint:
    def test_includes_the_paper_run_progress(self, client):
        paper = client.get("/api/dashboard").json()["paper"]
        assert paper == {"paper_mode": True, "first_trade_date": "2026-10-03", "days_traded": 6,
                         "target_days": 14, "days_remaining": 8, "reached": False}

    def test_returns_the_whole_dashboard_as_json(self, client):
        r = client.get("/api/dashboard")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == asdict(sample())

    def test_payload_has_the_documented_sections(self, client):
        body = client.get("/api/dashboard").json()
        assert set(body) == {"generated_at", "period", "status", "summary", "cycle", "r_histogram",
                             "open_positions", "recent_trades", "equity_curve", "warnings", "paper"}

    def test_every_request_reads_fresh_data(self, client, service):
        client.get("/api/dashboard")
        client.get("/api/dashboard")
        assert service.calls == 2

    def test_responses_are_never_cached(self, client):
        assert client.get("/api/dashboard").headers["cache-control"] == "no-store"

    def test_a_service_failure_is_a_clean_500_without_a_traceback(self):
        client = TestClient(create_app(FakeService(error=RuntimeError("secret internals"))),
                            raise_server_exceptions=False)
        r = client.get("/api/dashboard")
        assert r.status_code == 500
        assert r.json() == {"error": "internal server error"}
        assert "secret" not in r.text


class TestRouting:
    def test_unknown_route_is_a_json_404(self, client):
        r = client.get("/api/nope")
        assert r.status_code == 404 and r.json() == {"error": "not found"}

    @pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
    def test_the_api_is_read_only(self, client, method):
        assert getattr(client, method)("/api/dashboard").status_code == 405


class TestPeriodParameter:
    def test_defaults_to_today(self, client, service):
        client.get("/api/dashboard")
        assert service.periods == ["today"]

    @pytest.mark.parametrize("period", ["today", "7d", "30d", "all"])
    def test_is_passed_to_the_service(self, client, service, period):
        assert client.get(f"/api/dashboard?period={period}").status_code == 200
        assert service.periods == [period]

    def test_an_unknown_period_is_a_400_with_a_json_error(self, service):
        from trading_bot.api.service import InvalidPeriod
        service.error = InvalidPeriod("year")
        r = TestClient(create_app(service)).get("/api/dashboard?period=year")
        assert r.status_code == 400 and r.json() == {"error": "invalid period: year"}
