"""Shared test utilities: add src/ to sys.path so tests run without `pip install -e .`."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def temp_dir(name: str) -> str:
    """Return a unique temp dir under /tmp and create it."""
    import tempfile
    base = tempfile.mkdtemp(prefix=f"cfm_test_{name}_")
    return base
