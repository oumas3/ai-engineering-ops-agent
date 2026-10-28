from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CIResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: int = Field(gt=0)
    service: str = Field(min_length=1)
    status: Literal["passed", "failed", "running"]
class FailedTest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    message: str = Field(min_length=1)
class FailedTestsReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: int = Field(gt=0)
    tests: list[FailedTest]
class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    level: Literal["INFO", "WARNING", "ERROR"]
    message: str = Field(min_length=1)

class LogsReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: int = Field(gt=0)
    service: str = Field(min_length=1)
    entries: list[LogEntry]
class ServiceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    service: str = Field(min_length=1)
    environment: Literal["local", "staging", "production"]
    status: Literal["healthy", "degraded", "down", "unknown"]
class IssueProposal(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    run_id: int = Field(gt=0)
    service: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
class AgentPermissions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    can_create_issue: bool = False

class CreatedIssue(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    issue_id: str = Field(min_length=1)
    run_id: int = Field(gt=0)
    service: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    