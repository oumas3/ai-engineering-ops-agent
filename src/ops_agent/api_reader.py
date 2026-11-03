from pathlib import Path
from uuid import UUID

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ops_agent.api_models import InvestigationResultResponse
from ops_agent.persistence import create_serializer


async def read_investigation(
    investigation_id: UUID,
    database_path: Path,
) -> InvestigationResultResponse | None:
    if not database_path.is_file():
        return None

    config = {"configurable": {"thread_id": str(investigation_id)}}

    async with aiosqlite.connect(str(database_path)) as connection:
        saver = AsyncSqliteSaver(connection, serde=create_serializer())
        saved = await saver.aget_tuple(config)

    if saved is None:
        return None

    values = saved.checkpoint["channel_values"]

    # An early checkpoint can exist before the initial state is applied.
    if "service" not in values or "environment" not in values:
        return None

    return InvestigationResultResponse(
        investigation_id=investigation_id,
        service=values["service"],
        environment=values["environment"],
        ci=values.get("ci"),
        failed_tests=values.get("failed_tests"),
        logs=values.get("logs"),
        service_status=values.get("service_status"),
        analysis=values.get("analysis"),
        issue_proposal=values.get("issue_proposal"),
        errors=values.get("errors", []),
    )