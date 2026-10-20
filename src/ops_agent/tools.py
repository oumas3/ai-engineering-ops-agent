from pathlib import Path

from ops_agent.models import CIResult, FailedTestsReport , LogsReport


def get_ci_status(path: Path) -> CIResult:
    """Load and validate a CI result from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return CIResult.model_validate_json(content)

def get_failed_tests(path: Path) -> FailedTestsReport:
    """Load and validate a failed-tests report from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return FailedTestsReport.model_validate_json(content)

def read_logs(path: Path) -> LogsReport:
    """Load and validate a log report from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return LogsReport.model_validate_json(content)