from pathlib import Path
from uuid import UUID


class ReportRunNotFound(Exception):
    pass


def find_report_directory(runs_dir: Path, report_run: UUID) -> Path:
    directory = runs_dir / report_run.hex

    if not directory.is_dir():
        raise ReportRunNotFound(f"Report run {report_run} was not found.")

    return directory