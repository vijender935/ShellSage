"""
Grok (xAI) provider – OpenAI-compatible Chat Completions + tools.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from config.settings import GROK_CHAT_URL, GROK_MODEL, WORKSPACE, XAI_API_KEY
from core.tools import TOOL_SCHEMAS


SYSTEM_INSTRUCTION = f"""
You are a capable, careful AI agent that helps the user manage files and run
commands inside a restricted workspace.

Core rules:
1. Always prefer the provided tools over guessing.
2. Work step-by-step. After each tool result, decide whether another tool is needed.
3. Never invent file contents or command outputs.
4. For destructive actions the runtime may ask for confirmation – you do not need to ask again.
5. Keep paths relative to the workspace root.
6. When the task is finished, give a clear, concise final answer in the same language the user used.
7. If a tool fails, analyse the error and try a safe alternative or report it.
8. Do not attempt to leave the workspace or escalate privileges.
9. run_command takes ONE simple allowlisted command. Pipes, &&, ;, redirects and
   $(...) are not supported. Use git_status / git_diff / git_log to inspect git state.
10. After you create or modify code, call run_tests (if the project has tests) and
    git_diff to verify your work. If tests fail, read the failures, fix the cause and
    run run_tests again before giving the final answer. If there are no tests, say so.
    Never claim success for something you did not verify.

Current workspace: {WORKSPACE}
""".strip()


def ask_grok(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Send conversation to Grok; return raw chat.completions-style JSON."""
    if not XAI_API_KEY:
        return {
            "error": {
                "message": "XAI_API_KEY is not set. Add it to .env (https://console.x.ai)"
            }
        }

    full = messages
    if not messages or messages[0].get("role") != "system":
        full = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + messages

    payload = {
        "model": GROK_MODEL,
        "messages": full,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.2,
    }

    try:
        resp = requests.post(
            GROK_CHAT_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {XAI_API_KEY}",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        return {"error": {"message": f"Network error talking to xAI: {e}"}}

    if resp.status_code != 200:
        try:
            err = resp.json()
        except Exception:
            err = {"message": resp.text[:500]}
        return {"error": err, "status_code": resp.status_code}

    return resp.json()


def extract_message(response: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return response["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw = message.get("tool_calls") or []
    result = []
    for tc in raw:
        fn = tc.get("function") or {}
        args_str = fn.get("arguments", "{}")
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else (args_str or {})
        except json.JSONDecodeError:
            args = {}
        result.append({
            "id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "arguments": args,
        })
    return result


def extract_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return "\n".join(t for t in texts if t).strip()
    return str(content).strip()
