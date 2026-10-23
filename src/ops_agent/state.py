from typing import Literal, TypedDict

from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    LogsReport,
    ServiceStatus,
)


class InvestigationState(TypedDict):
    service: str
    environment: Literal["local", "staging", "production"]
    ci: CIResult | None
    failed_tests: FailedTestsReport | None
    logs: LogsReport | None
    service_status: ServiceStatus | None
    errors: list[str]


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
    }