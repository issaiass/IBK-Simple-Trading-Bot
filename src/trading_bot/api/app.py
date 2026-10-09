"""The read-only HTTP layer: two GET endpoints and JSON error handling."""
import logging
from dataclasses import asdict
from typing import Protocol

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from trading_bot.api.schemas import DashboardData
from trading_bot.api.service import InvalidPeriod

log = logging.getLogger(__name__)
NO_STORE = {"Cache-Control": "no-store"}


class DashboardProvider(Protocol):
    def dashboard(self, period: str = ...) -> DashboardData: ...


def create_app(service: DashboardProvider) -> Starlette:
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers=NO_STORE)

    async def dashboard(request: Request) -> JSONResponse:
        # the service reads files and may call Yahoo: keep it off the event loop
        period = request.query_params.get("period", "today")
        try:
            data = await run_in_threadpool(service.dashboard, period)
        except InvalidPeriod as exc:
            return JSONResponse({"error": f"invalid period: {exc}"}, status_code=400, headers=NO_STORE)
        return JSONResponse(asdict(data), headers=NO_STORE)

    async def not_found(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "not found"}, status_code=404)

    async def server_error(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse({"error": "internal server error"}, status_code=500)

    return Starlette(
        routes=[
            Route("/api/health", health, methods=["GET"]),
            Route("/api/dashboard", dashboard, methods=["GET"]),
        ],
        exception_handlers={404: not_found, Exception: server_error},
    )
