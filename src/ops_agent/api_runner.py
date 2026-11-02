import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from ops_agent.api_models import StartInvestigationRequest
from ops_agent.report_store import find_report_directory

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class InvestigationJob:
    investigation_id: UUID
    report_run: UUID
    analyse: bool


class InvestigationRunner:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.queue: asyncio.Queue[InvestigationJob] = asyncio.Queue()

    async def start(self, request: StartInvestigationRequest) -> UUID:
        find_report_directory(self.runs_dir, request.report_run)

        job = InvestigationJob(
            investigation_id=uuid4(),
            report_run=request.report_run,
            analyse=request.analyse,
        )
        await self.queue.put(job)
        return job.investigation_id
    async def process_next(
        self,
        execute: Callable[[InvestigationJob], Awaitable[None]],
    ) -> None:
        job = await self.queue.get()

        try:
            await execute(job)
        except Exception:
            logger.exception("Investigation %s failed", job.investigation_id)
        finally:
            self.queue.task_done()

    async def run_worker(
        self,
        execute: Callable[[InvestigationJob], Awaitable[None]],
    ) -> None:
        while True:
            await self.process_next(execute)