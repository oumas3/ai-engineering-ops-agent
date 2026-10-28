import asyncio
import sys
from pathlib import Path
import argparse
from mcp import Client, StdioServerParameters

from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import aiosqlite

from ops_agent.persistence import create_serializer

async def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--inspect",
        action="store_true",
        help="Read the saved investigation without running the graph.",
    )
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Continue an unfinished saved investigation.",
    )
    parser.add_argument(
            "--thread-id",
            default="investigation-001",
            help="Identify the investigation to run or inspect.",
        )
    parser.add_argument(
        "--pause-before-tests",
        action="store_true",
        help="Pause before collecting failed-test details.",
    )
    args = parser.parse_args()

    if args.pause_before_tests and (args.inspect or args.resume):
        parser.error(
            "--pause-before-tests is only available for a new execution."
        )
    serializer = create_serializer()
    src_dir = Path(__file__).resolve().parents[1]

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={"PYTHONPATH": str(src_dir)},
    )

    initial_state = create_initial_state("backend", "staging")
   
    runtime_dir = Path(__file__).resolve().parents[2] / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    database_path = runtime_dir / "checkpoints.sqlite"

    config = {
        "configurable": {
            "thread_id": args.thread_id,
        }
    }

    async with aiosqlite.connect(str(database_path)) as connection:
        checkpointer = AsyncSqliteSaver(
            connection,
            serde=serializer,
        )
        async with Client(params) as client:
            graph = build_graph(
                client,
                checkpointer=checkpointer,
                interrupt_before=(
                    ["collect_failed_tests"]
                    if args.pause_before_tests
                    else None
                ),
            )
            if args.inspect or args.resume:
                snapshot = await graph.aget_state(config)

                if not snapshot.values:
                    print("No saved investigation found.")
                    return

                if not snapshot.values:
                    print("No saved investigation found.")
                    return

                if args.inspect:
                    final_state = snapshot.values
                else:
                    if not snapshot.next:
                        print("Investigation already completed; nothing to resume.")
                        return

                    final_state = await graph.ainvoke(
                        None,
                        config=config,
                    )
            else:
                final_state = await graph.ainvoke(
                    initial_state,
                    config=config,
                )
            snapshot = await graph.aget_state(config)
            print("Saved service:", snapshot.values["service"])
            print("Next nodes:", snapshot.next)

    ci = final_state["ci"]
    if ci is not None:
        print(f"CI run {ci.run_id}: {ci.status} ({ci.service})")

    report = final_state["failed_tests"]
    if report is not None:
        if not report.tests:
            print("No failed-test details are available.")
        else:
            for test in report.tests:
                print(f"- {test.name}: {test.message}")

    for error in final_state["errors"]:
        print(f"Investigation error: {error}")



if __name__ == "__main__":
    asyncio.run(main())