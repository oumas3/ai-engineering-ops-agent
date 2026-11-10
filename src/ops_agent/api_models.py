from typing import Annotated, Literal
from uuid import UUID
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    PlainSerializer,
    StrictBool,
)

from ops_agent.models import (
    FailedTest,
    InvestigationAnalysis,
    LogEntry,
    ServiceStatus,
)


SafeRunId = Annotated[
    int,
    PlainSerializer(
        lambda value: str(value),
        return_type=str,
        when_used="json",
    ),
]


class StartInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_run: UUID
    analyse: StrictBool = False


class StartInvestigationResponse(BaseModel):
    investigation_id: UUID


class CIResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: SafeRunId
    service: str
    status: Literal["passed", "failed", "running"]


class FailedTestsReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: SafeRunId
    tests: list[FailedTest]


class LogsReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: SafeRunId
    service: str
    entries: list[LogEntry]


class IssueProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: SafeRunId
    service: str
    title: str
    description: str


class InvestigationResultResponse(BaseModel):
    investigation_id: UUID
    service: str
    environment: str
    ci: CIResultResponse | None
    failed_tests: FailedTestsReportResponse | None
    logs: LogsReportResponse | None
    service_status: ServiceStatus | None
    analysis: InvestigationAnalysis | None
    issue_proposal: IssueProposalResponse | None
    errors: list[str]


class ApprovalStatusResponse(BaseModel):
    approval_pending: bool
    issue_creation_enabled: bool

class InvestigationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]


InvestigationLifecycleStatus = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
]


class InvestigationStatusResponse(BaseModel):
    investigation_id: UUID
    status: InvestigationLifecycleStatus
    error: str | None = None


class InvestigationEventResponse(BaseModel):
    event_id: int
    investigation_id: UUID
    status: InvestigationLifecycleStatus
    error: str | None = None
    occurred_at: datetime

class InvestigationMetricsResponse(BaseModel):
    investigation_id: UUID
    execution_duration_ms: int | None

class NodeExecutionResponse(BaseModel):
    execution_id: int
    investigation_id: UUID
    node_name: str
    outcome: Literal["completed", "failed", "interrupted"]
    started_at: datetime
    duration_ms: int
    error_type: str | None = None
