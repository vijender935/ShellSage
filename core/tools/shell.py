"""
Controlled shell command execution inside the workspace.

Default: allowlist policy (core/safety.py) + shell=False.
SHELL_UNRESTRICTED=1 restores the old shell=True behaviour.
Secrets (tokens / API keys) are stripped from the child environment.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Mapping

from config.settings import (
    COMMAND_TIMEOUT_DEFAULT,
    COMMAND_TIMEOUT_MAX,
    MAX_COMMAND_OUTPUT,
    WORKSPACE,
)
from core.safety import evaluate_command, is_risky_command

_SECRET_MARKERS = ("TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "PASSWD", "CREDENTIAL")


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"success": True, **kwargs}


def _err(msg: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error": msg, **extra}


def _child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for child processes, without anything that looks like a secret."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(marker in k.upper() for marker in _SECRET_MARKERS)
    }
    env.update(extra or {})
    return env


def run_command(command: str, timeout: int | None = None) -> dict[str, Any]:
    """
    Run a command inside the agent workspace.

    The command must pass the allowlist policy (unless SHELL_UNRESTRICTED=1).
    Output is truncated. Timeout is clamped.
    """
    command = (command or "").strip()
    if not command:
        return _err("Command is empty.")

    decision = evaluate_command(command)
    if not decision.allowed:
        return _err(f"Blocked by shell policy: {decision.reason}", command=command)

    t = timeout if timeout is not None else COMMAND_TIMEOUT_DEFAULT
    t = max(1, min(int(t), COMMAND_TIMEOUT_MAX))

    run_kwargs: dict[str, Any] = dict(
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=t,
        env=_child_env(decision.env_extra),
        stdin=subprocess.DEVNULL,
    )

    try:
        if decision.argv:
            result = subprocess.run(list(decision.argv), shell=False, **run_kwargs)
        else:  # unrestricted mode
            result = subprocess.run(command, shell=True, **run_kwargs)

        stdout = (result.stdout or "")[-MAX_COMMAND_OUTPUT:]
        stderr = (result.stderr or "")[-MAX_COMMAND_OUTPUT:]

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "command": command,
            "timeout": t,
            "policy": decision.reason,
            "risky": is_risky_command(command),
        }
    except subprocess.TimeoutExpired:
        return _err(f"Command timed out after {t}s: {command}")
    except Exception as e:
        return _err(str(e))
