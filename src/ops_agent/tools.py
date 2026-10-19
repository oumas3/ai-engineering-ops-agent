from pathlib import Path

from ops_agent.models import CIResult


def get_ci_status(path: Path) -> CIResult:
    """Load and validate a CI result from a local JSON file."""
    content = path.read_text(encoding="utf-8")
    return CIResult.model_validate_json(content)