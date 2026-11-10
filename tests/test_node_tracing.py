
import asyncio
import sqlite3

from pathlib import Path
from uuid import UUID
import threading

import pytest

from langgraph.errors import GraphInterrupt

from ops_agent.api_status_store import initialize_status_store
from ops_agent.node_tracing import trace_node
from ops_agent.state import create_initial_state


INVESTIGATION_ID = UUID(
    "00000000-0000-4000-8000-000000000090"
)


def read_traces(database: Path) -> list[tuple]:
    with sqlite3.connect(database) as db:
        return db.execute(
            """
            SELECT node_name, outcome, duration_ms, error_type
            FROM node_executions
            ORDER BY execution_id
            """
        ).fetchall()


def test_traced_async_node_succeeds(tmp_path: Path) -> None:
    database = tmp_path / "statuses.sqlite"

    async def check() -> None:
        await initialize_status_store(database)

        async def collect_ci(state):
            return {"ci": None}

        traced = trace_node(
            "collect_ci",
            collect_ci,
            database_path=database,
            investigation_id=INVESTIGATION_ID,
        )

        result = await traced(
            create_initial_state("backend", "local")
        )

        assert result == {"ci": None}

    asyncio.run(check())

    traces = read_traces(database)
    assert len(traces) == 1
    assert traces[0][0] == "collect_ci"
    assert traces[0][1] == "completed"
    assert traces[0][2] >= 0
    assert traces[0][3] is None


def test_traced_node_records_failure(tmp_path: Path) -> None:
    database = tmp_path / "statuses.sqlite"

    async def check() -> None:
        await initialize_status_store(database)

        async def failing_node(state):
            raise ValueError("Sensitive failure details")

        traced = trace_node(
            "collect_logs",
            failing_node,
            database_path=database,
            investigation_id=INVESTIGATION_ID,
        )

        with pytest.raises(ValueError):
            await traced(create_initial_state("backend", "local"))

    asyncio.run(check())

    traces = read_traces(database)

    assert len(traces) == 1
    assert traces[0][1] == "failed"
    assert traces[0][3] == "ValueError"
    assert "Sensitive failure details" not in str(traces)


def test_traced_node_preserves_interrupt(tmp_path: Path) -> None:
    database = tmp_path / "statuses.sqlite"

    async def check() -> None:
        await initialize_status_store(database)

        def approval_node(state):
            raise GraphInterrupt()

        traced = trace_node(
            "request_approval",
            approval_node,
            database_path=database,
            investigation_id=INVESTIGATION_ID,
        )

        with pytest.raises(GraphInterrupt):
            await traced(create_initial_state("backend", "local"))

    asyncio.run(check())

    traces = read_traces(database)

    assert len(traces) == 1
    assert traces[0][1] == "interrupted"
    assert traces[0][3] is None

def test_sync_node_runs_outside_event_loop(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"

    async def check() -> None:
        await initialize_status_store(database)

        loop_thread = threading.get_ident()

        def sync_node(state):
            assert threading.get_ident() != loop_thread
            return {"ci": None}

        traced = trace_node(
            "collect_ci",
            sync_node,
            database_path=database,
            investigation_id=INVESTIGATION_ID,
        )

        result = await traced(
            create_initial_state("backend", "local")
        )

        assert result == {"ci": None}

    asyncio.run(check())

    traces = read_traces(database)

    assert len(traces) == 1
    assert traces[0][1] == "completed"


def test_trace_storage_failure_preserves_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(**kwargs):
        raise OSError("Trace database unavailable")

    monkeypatch.setattr(
        "ops_agent.node_tracing.save_node_execution",
        unavailable,
    )

    async def successful_node(state):
        return {"ci": None}

    traced = trace_node(
        "collect_ci",
        successful_node,
        database_path=tmp_path / "statuses.sqlite",
        investigation_id=INVESTIGATION_ID,
    )

    result = asyncio.run(
        traced(create_initial_state("backend", "local"))
    )

    assert result == {"ci": None}

def test_node_cancellation_is_propagated(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"

    async def check() -> None:
        await initialize_status_store(database)

        started = asyncio.Event()
        never_finish = asyncio.Event()

        async def long_running_node(state):
            started.set()
            await never_finish.wait()
            return {"ci": None}

        traced = trace_node(
            "collect_ci",
            long_running_node,
            database_path=database,
            investigation_id=INVESTIGATION_ID,
        )

        task = asyncio.create_task(
            traced(create_initial_state("backend", "local"))
        )

        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())

    traces = read_traces(database)

    assert len(traces) == 1
    assert traces[0][1] == "failed"
    assert traces[0][3] == "CancelledError"
