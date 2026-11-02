from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool


class StartInvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_run: UUID
    analyse: StrictBool = False

class StartInvestigationResponse(BaseModel):
    investigation_id: UUID