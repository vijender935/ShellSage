"""
Read-only git tools. They go through run_command, so the same shell policy
(allowlist, path checks, no hooks/fsmonitor) applies.
"""

from __future__ import annotations

import shlex
from typing import Any

from core.tools.shell import run_command


def _git(args: list[str], timeout: int = 30) -> dict[str, Any]:
    return run_command(shlex.join(["git", *args]), timeout=timeout)


def git_status() -> dict[str, Any]:
    """Short git status with branch info."""
    return _git(["status", "--short", "--branch"])


def git_diff(path: str = "", staged: bool = False) -> dict[str, Any]:
    """Git diff (working tree, or staged changes). Optionally limited to one path."""
    args = ["diff", "--no-ext-diff", "--no-textconv"]
    if staged:
        args.append("--staged")
    if path:
        args += ["--", path]
    return _git(args)


def git_log(count: int = 10) -> dict[str, Any]:
    """Recent commits, one per line (max 100)."""
    try:
        n = int(count)
    except (TypeError, ValueError):
        n = 10
    n = max(1, min(n, 100))
    return _git(["log", "--oneline", "--decorate", "-n", str(n)])
