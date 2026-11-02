import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import aiosqlite
from groq import AsyncGroq
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from mcp import Client, StdioServerParameters

from ops_agent.api_runner import InvestigationJob
from ops_agent.models import AgentPermissions
from ops_agent.persistence import create_serializer
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph


async def execute_investigation(job: InvestigationJob) -> None:
    src_dir = Path(__file__).resolve().parents[1]
    runtime_dir = src_dir.parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={
            "PYTHONPATH": str(src_dir),
            "OPS_REPORT_RUN": job.report_run.hex,
        },
    )

    async with AsyncExitStack() as stack:
        connection = await stack.enter_async_context(
            aiosqlite.connect(str(runtime_dir / "checkpoints.sqlite"))
        )
        checkpointer = AsyncSqliteSaver(connection, serde=create_serializer())
        mcp_client = await stack.enter_async_context(Client(params))

        llm_client = None
        if job.analyse:
            llm_client = await stack.enter_async_context(
                AsyncGroq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)
            )

        graph = build_graph(
            mcp_client,
            checkpointer=checkpointer,
            llm_client=llm_client,
            permissions=AgentPermissions(can_create_issue=False),
        )

        await graph.ainvoke(
            create_initial_state("backend", "local"),
            config={"configurable": {"thread_id": str(job.investigation_id)}},
        )