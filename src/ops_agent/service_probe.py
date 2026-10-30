from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, ValidationError

from ops_agent.models import ServiceStatus


class ReadinessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    service: Literal["backend"]
    status: Literal["ready", "not_ready"]


def probe_backend() -> ServiceStatus:
    health = ServiceStatus(
        service="backend",
        environment="local",
        status="unknown",
    )

    try:
        try:
            with urlopen(
                "http://127.0.0.1:8000/ready",
                timeout=5,
            ) as response:
                http_status = response.status
                body = response.read()
        except HTTPError as error:
            with error:
                http_status = error.code
                body = error.read()

        payload = ReadinessPayload.model_validate_json(body)

    except (URLError, OSError, TimeoutError, ValidationError):
        return health

    if http_status == 200 and payload.status == "ready":
        health.status = "healthy"
    elif http_status == 503 and payload.status == "not_ready":
        health.status = "degraded"

    return health