from unittest.mock import AsyncMock
from uuid import UUID

import asyncio

from ops_agent.api_status_store import (
    initialize_status_store,
    read_investigation_status,
    save_investigation_status,
)
from fastapi.testclient import TestClient

from ops_agent.api import create_app
from pathlib import Path

from ops_agent.api_models import (
    InvestigationResultResponse,
    StartInvestigationRequest,
)

from ops_agent.report_store import find_report_directory
from ops_agent.api_runner import InvestigationRunner



def test_decision_updates_lifecycle_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000030"
    )

    database = tmp_path / "statuses.sqlite"

    asyncio.run(initialize_status_store(database))

    asyncio.run(
        save_investigation_status(
            database,
            investigation_id,
            "awaiting_approval",
        )
    )

    decision = AsyncMock()

    monkeypatch.setattr(
        "ops_agent.api.apply_decision",
        decision,
    )

    monkeypatch.setenv(
        "OPS_ALLOW_CREATE_ISSUE",
        "1",
    )

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database

        response = client.post(
            f"/investigations/{investigation_id}/decision",
            json={"decision": "approved"},
        )

    assert response.status_code == 204

    decision.assert_awaited_once()

    saved = asyncio.run(
        read_investigation_status(
            database,
            investigation_id,
        )
    )

    assert saved is not None
    assert saved.status == "completed"
    assert saved.error is None



def test_start_returns_id_from_runner() -> None:
    investigation_id = UUID("00000000-0000-4000-8000-000000000001")
    runner = AsyncMock(return_value=investigation_id)
    report_run = "94f6c0cdef5d456d9c708b84d986df24"

    with TestClient(create_app(runner)) as client:
        response = client.post(
            "/investigations",
            json={"report_run": report_run},
        )

    assert response.status_code == 202
    assert response.json() == {"investigation_id": str(investigation_id)}
    runner.assert_awaited_once()
    assert runner.await_args.args[0].report_run == UUID(report_run)



def test_start_rejects_analysis_without_groq_key(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    runner = AsyncMock()

    with TestClient(create_app(runner)) as client:
        response = client.post(
            "/investigations",
            json={
                "report_run": "94f6c0cdef5d456d9c708b84d986df24",
                "analyse": True,
            },
        )

    assert response.status_code == 400
    assert "GROQ_API_KEY" in response.json()["detail"]

    runner.assert_not_awaited()

def test_invalid_report_never_reaches_runner() -> None:
    runner = AsyncMock()

    with TestClient(create_app(runner)) as client:
        response = client.post(
            "/investigations",
            json={"report_run": "../data"},
        )

    assert response.status_code == 422
    runner.assert_not_awaited()

def test_lookup_finds_hex_report_folder(tmp_path: Path) -> None:
    report_run = UUID("94f6c0cd-ef5d-456d-9c70-8b84d986df24")
    expected = tmp_path / report_run.hex
    expected.mkdir()

    assert find_report_directory(tmp_path, report_run) == expected


def test_start_returns_404_for_missing_report(tmp_path: Path) -> None:
    runner = InvestigationRunner(tmp_path)
    report_run = UUID("94f6c0cd-ef5d-456d-9c70-8b84d986df24")

    with TestClient(create_app(runner.start)) as client:
        response = client.post(
            "/investigations",
            json={"report_run": str(report_run)},
        )

    assert response.status_code == 404
    assert runner.queue.empty()


def test_start_queues_the_requested_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-only-dummy-key")

    runner = InvestigationRunner(tmp_path)
    report_run = UUID("94f6c0cd-ef5d-456d-9c70-8b84d986df24")
    (tmp_path / report_run.hex).mkdir()

    with TestClient(create_app(runner.start)) as client:
        response = client.post(
            "/investigations",
            json={"report_run": str(report_run), "analyse": True},
        )

    assert response.status_code == 202

    job = runner.queue.get_nowait()

    assert job.investigation_id == UUID(response.json()["investigation_id"])
    assert job.report_run == report_run
    assert job.analyse is True


def test_get_investigation_returns_saved_result(monkeypatch) -> None:
    investigation_id = UUID("00000000-0000-4000-8000-000000000002")

    result = InvestigationResultResponse(
        investigation_id=investigation_id,
        service="backend",
        environment="local",
        ci=None,
        failed_tests=None,
        logs=None,
        service_status=None,
        analysis=None,
        issue_proposal=None,
        errors=[],
    )

    reader = AsyncMock(return_value=result)
    monkeypatch.setattr("ops_agent.api.read_investigation", reader)

    runner = AsyncMock()

    with TestClient(create_app(runner)) as client:
        response = client.get(f"/investigations/{investigation_id}")

    assert response.status_code == 200
    assert response.json()["investigation_id"] == str(investigation_id)
    assert response.json()["service"] == "backend"


def test_get_unknown_investigation_returns_404(monkeypatch) -> None:
    investigation_id = UUID("00000000-0000-4000-8000-000000000003")

    reader = AsyncMock(return_value=None)
    monkeypatch.setattr("ops_agent.api.read_investigation", reader)

    runner = AsyncMock()

    with TestClient(create_app(runner)) as client:
        response = client.get(f"/investigations/{investigation_id}")

    assert response.status_code == 404


def test_decision_endpoint_accepts_approval(monkeypatch) -> None:
    investigation_id = UUID("00000000-0000-4000-8000-000000000004")

    decision = AsyncMock()
    monkeypatch.setattr("ops_agent.api.apply_decision", decision)
    monkeypatch.setenv("OPS_ALLOW_CREATE_ISSUE", "1")

    runner = AsyncMock()

    with TestClient(create_app(runner)) as client:
        response = client.post(
            f"/investigations/{investigation_id}/decision",
            json={"decision": "approved"},
        )

    assert response.status_code == 204

    decision.assert_awaited_once_with(
        investigation_id,
        "approved",
        allow_create_issue=True,
    )


def test_approval_status_without_pending_approval(monkeypatch) -> None:
    investigation_id = UUID("00000000-0000-4000-8000-000000000020")

    checker = AsyncMock(return_value=False)
    monkeypatch.setattr("ops_agent.api.is_approval_pending", checker)
    monkeypatch.delenv("OPS_ALLOW_CREATE_ISSUE", raising=False)

    with TestClient(create_app(AsyncMock())) as client:
        response = client.get(
            f"/investigations/{investigation_id}/approval"
        )

    assert response.status_code == 200
    assert response.json() == {
        "approval_pending": False,
        "issue_creation_enabled": False,
    }
    checker.assert_awaited_once_with(investigation_id)


def test_get_investigation_lifecycle_status(
    tmp_path: Path,
) -> None:
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000040"
    )

    database = tmp_path / "statuses.sqlite"

    asyncio.run(initialize_status_store(database))

    asyncio.run(
        save_investigation_status(
            database,
            investigation_id,
            "awaiting_approval",
        )
    )

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database

        response = client.get(
            f"/investigations/{investigation_id}/status"
        )

    assert response.status_code == 200

    assert response.json() == {
        "investigation_id": str(investigation_id),
        "status": "awaiting_approval",
        "error": None,
    }



def test_get_unknown_lifecycle_status(
    tmp_path: Path,
) -> None:
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000041"
    )

    database = tmp_path / "statuses.sqlite"

    asyncio.run(initialize_status_store(database))

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database

        response = client.get(
            f"/investigations/{investigation_id}/status"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Investigation status not found."
    )



def test_list_investigations_returns_latest_first(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"

    first_id = UUID("00000000-0000-4000-8000-000000000001")
    second_id = UUID("00000000-0000-4000-8000-000000000002")

    async def prepare_database() -> None:
        await initialize_status_store(database)

        await save_investigation_status(
            database, first_id, "completed"
        )

        await save_investigation_status(
            database, second_id, "failed", "Test failure"
        )

    asyncio.run(prepare_database())

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database

        response = client.get("/investigations?limit=1")

    assert response.status_code == 200

    history = response.json()

    assert len(history) == 1
    assert history[0]["investigation_id"] == str(second_id)
    assert history[0]["status"] == "failed"
    assert history[0]["error"] == "Test failure"


def test_list_investigations_empty_history(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"
    asyncio.run(initialize_status_store(database))

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database
        response = client.get("/investigations")

    assert response.status_code == 200
    assert response.json() == []


def test_list_investigations_invalid_limit() -> None:
    with TestClient(create_app(AsyncMock())) as client:
        response_low = client.get("/investigations?limit=0")
        response_high = client.get("/investigations?limit=101")

    assert response_low.status_code == 422
    assert response_high.status_code == 422

def test_get_investigation_events(tmp_path: Path) -> None:
    database = tmp_path / "statuses.sqlite"
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000060"
    )

    async def prepare() -> None:
        await initialize_status_store(database)
        await save_investigation_status(
            database, investigation_id, "queued"
        )
        await save_investigation_status(
            database, investigation_id, "running"
        )
        await save_investigation_status(
            database, investigation_id, "completed"
        )

    asyncio.run(prepare())

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database
        response = client.get(
            f"/investigations/{investigation_id}/events"
        )

    assert response.status_code == 200

    events = response.json()

    assert [event["status"] for event in events] == [
        "queued",
        "running",
        "completed",
    ]

    assert len(events) == 3
    assert all(event["occurred_at"] for event in events)
    assert all(
        event["investigation_id"] == str(investigation_id)
        for event in events
    )

    assert [event["event_id"] for event in events] == sorted(
        event["event_id"] for event in events
    )


def test_get_unknown_investigation_events(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"
    asyncio.run(initialize_status_store(database))

    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000061"
    )

    with TestClient(create_app(AsyncMock())) as client:
        client.app.state.status_db = database
        response = client.get(
            f"/investigations/{investigation_id}/events"
        )

    assert response.status_code == 404
