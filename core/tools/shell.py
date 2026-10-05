"""
Controlled command execution inside the workspace.
Commands are always parsed with shlex and executed with shell=False.
"""
from __future__ import annotations
import os
import subprocess
from typing import Any, Mapping
from config.settings import COMMAND_TIMEOUT_DEFAULT, COMMAND_TIMEOUT_MAX, MAX_COMMAND_OUTPUT, WORKSPACE
from core.safety import evaluate_command, is_risky_command

_SECRET_MARKERS = ("TOKEN", "SECRET", "API_KEY", "APIKEY", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTHORIZATION")
_SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"

def _err(msg: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error": msg, **extra}

def _child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not any(m in k.upper() for m in _SECRET_MARKERS)}
    for key, value in (extra or {}).items():
        if not any(m in str(key).upper() for m in _SECRET_MARKERS):
            env[str(key)] = str(value)
    env["PATH"] = _SAFE_PATH
    env.setdefault("HOME", "/tmp")
    env["PYTHONNOUSERSITE"] = "1"
    return env

def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(proc.pid, 15)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.terminate()
    except (ProcessLookupError, OSError):
        pass

def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        try:
            os.killpg(proc.pid, 9)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass

def run_command(command: str, timeout: int | None = None) -> dict[str, Any]:
    command = (command or "").strip()
    if not command:
        return _err("Command is empty.")
    decision = evaluate_command(command)
    if not decision.allowed:
        return _err(f"Blocked by shell policy: {decision.reason}", command=command)
    t = timeout if timeout is not None else COMMAND_TIMEOUT_DEFAULT
    t = max(1, min(int(t), COMMAND_TIMEOUT_MAX))
    argv = list(decision.argv)
    if not argv:
        return _err("Shell execution is disabled; commands must use the allowlist.", command=command)
    proc = None
    try:
        proc = subprocess.Popen(
            argv, cwd=str(WORKSPACE), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, env=_child_env(decision.env_extra),
            start_new_session=(os.name == "posix"),
        )
        stdout, stderr = proc.communicate(timeout=t)
        return {
            "success": proc.returncode == 0, "returncode": proc.returncode,
            "stdout": (stdout or "")[-MAX_COMMAND_OUTPUT:],
            "stderr": (stderr or "")[-MAX_COMMAND_OUTPUT:],
            "command": command, "timeout": t, "policy": decision.reason,
            "risky": is_risky_command(command),
        }
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            _terminate_process_tree(proc)
            try:
                proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_process_tree(proc)
                proc.communicate()
        return _err(
            f"Command timed out after {t}s: {command}", command=command, timeout=t,
            stdout=str(exc.output or "")[-MAX_COMMAND_OUTPUT:],
            stderr=str(exc.stderr or "")[-MAX_COMMAND_OUTPUT:],
        )
    except Exception as exc:
        if proc is not None:
            _kill_process_tree(proc)
        return _err(str(exc), command=command)
