from pathlib import Path

import pytest
from pydantic import ValidationError

from ops_agent.tools import get_ci_status, get_failed_tests,read_logs

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