from unittest.mock import AsyncMock
from uuid import UUID

from fastapi.testclient import TestClient

from ops_agent.api import create_app
from pathlib import Path

from ops_agent.api_models import (
    InvestigationResultResponse,
    StartInvestigationRequest,
)

from ops_agent.report_store import find_report_directory
from ops_agent.api_runner import InvestigationRunner


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

def test_start_queues_the_requested_report(tmp_path: Path) -> None:
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