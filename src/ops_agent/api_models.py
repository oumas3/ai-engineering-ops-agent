from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool
from typing import Literal
class StartInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_run: UUID
    analyse: StrictBool = False

class StartInvestigationResponse(BaseModel):
    investigation_id: UUID

from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    InvestigationAnalysis,
    IssueProposal,
    LogsReport,
    ServiceStatus,
)

class InvestigationResultResponse(BaseModel):
    investigation_id: UUID
    service: str
    environment: str
    ci: CIResult | None
    failed_tests: FailedTestsReport | None
    logs: LogsReport | None
    service_status: ServiceStatus | None
    analysis: InvestigationAnalysis | None
    issue_proposal: IssueProposal | None
    errors: list[str]

class InvestigationDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]