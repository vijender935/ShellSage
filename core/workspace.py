"""
Path sandbox – every file operation must go through safe_path().

Supports multiple allowed roots:
  - Primary WORKSPACE (for relative paths + shell cwd)
  - Extra roots from AGENT_EXTRA_ROOTS (e.g. /sdcard/Download)

`.git` internals are protected: file tools cannot read or write inside a .git
folder (a writable .git/config or hooks dir would allow code execution through
git). Git is used only via the dedicated git tools / allowlisted `git` command.
"""

from __future__ import annotations

from pathlib import Path

from config.settings import ALLOWED_ROOTS, WORKSPACE

PROTECTED_COMPONENTS = frozenset({".git"})


class PathEscapeError(Exception):
    """Raised when a path tries to leave the allowed workspaces."""


def _is_under_any_root(target: Path) -> Path | None:
    """Return the matching root if target is inside any ALLOWED_ROOTS, else None."""
    for root in ALLOWED_ROOTS:
        try:
            target.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def safe_path(path: str | Path | None = ".") -> Path:
    """
    Resolve *path* and ensure it stays inside one of the ALLOWED_ROOTS.

    - Relative paths are resolved against the primary WORKSPACE.
    - Absolute paths are accepted only if they fall under an allowed root.
    - Paths inside a `.git` directory are refused.
    - Raises PathEscapeError on any attempt to escape.
    """
    if path is None or str(path).strip() == "":
        path = "."

    raw = str(path).replace("\x00", "")
    p = Path(raw)

    if p.is_absolute():
        target = p.resolve()
    else:
        # Relative → always under primary workspace
        target = (WORKSPACE / raw).resolve()

    matched_root = _is_under_any_root(target)
    if matched_root is None:
        roots_str = ", ".join(str(r) for r in ALLOWED_ROOTS)
        raise PathEscapeError(
            f"Access denied: '{path}' is outside the allowed roots ({roots_str})"
        )

    for part in target.relative_to(matched_root).parts:
        if part.lower() in PROTECTED_COMPONENTS:
            raise PathEscapeError(
                f"Access denied: '{path}' is inside protected git internals (.git)"
            )

    return target


def rel_to_workspace(path: Path) -> str:
    """
    Return a readable relative path.
    Prefers primary WORKSPACE; falls back to the matched extra root.
    """
    try:
        rel = path.relative_to(WORKSPACE)
        return str(rel) if str(rel) != "." else "."
    except ValueError:
        pass

    for root in ALLOWED_ROOTS:
        try:
            rel = path.relative_to(root)
            # Show as absolute-ish so user knows which root it belongs to
            return f"{root.name}/{rel}" if str(rel) != "." else str(root)
        except ValueError:
            continue

    return str(path)
