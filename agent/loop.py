"""
Local multi-step agent loop (Grok + tools).
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from config.settings import MAX_STEPS, REQUIRE_CONFIRMATION, WORKSPACE
from core.safety import is_risky_command
from core.tools import execute_tool
from security.audit import log_tool_call
from security.confirmation import ask_confirmation
from agent.verify import VerifyTracker
from agent.providers.grok import (
    ask_grok,
    extract_message,
    extract_text,
    extract_tool_calls,
)


def _print_banner() -> None:
    print("=" * 50)
    print("       Grok Local Agent")
    print("=" * 50)
    print(f"Workspace : {WORKSPACE}")
    print("Type your request in natural language.")
    print("Commands  : exit | quit | clear")
    print()


def _pretty_result(result: dict[str, Any]) -> None:
    if "summary" in result and "counts" in result:  # run_tests
        icon = "✅" if result.get("success") else "❌"
        print(f"      {icon} tests: {result['summary']}")
        for failed in result.get("failed_tests", [])[:10]:
            print(f"         - {failed}")
        return

    if result.get("success"):
        if "items" in result:
            print(f"      📁 {result.get('path', '.')} ({result.get('count', 0)} items)")
            for item in result["items"][:40]:
                print(f"         - {item}")
            if len(result["items"]) > 40:
                print(f"         … and {len(result['items']) - 40} more")
        elif "content" in result:
            content = result["content"]
            preview = content if len(content) < 600 else content[:600] + "\n… (truncated)"
            print(f"      📄 Content:\n{preview}")
        elif "stdout" in result or "stderr" in result:
            if result.get("stdout"):
                print(f"      stdout:\n{result['stdout']}")
            if result.get("stderr"):
                print(f"      stderr:\n{result['stderr']}")
            print(f"      returncode: {result.get('returncode')}")
        else:
            print(f"      ✅ {result.get('message', result)}")
    else:
        print(f"      ❌ {result.get('error', result)}")


def run_agent() -> None:
    _print_banner()
    history: list[dict[str, Any]] = []
    verify = VerifyTracker.from_env()

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAgent stopped.")
            break

        if not user_input:
            continue

        lower = user_input.lower()
        if lower in ("exit", "quit", "q"):
            print("Goodbye.")
            break
        if lower == "clear":
            history.clear()
            print("Conversation history cleared.\n")
            continue

        history.append({"role": "user", "content": user_input})
        verify.new_turn()

        for step in range(1, MAX_STEPS + 1):
            response = ask_grok(history)

            if "error" in response:
                print("\n❌ Grok API error:")
                print(json.dumps(response["error"], indent=2, ensure_ascii=False))
                print()
                history.pop()
                break

            message = extract_message(response)
            if not message:
                print("\n⚠️  Empty response from model.")
                print(json.dumps(response, indent=2)[:800])
                history.pop()
                break

            history.append(message)
            tool_calls = extract_tool_calls(message)

            if not tool_calls:
                # Edit -> test -> fix: do not accept "done" while changes are unverified.
                nudge = verify.pending_message()
                if nudge:
                    print("\n🔎 Verifying before finishing…")
                    history.append({"role": "user", "content": nudge})
                    continue

                text = extract_text(message)
                if text:
                    print(f"\nAgent: {text}\n")
                else:
                    print("\n(Agent finished without text.)\n")
                break

            for tc in tool_calls:
                name = tc["name"]
                args = tc["arguments"]
                call_id = tc["id"]

                print(f"\n[{step}] Tool → {name}")
                print(f"      Args → {args}")

                risky = False
                reason = ""
                if name == "delete_path":
                    risky = True
                    reason = f"delete '{args.get('path')}'"
                elif name == "run_command":
                    cmd = str(args.get("command", ""))
                    if is_risky_command(cmd):
                        risky = True
                        reason = f"run command: {cmd}"

                if risky and REQUIRE_CONFIRMATION:
                    if not ask_confirmation(reason):
                        result = {"success": False, "error": "User cancelled the action."}
                    else:
                        t0 = time.perf_counter()
                        result = execute_tool(name, args)
                        log_tool_call(
                            name, args, result,
                            source="local_agent",
                            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        )
                else:
                    t0 = time.perf_counter()
                    result = execute_tool(name, args)
                    log_tool_call(
                        name, args, result,
                        source="local_agent",
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                    )

                verify.observe(name, result)
                _pretty_result(result)

                history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            print(f"\n⚠️  Stopped after {MAX_STEPS} steps to prevent infinite loops.\n")


if __name__ == "__main__":
    try:
        run_agent()
    except Exception as exc:
        print(f"\nFatal error: {exc}", file=sys.stderr)
        sys.exit(1)
