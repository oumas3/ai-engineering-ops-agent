
import asyncio
import sqlite3
from pathlib import Path
from uuid import UUID

from ops_agent.api_status_store import (
    initialize_status_store,
    read_investigation_status,
    save_investigation_status,
)



def test_status_updates_create_events(tmp_path: Path) -> None:
    database = tmp_path / "statuses.sqlite"
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000050"
    )

    async def prepare() -> None:
        await initialize_status_store(database)
        await save_investigation_status(
            database, investigation_id, "queued"
        )
        await save_investigation_status(
            database, investigation_id, "running"
        )
        await save_investigation_status(
            database, investigation_id, "failed", "Test failure"
        )

    asyncio.run(prepare())

    with sqlite3.connect(database) as db:
        rows = db.execute(
            """
            SELECT status, error, occurred_at
            FROM investigation_events
            WHERE investigation_id = ?
            ORDER BY event_id
            """,
            (str(investigation_id),),
        ).fetchall()

    assert [row[0] for row in rows] == [
        "queued",
        "running",
        "failed",
    ]
    assert rows[-1][1] == "Test failure"
    assert all(row[2].endswith("Z") for row in rows)

    current = asyncio.run(
        read_investigation_status(database, investigation_id)
    )

    assert current is not None
    assert current.status == "failed"
