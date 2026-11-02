import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, status

from ops_agent.api_executor import execute_investigation
from ops_agent.api_models import (
    StartInvestigationRequest,
    StartInvestigationResponse,
)
from ops_agent.api_runner import InvestigationRunner
from ops_agent.report_store import ReportRunNotFound


StartRunner = Callable[[StartInvestigationRequest], Awaitable[UUID]]


def create_app(start_runner: StartRunner | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if start_runner is not None:
            app.state.start_runner = start_runner
            yield
            return

        runs_dir = Path(__file__).resolve().parents[2] / "runtime" / "runs"
        runner = InvestigationRunner(runs_dir)
        app.state.start_runner = runner.start
        worker = asyncio.create_task(runner.run_worker(execute_investigation))

        try:
            yield
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

    app = FastAPI(title="Engineering Operations Agent", lifespan=lifespan)

    @app.post(
        "/investigations",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=StartInvestigationResponse,
    )
    async def start_investigation(
        request: StartInvestigationRequest,
    ) -> StartInvestigationResponse:
        try:
            investigation_id = await app.state.start_runner(request)
        except ReportRunNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        return StartInvestigationResponse(investigation_id=investigation_id)

    return app