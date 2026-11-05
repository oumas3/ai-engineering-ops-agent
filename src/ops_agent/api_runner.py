
import asyncio
import logging

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from ops_agent.api_models import (
    InvestigationLifecycleStatus,
    StartInvestigationRequest,
)
from ops_agent.api_status_store import (
    initialize_status_store,
    save_investigation_status,
)
from ops_agent.report_store import find_report_directory


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationJob:
    investigation_id: UUID
    report_run: UUID
    analyse: bool


class InvestigationRunner:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.status_db = (
            runs_dir.parent / "investigation_statuses.sqlite"
        )
        self.queue: asyncio.Queue[InvestigationJob] = asyncio.Queue()

    async def start(
        self,
        request: StartInvestigationRequest,
    ) -> UUID:
        find_report_directory(self.runs_dir, request.report_run)

        job = InvestigationJob(
            investigation_id=uuid4(),
            report_run=request.report_run,
            analyse=request.analyse,
        )

        await initialize_status_store(self.status_db)

        await save_investigation_status(
            self.status_db,
            job.investigation_id,
            "queued",
        )

        await self.queue.put(job)

        return job.investigation_id

    async def process_next(
        self,
        execute: Callable[
            [InvestigationJob],
            Awaitable[InvestigationLifecycleStatus | None],
        ],
    ) -> None:
        job = await self.queue.get()

        try:
            await save_investigation_status(
                self.status_db,
                job.investigation_id,
                "running",
            )

            outcome = await execute(job)

            if outcome not in (None, "awaiting_approval", "completed"):
                raise ValueError(
                    f"Unexpected investigation outcome: {outcome}"
                )

            final_status: InvestigationLifecycleStatus = (
                "awaiting_approval"
                if outcome == "awaiting_approval"
                else "completed"
            )

            await save_investigation_status(
                self.status_db,
                job.investigation_id,
                final_status,
            )

        except Exception:
            logger.exception(
                "Investigation %s failed",
                job.investigation_id,
            )

            try:
                await save_investigation_status(
                    self.status_db,
                    job.investigation_id,
                    "failed",
                    "Investigation execution failed; check server logs.",
                )
            except Exception:
                logger.exception(
                    "Could not save failure status for %s",
                    job.investigation_id,
                )

        finally:
            self.queue.task_done()
                
    async def run_worker(
        self,
        execute: Callable[
            [InvestigationJob],
            Awaitable[InvestigationLifecycleStatus | None],
        ],
    ) -> None:
        while True:
            await self.process_next(execute)
        