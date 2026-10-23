import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph


async def main() -> None:
    src_dir = Path(__file__).resolve().parents[1]

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={"PYTHONPATH": str(src_dir)},
    )

    initial_state = create_initial_state("backend", "staging")
   
    async with Client(params) as client:
        graph = build_graph(client)
        final_state = await graph.ainvoke(initial_state)

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