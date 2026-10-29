import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from ops_agent.models import CIResult
from ops_agent.report_parser import parse_failed_tests
from secrets import randbelow
from datetime import datetime, timezone
import os
import shutil


def main() -> None:
    docker_executable = (
        os.environ.get("OPS_DOCKER_EXECUTABLE")
        or shutil.which("docker")
    )

    if docker_executable is None:
        raise RuntimeError(
            "Docker executable not found. Set OPS_DOCKER_EXECUTABLE."
        )
    project_dir = Path(__file__).resolve().parents[2]

    identifier = uuid4()
    run_id = randbelow(2**63 - 1) + 1
    report_dir = project_dir / "runtime" / "runs" / identifier.hex
    report_dir.mkdir(parents=True)

    xml_path = report_dir / "pytest.xml"
    print(f"Report folder: {report_dir}", flush=True)
    started_at = datetime.now(timezone.utc).isoformat()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "integration_tests/test_backend.py",
            "-q",
            f"--junitxml={xml_path}",
        ],
        cwd=project_dir,
        check=False,
    )
    finished_at = datetime.now(timezone.utc).isoformat()


    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"Pytest did not complete normally: exit code {result.returncode}. "
            f"Inspect output and reports in {report_dir}."
        )

    failed_tests = parse_failed_tests(xml_path, run_id=run_id)
    ci = CIResult(
        run_id=run_id,
        service="backend",
        status="passed" if result.returncode == 0 else "failed",
    )

    (report_dir / "ci_run.json").write_text(
        ci.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (report_dir / "failed_tests.json").write_text(
        failed_tests.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(f"Local check status: {ci.status}")
    logs_result = subprocess.run(
        [
            docker_executable,
            "compose",
            "logs",
            "--no-color",
            "--no-log-prefix",
            "--timestamps",
            "--since",
            started_at,
            "--until",
            finished_at,
            "backend",
        ],
        cwd=project_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    if logs_result.returncode != 0:
        raise RuntimeError(
            f"Cannot collect backend logs: {logs_result.stderr.strip()}"
        )

    (report_dir / "backend.log").write_text(
        logs_result.stdout,
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()