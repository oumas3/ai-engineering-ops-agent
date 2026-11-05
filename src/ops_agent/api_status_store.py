
from pathlib import Path
from uuid import UUID

import aiosqlite

from ops_agent.api_models import (
    InvestigationLifecycleStatus,
    InvestigationStatusResponse,
)


async def initialize_status_store(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(database_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS investigations (
                investigation_id TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'queued',
                        'running',
                        'awaiting_approval',
                        'completed',
                        'failed'
                    )
                ),
                error TEXT
            )
        """)
        await db.commit()


async def save_investigation_status(
    database_path: Path,
    investigation_id: UUID,
    status: InvestigationLifecycleStatus,
    error: str | None = None,
) -> None:
    async with aiosqlite.connect(str(database_path)) as db:
        await db.execute(
            """
            INSERT INTO investigations (
                investigation_id, status, error
            )
            VALUES (?, ?, ?)
            ON CONFLICT(investigation_id)
            DO UPDATE SET
                status = excluded.status,
                error = excluded.error
            """,
            (str(investigation_id), status, error),
        )
        await db.commit()


async def read_investigation_status(
    database_path: Path,
    investigation_id: UUID,
) -> InvestigationStatusResponse | None:
    if not database_path.is_file():
        return None

    async with aiosqlite.connect(str(database_path)) as db:
        cursor = await db.execute(
            """
            SELECT status, error
            FROM investigations
            WHERE investigation_id = ?
            """,
            (str(investigation_id),),
        )
        row = await cursor.fetchone()
        await cursor.close()

    if row is None:
        return None

    return InvestigationStatusResponse(
        investigation_id=investigation_id,
        status=row[0],
        error=row[1],
    )
