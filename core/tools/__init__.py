"""
Tool registry – single place that maps names to callables + schemas.
"""

from __future__ import annotations

from typing import Any, Callable

from core.tools import filesystem, git, shell, verify

TOOL_MAP: dict[str, Callable[..., dict[str, Any]]] = {
    "list_files": filesystem.list_files,
    "create_folder": filesystem.create_folder,
    "create_file": filesystem.create_file,
    "read_file": filesystem.read_file,
    "write_file": filesystem.write_file,
    "copy_file": filesystem.copy_file,
    "move_file": filesystem.move_file,
    "delete_path": filesystem.delete_path,
    "run_command": shell.run_command,
    "run_tests": verify.run_tests,
    "git_status": git.git_status,
    "git_diff": git.git_diff,
    "git_log": git.git_log,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and folders in a directory (non-recursive).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path inside workspace. Default: '.'",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Create a new folder (parents are created automatically).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Folder name or relative path"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new text file (overwrites if it already exists).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full content of a text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Overwrite an existing text file. Use create_file for new files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file to another location inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file/folder inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_path",
            "description": "Delete a file or folder (recursive). Destructive – use carefully.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Execute ONE simple command inside the workspace (no pipes, &&, ;, "
                "redirects or $(...)). Only allowlisted commands are permitted "
                "(e.g. ls, cat, grep, find, git, pytest, python script.py)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "A single command with arguments",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30, max 90)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Run the project's test suite (pytest) in the workspace. Returns pass/fail, "
                "counts, the failing test ids and the tail of the output. Call this after "
                "changing code to verify it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Test file or folder (optional, default: whole suite)",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Only run tests matching this expression (pytest -k)",
                    },
                    "fail_fast": {
                        "type": "boolean",
                        "description": "Stop at the first failure",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git status (short format, with branch).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff of the working tree (or staged changes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Limit the diff to this file/folder (optional)",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "Show staged changes instead of unstaged",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent commits, one per line.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "How many commits (default 10, max 100)",
                    }
                },
            },
        },
    },
]

def execute_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a registered tool with validated keyword arguments."""
    if name not in TOOL_MAP:
        return {"success": False, "error": f"Unknown tool: {name}"}

    fn = TOOL_MAP[name]
    kwargs = dict(args or {})
    try:
        return fn(**kwargs)
    except TypeError as exc:
        return {"success": False, "error": f"Invalid arguments for {name}: {exc}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

def tool_names() -> list[str]:
    """Return the names of all registered tools."""
    return list(TOOL_MAP.keys())
