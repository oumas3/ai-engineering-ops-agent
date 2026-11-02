import asyncio
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from ops_agent.api_models import StartInvestigationRequest
from ops_agent.api_runner import InvestigationJob, InvestigationRunner


def test_worker_continues_after_one_job_fails(tmp_path: Path) -> None:
    async def check() -> None:
        runner = InvestigationRunner(tmp_path)
        report_run = UUID("94f6c0cd-ef5d-456d-9c70-8b84d986df24")
        (tmp_path / report_run.hex).mkdir()
        request = StartInvestigationRequest(report_run=report_run)

        first_id = await runner.start(request)
        second_id = await runner.start(request)
        processed: list[UUID] = []

        async def execute(job: InvestigationJob) -> None:
            processed.append(job.investigation_id)
            if job.investigation_id == first_id:
                raise RuntimeError("Simulated investigation failure")

        worker = asyncio.create_task(runner.run_worker(execute))
        try:
            await asyncio.wait_for(runner.queue.join(), timeout=2)
            assert processed == [first_id, second_id]
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

    asyncio.run(check())