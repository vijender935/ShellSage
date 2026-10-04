"""Cloud-hosted MCP server for the Agent.

Provides a streamable HTTP MCP endpoint suitable for Render and remote MCP clients.

Security defaults:
  - HTTP mode REQUIRES AGENT_API_TOKEN (Bearer header or ?token= query).
    Set ALLOW_UNAUTHENTICATED=1 to explicitly opt out (not recommended).
  - `run_command` is only exposed when ENABLE_SHELL=1, and even then it is
    restricted by the allowlist policy (see core/safety.py).
  - `delete_path` is only exposed when ENABLE_DELETE=1.
  - git_status / git_diff / git_log are read-only and always available.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Callable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    from mcp.server import FastMCP  # type: ignore
    from mcp.server.transport_security import TransportSecuritySettings

from config.settings import WORKSPACE
from core.tools import execute_tool, tool_names
from mcp_local.auth import BearerAuthMiddleware
from security.audit import log_tool_call

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


ENABLE_SHELL = _flag("ENABLE_SHELL")
ENABLE_DELETE = _flag("ENABLE_DELETE")
_AUTH_STATE = "n/a (stdio)"

mcp = FastMCP(
    "Agent",
    instructions=(
        "You are connected to a cloud-hosted agent. "
        f"File operations are restricted to the workspace: {WORKSPACE}. "
        "Shell and delete tools are only available if the operator enabled them. "
        "run_command takes ONE simple allowlisted command (no pipes, &&, ;, redirects). "
        "Use destructive operations carefully."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _tool_if(enabled: bool) -> Callable:
    """Register the function as an MCP tool only when *enabled* is true."""
    def decorator(fn):
        return mcp.tool()(fn) if enabled else fn
    return decorator


def _run(name: str, args: dict[str, Any], *, source: str = "mcp") -> dict[str, Any]:
    started = time.perf_counter()
    result = execute_tool(name, args)
    duration = (time.perf_counter() - started) * 1000
    log_tool_call(name, args, result, source=source, duration_ms=round(duration, 1))
    return result


@mcp.tool()
def list_files(path: str = ".") -> dict[str, Any]:
    """List files and folders in the agent workspace."""
    return _run("list_files", {"path": path})

@mcp.tool()
def create_folder(name: str) -> dict[str, Any]:
    """Create a folder in the agent workspace."""
    return _run("create_folder", {"name": name})

@mcp.tool()
def create_file(path: str, content: str = "") -> dict[str, Any]:
    """Create or replace a text file in the agent workspace."""
    return _run("create_file", {"path": path, "content": content})

@mcp.tool()
def read_file(path: str) -> dict[str, Any]:
    """Read a text file from the agent workspace."""
    return _run("read_file", {"path": path})

@mcp.tool()
def write_file(path: str, content: str) -> dict[str, Any]:
    """Overwrite an existing text file in the agent workspace."""
    return _run("write_file", {"path": path, "content": content})

@mcp.tool()
def copy_file(source: str, destination: str) -> dict[str, Any]:
    """Copy a file inside the agent workspace."""
    return _run("copy_file", {"source": source, "destination": destination})

@mcp.tool()
def move_file(source: str, destination: str) -> dict[str, Any]:
    """Move or rename a file or folder inside the agent workspace."""
    return _run("move_file", {"source": source, "destination": destination})

@_tool_if(ENABLE_DELETE)
def delete_path(path: str) -> dict[str, Any]:
    """Delete a file or folder recursively inside the agent workspace."""
    return _run("delete_path", {"path": path})

@_tool_if(ENABLE_SHELL)
def run_command(command: str, timeout: int = 30) -> dict[str, Any]:
    """Run ONE simple allowlisted command in the agent workspace (no pipes, &&, ;, redirects)."""
    return _run("run_command", {"command": command, "timeout": timeout})

@mcp.tool()
def git_status() -> dict[str, Any]:
    """Show git status (short format, with branch) of the workspace repo."""
    return _run("git_status", {})

@mcp.tool()
def git_diff(path: str = "", staged: bool = False) -> dict[str, Any]:
    """Show git diff of the workspace repo (optionally one path, or staged changes)."""
    return _run("git_diff", {"path": path, "staged": staged})

@mcp.tool()
def git_log(count: int = 10) -> dict[str, Any]:
    """Show recent commits (one per line, max 100)."""
    return _run("git_log", {"count": count})

@mcp.tool()
def agent_status() -> str:
    """Return basic agent status and workspace information."""
    exposed = [
        n for n in tool_names()
        if not (n == "run_command" and not ENABLE_SHELL)
        and not (n == "delete_path" and not ENABLE_DELETE)
    ]
    return (
        "Agent is online.\n"
        f"Workspace: {WORKSPACE}\n"
        f"Auth: {_AUTH_STATE}\n"
        f"Shell: {'ENABLED' if ENABLE_SHELL else 'disabled'}\n"
        f"Delete: {'ENABLED' if ENABLE_DELETE else 'disabled'}\n"
        f"Tools: {', '.join(exposed)}"
    )


def main() -> None:
    global _AUTH_STATE
    parser = argparse.ArgumentParser(description="Cloud Agent MCP Server")
    parser.add_argument("--http", action="store_true", help="Use streamable HTTP")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    if not args.http:
        mcp.run(transport="stdio")
        return

    token = os.getenv("AGENT_API_TOKEN", "").strip()
    if not token and not _flag("ALLOW_UNAUTHENTICATED"):
        sys.exit(
            "Refusing to start: AGENT_API_TOKEN is not set.\n"
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
            "(or set ALLOW_UNAUTHENTICATED=1 to run without auth - not recommended)."
        )

    app = mcp.streamable_http_app()
    if token:
        app = BearerAuthMiddleware(app, token)
        _AUTH_STATE = "ENABLED (Bearer / ?token=)"
    else:
        _AUTH_STATE = "DISABLED (ALLOW_UNAUTHENTICATED=1)"

    import uvicorn
    # access_log off: the ?token= query string must not end up in logs.
    uvicorn.run(app, host=args.host, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
