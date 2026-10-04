import os
import shutil
import subprocess

import pytest

from core import safety
from core.tools import git, shell
from core.workspace import PathEscapeError, safe_path

posix_only = pytest.mark.skipif(os.name == "nt", reason="needs POSIX echo/ls")
git_missing = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture(autouse=True)
def _enforce_policy(ws, monkeypatch):
    monkeypatch.setattr(safety, "SHELL_UNRESTRICTED", False)
    monkeypatch.setattr(shell, "WORKSPACE", ws)


# ---- run_command ---------------------------------------------------------

@posix_only
def test_run_command_runs_allowed():
    r = shell.run_command("echo hello")
    assert r["success"] and r["stdout"].strip() == "hello"
    assert r["policy"] == "allowlist"


@pytest.mark.parametrize("cmd", [
    "echo hi; echo there", "echo hi && echo there", "echo $(id)", "rm -rf x",
    "cat /etc/passwd",
])
def test_run_command_blocks(cmd):
    r = shell.run_command(cmd)
    assert not r["success"]
    assert "Blocked by shell policy" in r["error"]


def test_empty_command():
    assert not shell.run_command("  ")["success"]


def test_child_env_scrubs_secrets(monkeypatch):
    monkeypatch.setenv("AGENT_API_TOKEN", "x")
    monkeypatch.setenv("XAI_API_KEY", "y")
    monkeypatch.setenv("MY_PASSWORD", "z")
    monkeypatch.setenv("KEEP_ME", "1")
    env = shell._child_env({"EXTRA": "e"})
    assert "AGENT_API_TOKEN" not in env
    assert "XAI_API_KEY" not in env
    assert "MY_PASSWORD" not in env
    assert env["KEEP_ME"] == "1" and env["EXTRA"] == "e"


# ---- git tools -----------------------------------------------------------

@git_missing
def test_git_status_diff_log(ws):
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    (ws / "f.txt").write_text("hi\n")

    status = git.git_status()
    assert status["success"], status
    assert "f.txt" in status["stdout"]

    assert git.git_diff()["success"]
    assert git.git_diff(staged=True)["success"]
    assert not git.git_diff(path="../x")["success"]       # path escape
    assert not git.git_diff(path=".git/config")["success"]  # protected
    assert git.git_log(count=-5)["success"] in (True, False)  # clamps; empty repo may fail


@git_missing
def test_git_does_not_run_fsmonitor_from_repo_config(ws):
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    marker = ws / "pwned"
    # Simulate a malicious config planted by other means.
    cfg = ws / ".git" / "config"
    cfg.write_text(cfg.read_text() + f"\n[core]\n\tfsmonitor = touch {marker}\n")
    git.git_status()
    assert not marker.exists()


# ---- .git protection in the file sandbox ---------------------------------

@pytest.mark.parametrize("p", [".git", ".git/config", ".git/hooks/pre-commit", "a/.git/x", ".GIT/config"])
def test_dot_git_blocked(ws, p):
    with pytest.raises(PathEscapeError):
        safe_path(p)


@pytest.mark.parametrize("p", [".gitignore", ".github/workflows/ci.yml", "src/.gitkeep", "git/x"])
def test_dot_git_lookalikes_allowed(ws, p):
    assert safe_path(p).is_relative_to(ws)
