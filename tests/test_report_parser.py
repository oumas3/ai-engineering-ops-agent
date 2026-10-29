from pathlib import Path

from ops_agent.report_parser import parse_failed_tests


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