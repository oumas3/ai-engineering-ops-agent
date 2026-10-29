from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
import logging
import os

import asyncpg
from fastapi import FastAPI, Response

logger = logging.getLogger("uvicorn.error")
DATABASE_URL = os.environ["DATABASE_URL"]

class LivenessResponse(BaseModel):
    service: Literal["backend"] = "backend"
    status: Literal["alive"] = "alive"


app = FastAPI(title="Operations Demo Backend")


@app.get("/live", response_model=LivenessResponse)
async def check_liveness() -> LivenessResponse:
    return LivenessResponse()

class ReadinessResponse(BaseModel):
    service: Literal["backend"] = "backend"
    status: Literal["ready", "not_ready"]
@app.get("/ready", response_model=ReadinessResponse)
async def check_readiness(response: Response) -> ReadinessResponse:
    try:
        connection = await asyncpg.connect(
            DATABASE_URL,
            timeout=2,
            command_timeout=2,
        )

        try:
            await connection.fetchval("SELECT 1")
        finally:
            await connection.close(timeout=1)

    except (OSError, asyncpg.PostgresError, TimeoutError) as error:
        logger.error(
            "Database readiness check failed: %s",
            type(error).__name__,
        )
        response.status_code = 503
        return ReadinessResponse(status="not_ready")

    return ReadinessResponse(status="ready")