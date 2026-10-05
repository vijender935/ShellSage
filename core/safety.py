'''Shell command policy.

evaluate_command() decides whether a command may run and returns the exact argv
to execute (shell=False). Because no shell is involved, operators like `;`, `&&`,
`|`, `$(...)` and backticks never get interpreted; we also reject them up front
so the caller gets a clear error instead of silent literal arguments.

is_risky_command() is kept for the local agent's confirmation prompt.
'''
from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from config.settings import RISKY_COMMAND_PATTERNS
from config.shell_policy import GIT_ALLOWED_SUBCOMMANDS, SHELL_ALLOWLIST
from core import workspace as _ws


def is_risky_command(command: str) -> bool:
    """Heuristic check whether a shell command is potentially destructive."""
    cmd = (command or "").strip().lower()
    if not cmd:
        return False
    return any(pat in cmd for pat in RISKY_COMMAND_PATTERNS)


_SHELL_OPERATORS = frozenset(
    {"&&", "||", ";", "|", "&", ">", ">>", "<", "<<", "2>", "2>>", "2>&1", "&>"}
)
_FORBIDDEN_SUBSTRINGS = ("$(", "${")

# Per-command arguments that turn an innocent command into code execution / deletion.
_DENIED_ARGS: dict[str, frozenset[str]] = {
    "find": frozenset(
        {"-exec", "-execdir", "-ok", "-okdir", "-delete",
         "-fprint", "-fprint0", "-fprintf", "-fls"}
    ),
    "python": frozenset({"-c", "-"}),
    "python3": frozenset({"-c", "-"}),
    "git": frozenset(
        {"--hard", "--force", "-f", "--force-with-lease", "-D",
         "--exec-path", "--upload-pack", "--receive-pack", "--output"}
    ),
}

# Prepended to every git call: no fsmonitor, no hooks, no pager.
_GIT_PREFIX = (
    "--no-pager",
    "-c", "core.fsmonitor=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.pager=cat",
)
_GIT_ENV = {"GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"}


@dataclass(frozen=True)
class CommandDecision:
    allowed: bool
    reason: str = ""
    # Exact argv to run with shell=False. Empty when policy is "unrestricted".
    argv: tuple[str, ...] = ()
    env_extra: Mapping[str, str] | None = None


def _deny(reason: str) -> CommandDecision:
    return CommandDecision(False, reason)


def _escapes_workspace(arg: str) -> bool:
    '''True if *arg* looks like a path that leaves the allowed roots (or hits .git).'''
    value = arg
    if arg.startswith("--") and "=" in arg:
        value = arg.split("=", 1)[1]
    elif arg.startswith("-"):
        return False
    if not value:
        return False
    if value.startswith("~"):
        return True

    p = Path(value)
    suspicious = (
        p.is_absolute()
        or ".." in p.parts
        or any(part.lower() in _ws.PROTECTED_COMPONENTS for part in p.parts)
    )
    if not suspicious:
        candidate = _ws.WORKSPACE / p
        try:
            if not (candidate.exists() or candidate.is_symlink()):
                return False  # plain word / pattern / not-yet-existing file
        except OSError:
            return False

    try:
        _ws.safe_path(value)
        return False
    except _ws.PathEscapeError:
        return True


def evaluate_command(command: str) -> CommandDecision:
    cmd = (command or "").strip()
    if not cmd:
        return _deny("empty command")
    try:
        tokens = shlex.split(cmd)
    except ValueError as exc:
        return _deny(f"cannot parse command: {exc}")
    if not tokens:
        return _deny("empty command")

    for tok in tokens:
        if tok in _SHELL_OPERATORS or chr(96) in tok or any(s in tok for s in _FORBIDDEN_SUBSTRINGS):
            return _deny(
                f"shell operators/substitution are not supported ({tok!r}); "
                "run one simple command at a time"
            )

    name, args = tokens[0], tokens[1:]
    if "/" in name or name not in SHELL_ALLOWLIST:
        return _deny(f"command {name!r} is not in the allowlist")

    denied = _DENIED_ARGS.get(name, frozenset())
    for a in args:
        key = a.split("=", 1)[0] if a.startswith("--") else a
        if key in denied:
            return _deny(f"argument {a!r} is not allowed for {name}")

    prefix: tuple[str, ...] = ()
    env_extra: Mapping[str, str] | None = None
    if name == "git":
        if not args or args[0].startswith("-"):
            return _deny("git needs a subcommand first (global options are not allowed)")
        if args[0] not in GIT_ALLOWED_SUBCOMMANDS:
            return _deny(f"git subcommand {args[0]!r} is not allowed")
        prefix = _GIT_PREFIX
        env_extra = _GIT_ENV

    for a in args:
        if _escapes_workspace(a):
            return _deny(f"path argument {a!r} is outside the allowed workspace")

    return CommandDecision(True, "allowlist", (name, *prefix, *args), env_extra)
