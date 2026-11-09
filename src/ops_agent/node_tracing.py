
import asyncio
import inspect
import logging
import time

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langgraph.errors import GraphInterrupt

from ops_agent.api_status_store import save_node_execution
from ops_agent.state import InvestigationState


logger = logging.getLogger(__name__)

NodeResult = dict[str, object]
NodeFunction = Callable[
    [InvestigationState],
    NodeResult | Awaitable[NodeResult],
]


def trace_node(
    node_name: str,
    node: NodeFunction,
    *,
    database_path: Path,
    investigation_id: UUID,
) -> Callable[[InvestigationState], Awaitable[NodeResult]]:
    """Wrap a graph node with execution tracing."""

    async def traced(state: InvestigationState) -> NodeResult:
        started_at = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

        started_ns = time.perf_counter_ns()

        outcome = "failed"
        error_type = None

        try:
            result = node(state)

            if inspect.isawaitable(result):
                result = await result

            outcome = "completed"
            return result

        except GraphInterrupt:
            outcome = "interrupted"
            raise

        except asyncio.CancelledError:
            error_type = "CancelledError"
            raise

        except Exception as error:
            error_type = type(error).__name__
            raise

        finally:
            duration_ms = max(
                0,
                (time.perf_counter_ns() - started_ns) // 1_000_000,
            )

            try:
                await save_node_execution(
                    database_path=database_path,
                    investigation_id=investigation_id,
                    node_name=node_name,
                    outcome=outcome,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    error_type=error_type,
                )
            except Exception:
                logger.exception(
                    "Unable to save trace for node %s",
                    node_name,
                )

    return traced
