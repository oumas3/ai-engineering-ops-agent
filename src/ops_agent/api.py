import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from functools import partial
import os
from pathlib import Path
from uuid import UUID
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException, Response, Query, status
from ops_agent.api_executor import execute_investigation
from ops_agent.api_models import (
    InvestigationResultResponse,
    StartInvestigationRequest,
    StartInvestigationResponse,
    InvestigationStatusResponse,
)
from ops_agent.api_status_store import read_investigation_status , list_investigation_statuses
from ops_agent.api_runner import InvestigationRunner
from ops_agent.report_store import ReportRunNotFound
from ops_agent.api_reader import read_investigation
from ops_agent.api_status_store import initialize_status_store
from ops_agent.api_decisions import (
    InvestigationNotFound,
    IssueCreationDisabled,
    NoPendingApproval,
    apply_decision,
    is_approval_pending,
)
from ops_agent.api_status_store import save_investigation_status
from ops_agent.api_models import InvestigationDecisionRequest,ApprovalStatusResponse
from ops_agent.api_models import InvestigationEventResponse
from ops_agent.api_status_store import read_investigation_events

StartRunner = Callable[[StartInvestigationRequest], Awaitable[UUID]]


def create_app(start_runner: StartRunner | None = None) -> FastAPI:
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.allow_create_issue = (
            os.environ.get("OPS_ALLOW_CREATE_ISSUE") == "1"
        )
        app.state.decision_lock = asyncio.Lock()
        app.state.status_db = None
        if start_runner is not None:
            app.state.start_runner = start_runner
            yield
            return

        runs_dir = Path(__file__).resolve().parents[2] / "runtime" / "runs"
        runner = InvestigationRunner(runs_dir)
        app.state.start_runner = runner.start
        app.state.status_db = runner.status_db
        await initialize_status_store(runner.status_db)
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
    @app.get(
        "/investigations",
        response_model=list[InvestigationStatusResponse],
    )
    async def list_investigations(
        limit: int = Query(20, ge=1, le=100),
    ) -> list[InvestigationStatusResponse]:

        database = app.state.status_db

        if database is None:
            raise HTTPException(
                status_code=503,
                detail="Investigation history is unavailable.",
            )

        return await list_investigation_statuses(
            database,
            limit,
        )

    @app.get(
        "/investigations/{investigation_id}/events",
        response_model=list[InvestigationEventResponse],
    )
    async def get_investigation_events(
        investigation_id: UUID,
    ) -> list[InvestigationEventResponse]:
        database = app.state.status_db

        if database is None:
            raise HTTPException(
                status_code=503,
                detail="Investigation event storage is unavailable.",
            )

        current = await read_investigation_status(
            database,
            investigation_id,
        )

        if current is None:
            raise HTTPException(
                status_code=404,
                detail="Investigation not found.",
            )

        return await read_investigation_events(
            database,
            investigation_id,
        )


    @app.get(
        "/investigations/{investigation_id}/status",
        response_model=InvestigationStatusResponse,
    )
    async def get_investigation_status(
        investigation_id: UUID,
    ) -> InvestigationStatusResponse:

        database = app.state.status_db

        if database is None:
            raise HTTPException(
                status_code=503,
                detail="Investigation status storage is unavailable.",
            )

        result = await read_investigation_status(
            database,
            investigation_id,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Investigation status not found.",
            )

        return result

    @app.post(
        "/investigations",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=StartInvestigationResponse,
    )
    async def start_investigation(
        request: StartInvestigationRequest,
    ) -> StartInvestigationResponse:

        if request.analyse and not os.environ.get("GROQ_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "AI analysis is unavailable. "
                    "Disable AI analysis or configure GROQ_API_KEY."
                ),
            )

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

    @app.get(
        "/investigations/{investigation_id}/approval",
        response_model=ApprovalStatusResponse,
    )
    async def get_approval_status(
        investigation_id: UUID,
    ) -> ApprovalStatusResponse:
        try:
            pending = await is_approval_pending(investigation_id)
        except InvestigationNotFound as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error

        return ApprovalStatusResponse(
            approval_pending=pending,
            issue_creation_enabled=app.state.allow_create_issue,
        )

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

                if app.state.status_db is not None:
                    await save_investigation_status(
                        app.state.status_db,
                        investigation_id,
                        "completed",
                    )

        except InvestigationNotFound as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            ) from error

        except NoPendingApproval as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            ) from error

        except IssueCreationDisabled as error:
            raise HTTPException(
                status_code=403,
                detail=str(error),
            ) from error

        return Response(
            status_code=status.HTTP_204_NO_CONTENT
        )


    @app.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        page = Path(__file__).resolve().parent / "web" / "index.html"
        return FileResponse(page)

    return app
