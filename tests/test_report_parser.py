from pathlib import Path

from ops_agent.report_parser import parse_failed_tests
from ops_agent.report_parser import parse_backend_logs, parse_failed_tests


def test_parser_extracts_failed_test(tmp_path: Path) -> None:
    path = tmp_path / "results.xml"
    path.write_text(
        """
        <testsuites>
            <testsuite tests="2" failures="1" errors="0" skipped="0">
                <testcase name="test_liveness" />
                <testcase name="test_readiness">
                    <failure message="Expected HTTP 200, received HTTP 503." />
                </testcase>
            </testsuite>
        </testsuites>
        """,
        encoding="utf-8",
    )

    report = parse_failed_tests(path, run_id=101)

    assert report.run_id == 101
    assert len(report.tests) == 1
    assert report.tests[0].name == "test_readiness"
    assert report.tests[0].message == (
        "Expected HTTP 200, received HTTP 503."
    )
def test_parser_extracts_test_error(tmp_path: Path) -> None:
    path = tmp_path / "results.xml"
    path.write_text(
        """
        <testsuites>
            <testsuite tests="1" failures="0" errors="1" skipped="0">
                <testcase name="test_readiness">
                    <error message="Connection refused." />
                </testcase>
            </testsuite>
        </testsuites>
        """,
        encoding="utf-8",
    )

    report = parse_failed_tests(path, run_id=102)

    assert len(report.tests) == 1
    assert report.tests[0].name == "test_readiness"
    assert report.tests[0].message == "Connection refused."
def test_parser_extracts_backend_logs(tmp_path: Path) -> None:
    path = tmp_path / "backend.log"
    path.write_text(
        "2026-10-29T16:19:47.351680156Z ERROR:    "
        "Database readiness check failed: TimeoutError\n"
        "2026-10-29T16:19:47.352488399Z INFO:     "
        '172.18.0.1:52398 - "GET /ready HTTP/1.1" '
        "503 Service Unavailable\n",
        encoding="utf-8",
    )

    report = parse_backend_logs(
        path,
        run_id=103,
        service="backend",
    )

    assert report.run_id == 103
    assert report.service == "backend"
    assert len(report.entries) == 2

    assert report.entries[0].level == "ERROR"
    assert report.entries[0].message == (
        "2026-10-29T16:19:47.351680156Z "
        "Database readiness check failed: TimeoutError"
    )

    assert report.entries[1].level == "INFO"
    assert "503 Service Unavailable" in report.entries[1].message