"""Test bootstrap: point the agent at a throwaway workspace BEFORE settings import."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AGENT_WORKSPACE"] = tempfile.mkdtemp(prefix="shellsage-test-ws-")
os.environ.pop("AGENT_EXTRA_ROOTS", None)


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Isolated workspace root wired into core.workspace."""
    import core.workspace as w

    root = (tmp_path / "ws").resolve()
    root.mkdir()
    monkeypatch.setattr(w, "WORKSPACE", root)
    monkeypatch.setattr(w, "ALLOWED_ROOTS", [root])
    return root
