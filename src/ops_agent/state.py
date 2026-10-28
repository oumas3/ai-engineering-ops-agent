from typing import Literal, TypedDict

from ops_agent.models import (
    CIResult,
    CreatedIssue,
    FailedTestsReport,
    IssueProposal,
    LogsReport,
    ServiceStatus,
)
from uuid import uuid4


class InvestigationState(TypedDict):
    service: str
    environment: Literal["local", "staging", "production"]
    ci: CIResult | None
    failed_tests: FailedTestsReport | None
    logs: LogsReport | None
    service_status: ServiceStatus | None
    errors: list[str]
    issue_proposal: IssueProposal | None
    approval_decision: Literal["approved", "rejected"] | None
    issue_request_id: str
    created_issue: CreatedIssue | None


def create_initial_state(
    service: str,
    environment: Literal["local", "staging", "production"],
) -> InvestigationState:
    return {
        "service": service,
        "environment": environment,
        "ci": None,
        "failed_tests": None,
        "logs": None,
        "service_status": None,
        "errors": [],
        "issue_proposal": None,
        "approval_decision": None,
        "issue_request_id": str(uuid4()),
        "created_issue": None,

        
    }