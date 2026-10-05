"""
Path sandbox. Every file operation must go through safe_path().
Symlink components are rejected to reduce symlink-swap/TOCTOU escapes.
"""
from __future__ import annotations
from pathlib import Path
from config.settings import ALLOWED_ROOTS, WORKSPACE

PROTECTED_COMPONENTS = frozenset({".git"})

class PathEscapeError(Exception):
    pass

def _is_under_any_root(target: Path) -> Path | None:
    for root in ALLOWED_ROOTS:
        try:
            target.relative_to(root)
            return root
        except ValueError:
            continue
    return None

def _reject_symlink_components(candidate: Path, root: Path) -> None:
    try:
        rel = candidate.absolute().relative_to(root)
    except ValueError:
        return
    current = root
    for part in rel.parts:
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        try:
            if current.is_symlink():
                raise PathEscapeError(
                    f"Access denied: symlink path components are not allowed ({current.name!r})"
                )
        except OSError as exc:
            raise PathEscapeError(f"Access denied while checking path: {exc}") from exc

def safe_path(path: str | Path | None = ".") -> Path:
    if path is None or str(path).strip() == "":
        path = "."
    raw = str(path)
    if "\x00" in raw:
        raise PathEscapeError("Access denied: NUL bytes are not valid in paths")
    p = Path(raw)
    lexical = p.absolute() if p.is_absolute() else (WORKSPACE / p)
    roots = ALLOWED_ROOTS if p.is_absolute() else (WORKSPACE,)

    for root in roots:
        try:
            lexical.relative_to(root)
        except ValueError:
            continue
        _reject_symlink_components(lexical, root)
        break

    target = lexical.resolve(strict=False)
    matched_root = _is_under_any_root(target)
    if matched_root is None:
        roots_str = ", ".join(str(r) for r in ALLOWED_ROOTS)
        raise PathEscapeError(f"Access denied: {path!r} is outside the allowed roots ({roots_str})")
    for part in target.relative_to(matched_root).parts:
        if part.lower() in PROTECTED_COMPONENTS:
            raise PathEscapeError(f"Access denied: {path!r} is inside protected git internals (.git)")
    return target

def rel_to_workspace(path: Path) -> str:
    try:
        rel = path.relative_to(WORKSPACE)
        return str(rel) if str(rel) != "." else "."
    except ValueError:
        pass
    for root in ALLOWED_ROOTS:
        try:
            rel = path.relative_to(root)
            return f"{root.name}/{rel}" if str(rel) != "." else str(root)
        except ValueError:
            continue
    return str(path)
