from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CIResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: int = Field(gt=0)
    service: str = Field(min_length=1)
    status: Literal["passed", "failed", "running"]