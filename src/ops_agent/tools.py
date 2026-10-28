from pathlib import Path

from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    LogsReport,
    ServiceStatus,
)
from uuid import UUID

from ops_agent.models import CreatedIssue, IssueProposal

def get_ci_status(path: Path) -> CIResult:
    """Load and validate a CI result from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return CIResult.model_validate_json(content)

def get_service_status(path: Path) -> ServiceStatus:
    """Load and validate a service status from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return ServiceStatus.model_validate_json(content)

def get_failed_tests(path: Path) -> FailedTestsReport:
    """Load and validate a failed-tests report from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return FailedTestsReport.model_validate_json(content)

def read_logs(path: Path) -> LogsReport:
    """Load and validate a log report from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return LogsReport.model_validate_json(content)

def create_issue(
    proposal: IssueProposal,
    directory: Path,
    request_id: UUID,
) -> CreatedIssue:
    directory.mkdir(parents=True, exist_ok=True)

    issue = CreatedIssue(
        issue_id=str(request_id),
        run_id=proposal.run_id,
        service=proposal.service,
        title=proposal.title,
        description=proposal.description,
    )
    path = directory / f"{request_id}.json"

    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(issue.model_dump_json(indent=2))
    except FileExistsError:
        existing = CreatedIssue.model_validate_json(
            path.read_text(encoding="utf-8")
        )

        if existing != issue:
            raise ValueError(
                "Request ID already exists with different issue content."
            )

        return existing

    return issue