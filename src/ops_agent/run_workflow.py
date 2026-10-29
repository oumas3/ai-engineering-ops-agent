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
from ops_agent.models import AgentPermissions
from langgraph.types import Command

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
    parser.add_argument(
        "--allow-create-issue",
        action="store_true",
        help="Permit issue creation, subject to human approval.",
    )
    mode.add_argument(
        "--approve",
        action="store_true",
        help="Approve the saved issue proposal.",
    )
    mode.add_argument(
        "--reject",
        action="store_true",
        help="Reject the saved issue proposal.",
    )
    parser.add_argument(
        "--report-run",
        help="Select a generated local report folder by its UUID.",
    )
    args = parser.parse_args()

    if args.pause_before_tests and (
        args.inspect or args.resume or args.approve or args.reject
    ):
        parser.error(
            "--pause-before-tests is only available for a new execution."
        )

    if (args.approve or args.reject) and not args.allow_create_issue:
        parser.error(
            "Include --allow-create-issue to load the approval workflow."
        )
    serializer = create_serializer()
    src_dir = Path(__file__).resolve().parents[1]
    server_env = {"PYTHONPATH": str(src_dir)}

    if args.report_run is not None:
        server_env["OPS_REPORT_RUN"] = args.report_run
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env=server_env,
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
                permissions=AgentPermissions(
                can_create_issue=args.allow_create_issue,
                ),
            )
            if args.inspect or args.resume or args.approve or args.reject:
                snapshot = await graph.aget_state(config)

                if not snapshot.values:
                    print("No saved investigation found.")
                    return

                awaiting_decision = any(
                    task.interrupts for task in snapshot.tasks
                )

                if args.inspect:
                    final_state = snapshot.values

                elif args.approve or args.reject:
                    if not awaiting_decision:
                        print("No approval decision is pending.")
                        return

                    decision = "approved" if args.approve else "rejected"
                    final_state = await graph.ainvoke(
                        Command(resume=decision),
                        config=config,
                    )

                else:
                    if awaiting_decision:
                        print("Use --approve or --reject for this pause.")
                        return

                    if not snapshot.next:
                        print("Investigation already completed; nothing to resume.")
                        return

                    final_state = await graph.ainvoke(None, config=config)
            else:
                final_state = await graph.ainvoke(
                    initial_state,
                    config=config,
                )
            snapshot = await graph.aget_state(config)
            print("Saved service:", snapshot.values["service"])
            print("Next nodes:", snapshot.next)
            if any(task.interrupts for task in snapshot.tasks):
                print("Waiting for a human approval decision.")

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
    decision = final_state.get("approval_decision")
    issue = final_state.get("created_issue")
    if issue is not None:
        print("Created local issue:", issue.issue_id)
    if decision is not None:
        print("Approval decision:", decision)

    for error in final_state["errors"]:
        print(f"Investigation error: {error}")

    proposal = final_state.get("issue_proposal")

    if proposal is not None:
        print("\nProposed issue:")
        print(proposal.title)
        print(proposal.description)


if __name__ == "__main__":
    asyncio.run(main())