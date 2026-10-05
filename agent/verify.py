"""
Verification loop for the local agent: edit -> test -> fix.

VerifyTracker watches tool calls during one user turn. When the model tries to
finish (no more tool calls) but it changed files without running tests since,
or the last test run failed, the loop sends it a nudge instead of accepting the
answer. Nudges are capped so the agent can never get stuck.

Env:
  AUTO_VERIFY=0          disable the nudges
  VERIFY_MAX_NUDGES=2    max nudges per user turn
"""

from __future__ import annotations

import os
from typing import Any

_FALSE = {"0", "false", "no", "off"}

DIRTY_MESSAGE = (
    "[verification] You changed files but have not run the tests since. "
    "Call run_tests now (and git_diff to review your changes). If the project has "
    "no tests, say so explicitly in your final answer."
)
FAILED_MESSAGE = (
    "[verification] The last run_tests call failed. Read the failing tests, fix the "
    "cause, and run run_tests again. If you cannot fix it, explain exactly what is "
    "failing instead of claiming success."
)


class VerifyTracker:
    MUTATING = frozenset(
        {"create_file", "write_file", "copy_file", "move_file", "delete_path"}
    )

    def __init__(self, max_nudges: int = 2, enabled: bool = True) -> None:
        self.max_nudges = max_nudges
        self.enabled = enabled
        self.new_turn()

    @classmethod
    def from_env(cls) -> "VerifyTracker":
        enabled = os.getenv("AUTO_VERIFY", "1").strip().lower() not in _FALSE
        try:
            max_nudges = int(os.getenv("VERIFY_MAX_NUDGES", "2"))
        except ValueError:
            max_nudges = 2
        return cls(max_nudges=max_nudges, enabled=enabled)

    def new_turn(self) -> None:
        self.dirty = False
        self.last_tests_ok: bool | None = None
        self.nudges = 0

    def observe(self, name: str, result: dict[str, Any]) -> None:
        if name in self.MUTATING and result.get("success"):
            self.dirty = True
        elif name == "run_tests":
            if "returncode" not in result or result.get("no_tests"):
                # blocked by policy / timeout / no tests: cannot verify, do not nag
                self.dirty = False
                self.last_tests_ok = None
            else:
                self.dirty = False
                self.last_tests_ok = bool(result.get("success"))

    def pending_message(self) -> str | None:
        """Message to send instead of accepting a final answer, or None."""
        if not self.enabled or self.nudges >= self.max_nudges:
            return None
        if self.dirty:
            message = DIRTY_MESSAGE
        elif self.last_tests_ok is False:
            message = FAILED_MESSAGE
        else:
            return None
        self.nudges += 1
        return message
