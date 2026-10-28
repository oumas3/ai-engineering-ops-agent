from pathlib import Path

import pytest
from pydantic import ValidationError

from ops_agent.tools import get_ci_status, get_failed_tests,read_logs ,get_service_status
from uuid import uuid4

from ops_agent.models import IssueProposal
from ops_agent.tools import create_issue

def test_loads_ci_result(tmp_path: Path) -> None:
    path = tmp_path / "ci_run.json"
    path.write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )

    result = get_ci_status(path)

    assert result.run_id == 42
    assert result.service == "backend"
    assert result.status == "failed"


def test_rejects_invalid_file_data(tmp_path: Path) -> None:
    path = tmp_path / "ci_run.json"
    path.write_text(
        '{"run_id": 42, "service": "backend", "status": "broken"}',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        get_ci_status(path)
def test_missing_ci_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        get_ci_status(path)

def test_loads_failed_tests_report(tmp_path: Path) -> None:
    path = tmp_path / "failed_tests.json"
    path.write_text(
        """
        {
            "run_id": 42,
            "tests": [
                {
                    "name": "test_health_endpoint",
                    "message": "Expected HTTP 200, received HTTP 503."
                }
            ]
        }
        """,
        encoding="utf-8",
    )

    report = get_failed_tests(path)

    assert report.run_id == 42
    assert len(report.tests) == 1
    assert report.tests[0].name == "test_health_endpoint"
    assert report.tests[0].message == (
        "Expected HTTP 200, received HTTP 503."
    )


def test_loads_logs_report(tmp_path: Path) -> None:
    path = tmp_path / "logs.json"
    path.write_text(
        """
        {
            "run_id": 42,
            "service": "backend",
            "entries": [
                {
                    "level": "ERROR",
                    "message": "Database connection timed out."
                }
            ]
        }
        """,
        encoding="utf-8",
    )

    report = read_logs(path)

    assert report.run_id == 42
    assert report.service == "backend"
    assert len(report.entries) == 1
    assert report.entries[0].level == "ERROR"
    assert report.entries[0].message == "Database connection timed out."


def test_loads_service_status(tmp_path: Path) -> None:
    path = tmp_path / "service_status.json"
    path.write_text(
        """
        {
            "service": "backend",
            "environment": "staging",
            "status": "degraded"
        }
        """,
        encoding="utf-8",
    )

    report = get_service_status(path)

    assert report.service == "backend"
    assert report.environment == "staging"
    assert report.status == "degraded"
def test_create_issue_does_not_duplicate_same_request(
    tmp_path: Path,
) -> None:
    proposal = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )
    request_id = uuid4()
    directory = tmp_path / "issues"

    first = create_issue(proposal, directory, request_id)
    second = create_issue(proposal, directory, request_id)

    assert first == second
    assert first.issue_id == str(request_id)
    assert len(list(directory.glob("*.json"))) == 1

def test_create_issue_rejects_changed_content_for_same_request(
    tmp_path: Path,
) -> None:
    request_id = uuid4()
    directory = tmp_path / "issues"

    original = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )
    changed = IssueProposal(
        run_id=42,
        service="backend",
        title="Different issue title",
        description="The health test received HTTP 503.",
    )

    first = create_issue(original, directory, request_id)

    with pytest.raises(
        ValueError,
        match="Request ID already exists with different issue content.",
    ):
        create_issue(changed, directory, request_id)

    restored = create_issue(original, directory, request_id)

    assert restored == first
    assert len(list(directory.glob("*.json"))) == 1