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
    