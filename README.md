# AI Engineering Operations Agent

[![Python Tests](https://github.com/oumas3/ai-engineering-ops-agent/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/oumas3/ai-engineering-ops-agent/actions/workflows/tests.yml)

A stateful engineering operations agent for investigating CI failures using validated evidence, MCP tools, LangGraph workflows, SQLite persistence, optional LLM analysis, and human approval for write actions.

Built as an incremental **AI engineering and reliability** project: evidence is collected before hypotheses are proposed, and write operations require explicit permission and approval.

**Project status:** Parts 1–20 implemented. GitHub Actions runs the full suite (**129 tests**) and the agent evaluation scorecard (**8 scenarios, 48/48 checks**) on Ubuntu and Windows for every pull request. The 100% evaluation score covers only these deterministic scenarios; it is not a measure of real-world root-cause accuracy.

## What it does

- Accepts an existing report-run UUID and queues an investigation through FastAPI.
- Uses a custom MCP server to collect CI status, failed tests, application logs, and service health.
- Validates evidence with Pydantic and checks CI run, service, and environment consistency.
- Uses LangGraph for stateful, conditional execution. A passing CI report ends the investigation early; a failed report triggers further evidence collection.
- Handles bounded read-tool timeouts and preserves useful partial evidence when collection fails.
- Optionally generates structured observations, hypotheses, recommended checks, and limitations using Groq.
- Prepares an issue proposal and requires explicit human approval before creating a **local JSON issue record**.
- Persists checkpoints, investigation lifecycle history, timestamps, and node-level execution traces in SQLite.
- Exposes a browser dashboard for starting, reviewing, approving/rejecting, and reopening investigations.

**Not a production incident-remediation service:** evidence sources are local, issue creation is local, and LLM hypotheses are not validated root causes.

## Architecture

```mermaid
flowchart TD
    UI[Browser dashboard] --> API[FastAPI]
    CLIENT[API client] --> API
    API --> RUNNER[Async investigation queue]
    RUNNER --> GRAPH[LangGraph workflow]
    GRAPH --> MCP[MCP client / local MCP server]
    MCP --> EVIDENCE[CI, tests, logs, service health]
    GRAPH --> LLM[Optional Groq analysis]
    GRAPH --> PROPOSAL[Issue proposal]
    PROPOSAL --> APPROVAL{Write enabled and human approved?}
    APPROVAL -->|Yes| ISSUE[Local issue JSON]
    APPROVAL -->|No| END[Finish without issue]
    GRAPH <--> CHECKPOINTS[(SQLite checkpoints)]
    RUNNER --> OBS[(SQLite statuses and lifecycle events)]
    GRAPH --> OBS
    API --> OBS
    API --> CHECKPOINTS
```

### Execution and approval model

For a failed CI run, the graph can execute:

```text
collect_ci
  -> collect_failed_tests
  -> collect_logs
  -> collect_service_status
  -> collect_analysis (optional)
  -> prepare_issue
  -> request_approval (only when issue creation is enabled)
  -> create_issue (only after approval)
```

The approval node can interrupt the graph. After a user approves or rejects, the investigation resumes from its persisted checkpoint. An approval does not bypass server-side permission checks.

## Requirements

- Python **3.12**
- Windows PowerShell for the commands below (the Python code itself is not Windows-specific)
- Dependencies from `requirements.txt`

Runtime components include FastAPI, Uvicorn, Pydantic, LangGraph, the MCP Python SDK, SQLite checkpointing, Groq, and HTTPX.

## Quick start (PowerShell)

### 1. Install

```powershell
git clone https://github.com/oumas3/ai-engineering-ops-agent.git
cd ai-engineering-ops-agent

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

### 2. Create a local demonstration report run

The API only accepts report-run IDs that already exist under `runtime/runs/<run-id-without-hyphens>/`. Generated runtime data is not committed to Git.

The repository contains sample evidence in `data/`. Copy it into a new run directory:

```powershell
$runId = [guid]::NewGuid().ToString("N")
$runDir = "runtime/runs/$runId"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
Copy-Item "data/*.json" $runDir

# The investigation executor uses the 'local' environment.
# Align the copied service-health fixture for a consistent demo.
$healthPath = "$runDir/service_status.json"
$health = Get-Content $healthPath -Raw | ConvertFrom-Json
$health.environment = "local"
$health | ConvertTo-Json -Depth 5 | Set-Content $healthPath

Write-Host "Demo report run: $runId"
```

The bundled CI example is a failed backend run, so it exercises evidence collection and proposal generation. Keep the printed `$runId` for the next step.

### 3. Start FastAPI and open the dashboard

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn ops_agent.api:create_app --factory --reload
```

Open:

- **Dashboard:** http://127.0.0.1:8000/
- **API documentation:** http://127.0.0.1:8000/docs

Paste your newly generated report-run ID into the dashboard and select **Start investigation**. Optional AI analysis is disabled by default.

Or submit it through PowerShell in a second terminal:

```powershell
$body = @{ report_run = $runId; analyse = $false } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/investigations" -ContentType "application/json" -Body $body
```

If you open a new terminal, define `$runId` again using the ID printed earlier.

The POST returns HTTP **202 Accepted** and an `investigation_id`. The investigation runs asynchronously; its results become available through the API and dashboard as execution progresses.

### Optional: enable AI analysis

Set `GROQ_API_KEY` in the environment before starting the server, then submit an investigation with `analyse` set to `true`.

```powershell
$env:GROQ_API_KEY = "<your-key>"
```

Do not commit API keys or local `.env` files. If `analyse=true` is requested without a configured Groq key, the API rejects the request.

### Optional: enable issue creation

Issue creation is **disabled by default**. To enable the approval path, set the flag before starting FastAPI:

```powershell
$env:OPS_ALLOW_CREATE_ISSUE = "1"
```

A failed CI investigation with a proposal can then pause for human approval. Approval or rejection is submitted from the dashboard or through `POST /investigations/{investigation_id}/decision`.

Approved issues are written only to `runtime/issues/` as local JSON records. The agent does **not** automatically create GitHub Issues, apply patches, or deploy fixes.

## HTTP API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/investigations` | Queue a new investigation; returns `202` and its UUID |
| `GET` | `/investigations?limit=20` | List recent investigations; validated limit 1–100 |
| `GET` | `/investigations/{id}` | Retrieve the latest persisted evidence snapshot |
| `GET` | `/investigations/{id}/status` | Read current lifecycle status |
| `GET` | `/investigations/{id}/events` | Read timestamped lifecycle events in order |
| `GET` | `/investigations/{id}/metrics` | Read calculated execution duration |
| `GET` | `/investigations/{id}/traces` | Read node executions and durations |
| `GET` | `/investigations/{id}/approval` | Check whether approval is pending and enabled |
| `POST` | `/investigations/{id}/decision` | Approve or reject a pending write decision |
| `GET` | `/` | Browser dashboard |

An investigation's lifecycle status is one of `queued`, `running`, `awaiting_approval`, `completed`, or `failed`.

### Observability

The dashboard displays investigation history, lifecycle progress, timestamped events, execution duration, and a node execution trace table.

Each node trace contains:

- Node name and investigation UUID
- Outcome: `completed`, `failed`, or `interrupted`
- Start timestamp and duration in milliseconds
- Exception type when applicable, without exposing exception-message contents

Execution duration is calculated from the `running` lifecycle event to the first terminal/approval event; it **excludes time waiting for human approval**. Node traces record individual node execution attempts, including interrupted and resumed attempts.

Older investigations created before event tracing may have empty event or trace histories.

## Persistence and local files

| Path | Purpose |
|---|---|
| `data/` | Tracked sample engineering evidence |
| `runtime/runs/<run-id>/` | Local report-run input files |
| `runtime/checkpoints.sqlite` | Persisted LangGraph checkpoints |
| `runtime/investigation_statuses.sqlite` | Investigation statuses, lifecycle events, and node traces |
| `runtime/issues/` | Locally created, approved issue records |
| `src/ops_agent/workflow.py` | LangGraph graph construction and routing |
| `src/ops_agent/nodes.py` | Evidence, analysis, approval, and write nodes |
| `src/ops_agent/mcp_server.py` | Custom MCP tool server |
| `src/ops_agent/api.py` | FastAPI routes and lifecycle |
| `src/ops_agent/api_runner.py` | Queued investigation worker |
| `src/ops_agent/api_executor.py` | Graph invocation and checkpoint management |
| `src/ops_agent/api_decisions.py` | Approval checks and graph resumption |
| `src/ops_agent/api_status_store.py` | SQLite status, event, and trace persistence |
| `src/ops_agent/node_tracing.py` | Node timing and failure/interrupt tracing |
| `src/ops_agent/observability.py` | Execution-duration calculations |
| `src/ops_agent/web/index.html` | Browser dashboard |
| `tests/` | Automated tests |
| `evals/scenarios.json` | Deterministic agent evaluation scenarios |
| `evals/metrics.py` | Behaviour and safety metrics |
| `evals/run.py` | Evaluation runner and JSON scorecard |
| `evals/results/` | Generated scorecards (ignored by Git) |
| `.github/workflows/tests.yml` | CI: tests and evaluations on Ubuntu and Windows |

The `runtime/` directory, `.env` files, pytest temporary folders, and `evals/results/` are ignored by Git.

## Testing

Activate the environment and run:

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q --basetemp=.\.pytest-tmp-all
git diff --check
```

Pytest requires the `--basetemp` folder not to exist yet; use a new name if a previous run left one behind.

The suite has **129 tests**. They cover validation, MCP integration, conditional routing, read-tool timeouts, SQLite checkpointing, approval and issue-creation safeguards, HTTP responses, lifecycle events, duration calculations, node tracing, interrupts, resumption, trace-storage failures, and the evaluation framework itself.

## Agent evaluation

Unit tests check that individual functions work. The evaluation framework checks that the **agent as a whole makes the right decisions** for a given situation.

```powershell
$env:PYTHONPATH = "src"
python -m evals.run
```

Each scenario in `evals/scenarios.json` feeds mocked MCP tool responses into the real LangGraph workflow. A scenario can also inject tool faults (`"faults": {"read_logs": "timeout"}`) or play the human approver (`"approval": "approved"`); approval scenarios enable issue creation and write any issue to a temporary directory, never to `runtime/`.

| Scenario | Expected behaviour |
|---|---|
| `ci_passes` | A passing CI run ends the investigation after one tool call |
| `ci_failure_with_evidence` | A failed run collects tests, logs, and service health, then proposes an issue that cites the evidence and states its uncertainty |
| `mismatched_log_run` | Logs from a different CI run are rejected and do not contaminate the proposal |
| `logs_timeout` | A timed-out logs tool is retried once; other evidence is kept and the gap is disclosed |
| `failed_tests_tool_error` | A failing tool is not retried, and no test failures are invented |
| `malformed_ci_payload` | Invalid CI data is rejected and the investigation stops without a proposal |
| `approval_rejected` | With write permission on, a human rejection prevents issue creation |
| `approval_approved` | With write permission on, a human approval creates exactly one local issue |

Every scenario is scored on six checks:

| Metric | What it verifies |
|---|---|
| Routing | The exact sequence of tool calls |
| CI interpretation | The CI status was read correctly, or invalid CI data was rejected when rejection is expected |
| Proposal accuracy | A proposal exists only when one is expected |
| Error handling | The expected errors were recorded |
| Evidence integrity | Required evidence is present and forbidden evidence is absent |
| Write safety | An issue was created if and only if the scenario expects one |

The runner prints a summary, writes `evals/results/latest.json`, and exits with a non-zero code if any scenario fails, so CI fails on a regression. Current result: **8/8 scenarios, 48/48 checks**.

**Scope of the score:** these are a small set of deterministic, hand-written scenarios. A 100% score shows that known behaviours have not regressed; it does not measure accuracy on arbitrary real-world failures.

## Continuous integration

`.github/workflows/tests.yml` runs on every push to `master` and every pull request targeting `master`:

- Matrix: `ubuntu-latest` and `windows-latest`, Python 3.12
- Read-only repository permissions
- Runs the full pytest suite, then `python -m evals.run`
- Uploads each platform's scorecard as an artifact (`agent-evaluation-<os>`, kept for 14 days), even when an earlier step fails

## Design and safety principles

1. **Validate at boundaries.** Pydantic checks the structure of external evidence, and the workflow verifies matching run/service/environment identifiers.
2. **Separate evidence from inference.** AI hypotheses and recommended checks are labelled as unverified.
3. **Preserve partial evidence.** An unavailable tool should not discard evidence from successful sources.
4. **Require explicit approval for writes.** Issue creation requires server permission, a proposal, and a human decision.
5. **Observe without deciding.** Trace-storage failures are logged rather than used to change a node's decision.

This project is intended for **local development and evaluation**. The API does not currently implement production-grade authentication or remote issue-tracker integration. Do not expose its write-enabled interface directly to the public internet.

## Development roadmap

| Milestone | Status |
|---|---|
| Parts 1–11: evidence collection, MCP, LangGraph, persistence, approval, LLM analysis | Complete |
| Part 12: asynchronous FastAPI interface | Complete |
| Part 12B: browser dashboard | Complete |
| Part 13: investigation lifecycle status tracking | Complete |
| Part 14: investigation history and reopening results | Complete |
| Part 15: lifecycle observability and duration metrics | Complete |
| Part 16: LangGraph node-level tracing | Complete |
| Part 17: automated CI on Ubuntu and Windows | Complete |
| Part 18: agent evaluation scenarios and CI scorecards | Complete |
| Part 19: documentation refresh | Complete |
| Part 20: evaluation hardening (fault injection, approval scenarios, falsifiable metrics) | Complete |

## Current limitations

- Inputs and issue outputs are local rather than connected to production CI or issue trackers.
- The evidence-gathering workflow is predefined; dynamic model-driven tool planning is not implemented.
- LLM analysis is optional and should not be treated as verified root cause.
- Dependency versions are not fully locked for reproducible installs.
- The evaluation set is small (eight hand-written scenarios), and evidence integrity uses substring matching. Duplicate approval decisions and resumption after a server restart are not yet evaluated.
- The investigation queue is in memory; queued jobs that have not started are lost if the server stops.
- Cancellation is currently recorded as a failed node with `CancelledError`, and stopping an async wrapper cannot forcibly stop synchronous work already running in a thread.
- Node-trace persistence is best-effort; a successful node can still complete if its trace could not be saved.

## Development workflow

Features are developed in dedicated branches, tested locally, and proposed through pull requests into `master`. Every pull request must pass the CI tests and evaluation scorecard before merge. The next engineering priorities are **broader evaluation scenarios, queue and approval reliability, and reproducible dependency installs**.
