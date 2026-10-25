"""Lazy import of the optional CAD dependencies, failing loudly when absent."""

from __future__ import annotations

import importlib
from types import ModuleType

INSTALL_HINT = (
    "install the extra (pip install -e '.[cad]' in the cad-agent checkout) or "
    "run cad-agent with the CAD project's own python"
)

class MissingDependency(RuntimeError):
    """An optional CAD dependency is not importable; the work was not done."""

def require(module: str, purpose: str) -> ModuleType:
    """Import ``module`` or raise ``MissingDependency`` saying what could not run."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise MissingDependency(
            f"{purpose} needs '{module}', which is not importable ({exc}); {INSTALL_HINT}"
        ) from exc
