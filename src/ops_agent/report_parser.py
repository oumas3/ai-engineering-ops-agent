from pathlib import Path
from xml.etree import ElementTree

from ops_agent.models import FailedTest, FailedTestsReport, LogEntry, LogsReport
import re

def parse_failed_tests(
    path: Path,
    run_id: int,
) -> FailedTestsReport:
    root = ElementTree.parse(path).getroot()
    tests: list[FailedTest] = []

    for case in root.iter("testcase"):
        problem = case.find("failure")

        if problem is None:
            problem = case.find("error")

        if problem is None:
            continue

        name = case.get("name")
        if not name:
            raise ValueError("A failed test case is missing its name.")

        message = (
            problem.get("message")
            or problem.text
            or "Pytest reported a failure without details."
        )

        tests.append(
            FailedTest(
                name=name,
                message=message.strip(),
            )
        )

    return FailedTestsReport(
        run_id=run_id,
        tests=tests,
    )

def parse_backend_logs(
    path: Path,
    run_id: int,
    service: str,
) -> LogsReport:
    entries: list[LogEntry] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        match = re.fullmatch(
            r"(?P<timestamp>\S+)\s+"
            r"(?P<level>INFO|WARNING|ERROR):\s+"
            r"(?P<message>.+)",
            line,
        )

        if match is None:
            raise ValueError(f"Unsupported backend log format: {line}")

        entries.append(
            LogEntry(
                level=match.group("level"),
                message=(
                    f"{match.group('timestamp')} "
                    f"{match.group('message')}"
                ),
            )
        )

    return LogsReport(
        run_id=run_id,
        service=service,
        entries=entries,
    ) 


