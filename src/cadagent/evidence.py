"""Shared integrity screen for source-bound CAD and PCB report records."""
import hashlib
from pathlib import Path


def hashes_are_current(root: Path, data: dict) -> bool:
    """Check declared project-local hash maps; legacy records may omit them.

    This verifies bytes, not the truth of a reported physical or CAD result.
    A declared empty/invalid hash map fails instead of silently dropping evidence.
    """
    root = Path(root).resolve()
    try:
        for key in ('source_sha256', 'report_sha256', 'mechanical_sources', 'artifact_sha256'):
            if key not in data:
                continue
            values = data[key]
            if not isinstance(values, dict) or not values:
                return False
            for relative, expected in values.items():
                path = (root / relative).resolve()
                if root not in path.parents or not path.is_file():
                    return False
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    return False
        return True
    except (OSError, TypeError, ValueError):
        return False
