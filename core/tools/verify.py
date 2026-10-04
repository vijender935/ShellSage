"""
Test runner tool: runs the project's tests through the normal shell policy and
returns a compact, structured result the agent can act on.

Base command: `pytest -q --tb=short` (override with TEST_COMMAND, e.g.
TEST_COMMAND="python -m pytest -q --tb=short"). The command still has to pass
the shell allowlist, so it is no more powerful than run_command.
"""

from __future__ import annotations

import os
import re
import shlex
from typing import Any

from core.tools.shell import run_command

_COUNT_RE = re.compile(
    r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)"
)
_SUMMARY_HINT = re.compile(r"\b(\d+\s+(passed|failed|errors?)|no tests ran)\b")
_FAILED_RE = re.compile(r"^(FAILED|ERROR)\s+\S.*$")
_LABELS = {"error": "errors", "warning": "warnings"}


def _base_command() -> list[str]:
    raw = os.getenv("TEST_COMMAND", "").strip()
    if raw:
        try:
            parts = shlex.split(raw)
            if parts:
                return parts
        except ValueError:
            pass
    return ["pytest", "-q", "--tb=short"]


def parse_pytest_output(text: str) -> dict[str, Any]:
    """Extract the summary line, counts and failed test ids from pytest output."""
    lines = (text or "").splitlines()

    summary = ""
    for line in reversed(lines):
        if _SUMMARY_HINT.search(line):
            summary = line.strip("= ").strip()
            break

    counts: dict[str, int] = {}
    for number, label in _COUNT_RE.findall(summary):
        key = _LABELS.get(label, label)
        counts[key] = counts.get(key, 0) + int(number)

    failed = [ln.strip() for ln in lines if _FAILED_RE.match(ln)][:20]
    return {"summary": summary, "counts": counts, "failed_tests": failed}


def run_tests(
    path: str = "",
    keyword: str = "",
    fail_fast: bool = False,
    timeout: int = 90,
) -> dict[str, Any]:
    """Run the test suite in the workspace. Returns pass/fail, counts and failing tests."""
    path = (path or "").strip()
    if path.startswith("-"):
        return {"success": False, "error": "path must not start with '-'"}

    args = _base_command()
    if fail_fast:
        args.append("-x")
    if keyword:
        args += ["-k", keyword]
    if path:
        args.append(path)

    result = run_command(shlex.join(args), timeout=timeout)
    if "returncode" not in result:  # blocked by policy, timeout, or launch error
        return result

    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    combined = (stdout + ("\n" + stderr if stderr else "")).strip()
    parsed = parse_pytest_output(stdout or combined)

    rc = result["returncode"]
    no_tests = rc == 5 or "no tests ran" in parsed["summary"]
    summary = parsed["summary"] or ("no tests collected" if no_tests else f"exit code {rc}")

    return {
        "success": rc == 0,
        "returncode": rc,
        "no_tests": no_tests,
        "summary": summary,
        "counts": parsed["counts"],
        "failed_tests": parsed["failed_tests"],
        "output_tail": combined[-3000:],
        "command": result.get("command", ""),
    }
