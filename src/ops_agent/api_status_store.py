
from pathlib import Path
from uuid import UUID

import aiosqlite

from ops_agent.api_models import (
    InvestigationLifecycleStatus,
    InvestigationStatusResponse,
)
from ops_agent.api_models import (
    InvestigationLifecycleStatus,
    InvestigationStatusResponse,
    InvestigationEventResponse,
)
from typing import Literal
from ops_agent.api_models import NodeExecutionResponse


async def list_investigation_statuses(
    database_path: Path,
    limit: int = 20,
) -> list[InvestigationStatusResponse]:
    if not database_path.is_file():
        return []

    async with aiosqlite.connect(str(database_path)) as db:
        async with db.execute(
            """
            SELECT investigation_id, status, error
            FROM investigations
            ORDER BY rowid DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        InvestigationStatusResponse(
            investigation_id=UUID(row[0]),
            status=row[1],
            error=row[2],
        )
        for row in rows
    ]


async def initialize_status_store(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(database_path)) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS node_executions (
                execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                investigation_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                outcome TEXT NOT NULL CHECK (
                    outcome IN (
                        'completed',
                        'failed',
                        'interrupted'
                    )
                ),
                started_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL CHECK (
                    duration_ms >= 0
                ),
                error_type TEXT
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_executions
            ON node_executions (
                investigation_id,
                execution_id
            )
        """)

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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS investigation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                investigation_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'queued',
                        'running',
                        'awaiting_approval',
                        'completed',
                        'failed'
                    )
                ),
                error TEXT,
                occurred_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_investigation_events
            ON investigation_events (investigation_id, event_id)
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

        await db.execute(
            """
            INSERT INTO investigation_events (
                investigation_id, status, error
            )
            VALUES (?, ?, ?)
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


async def read_investigation_events(
    database_path: Path,
    investigation_id: UUID,
) -> list[InvestigationEventResponse]:
    if not database_path.is_file():
        return []

    async with aiosqlite.connect(str(database_path)) as db:
        async with db.execute(
            """
            SELECT event_id, status, error, occurred_at
            FROM investigation_events
            WHERE investigation_id = ?
            ORDER BY event_id ASC
            """,
            (str(investigation_id),),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        InvestigationEventResponse(
            event_id=row[0],
            investigation_id=investigation_id,
            status=row[1],
            error=row[2],
            occurred_at=row[3],
        )
        for row in rows
    ]

async def save_node_execution(
    database_path: Path,
    investigation_id: UUID,
    node_name: str,
    outcome: Literal["completed", "failed", "interrupted"],
    started_at: str,
    duration_ms: int,
    error_type: str | None = None,
) -> None:
    async with aiosqlite.connect(str(database_path)) as db:
        await db.execute(
            """
            INSERT INTO node_executions (
                investigation_id,
                node_name,
                outcome,
                started_at,
                duration_ms,
                error_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(investigation_id),
                node_name,
                outcome,
                started_at,
                duration_ms,
                error_type,
            ),
        )
        await db.commit()

async def read_node_executions(
    database_path: Path,
    investigation_id: UUID,
) -> list[NodeExecutionResponse]:
    if not database_path.is_file():
        return []

    async with aiosqlite.connect(str(database_path)) as db:
        async with db.execute(
            """
            SELECT
                execution_id,
                node_name,
                outcome,
                started_at,
                duration_ms,
                error_type
            FROM node_executions
            WHERE investigation_id = ?
            ORDER BY execution_id ASC
            """,
            (str(investigation_id),),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        NodeExecutionResponse(
            execution_id=row[0],
            investigation_id=investigation_id,
            node_name=row[1],
            outcome=row[2],
            started_at=row[3],
            duration_ms=row[4],
            error_type=row[5],
        )
        for row in rows
    ]
