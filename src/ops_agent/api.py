import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from functools import partial
import os
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Response, status

from ops_agent.api_executor import execute_investigation
from ops_agent.api_models import (
    InvestigationResultResponse,
    StartInvestigationRequest,
    StartInvestigationResponse,
)
from ops_agent.api_runner import InvestigationRunner
from ops_agent.report_store import ReportRunNotFound
from ops_agent.api_reader import read_investigation
from ops_agent.api_decisions import (
    InvestigationNotFound,
    IssueCreationDisabled,
    NoPendingApproval,
    apply_decision,
)
from ops_agent.api_models import InvestigationDecisionRequest


StartRunner = Callable[[StartInvestigationRequest], Awaitable[UUID]]


def create_app(start_runner: StartRunner | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.allow_create_issue = (
            os.environ.get("OPS_ALLOW_CREATE_ISSUE") == "1"
        )
        app.state.decision_lock = asyncio.Lock()
        if start_runner is not None:
            app.state.start_runner = start_runner
            yield
            return

        runs_dir = Path(__file__).resolve().parents[2] / "runtime" / "runs"
        runner = InvestigationRunner(runs_dir)
        app.state.start_runner = runner.start
        execute = partial(
            execute_investigation,
            allow_create_issue=app.state.allow_create_issue,
        )
        worker = asyncio.create_task(runner.run_worker(execute))
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
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error

        return StartInvestigationResponse(
            investigation_id=investigation_id,
        )

    @app.get(
        "/investigations/{investigation_id}",
        response_model=InvestigationResultResponse,
    )
    async def get_investigation(
        investigation_id: UUID,
    ) -> InvestigationResultResponse:
        runtime_dir = Path(__file__).resolve().parents[2] / "runtime"
        result = await read_investigation(
            investigation_id,
            runtime_dir / "checkpoints.sqlite",
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No saved investigation result is available for this ID.",
            )

        return result
    @app.post(
        "/investigations/{investigation_id}/decision",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def decide_investigation(
        investigation_id: UUID,
        request: InvestigationDecisionRequest,
    ) -> Response:
        try:
            async with app.state.decision_lock:
                await apply_decision(
                    investigation_id,
                    request.decision,
                    allow_create_issue=app.state.allow_create_issue,
                )
        except InvestigationNotFound as error:
            raise HTTPException(404, detail=str(error)) from error
        except NoPendingApproval as error:
            raise HTTPException(409, detail=str(error)) from error
        except IssueCreationDisabled as error:
            raise HTTPException(403, detail=str(error)) from error

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return app