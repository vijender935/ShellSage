"""Local multi-step agent loop (Grok + tools) with SQLite-backed history."""
from __future__ import annotations
import json,sys,time,uuid
from typing import Any
from config.settings import MAX_STEPS,REQUIRE_CONFIRMATION,WORKSPACE
from core.safety import is_risky_command
from core.tools import execute_tool
from security.audit import log_tool_call
from security.confirmation import ask_confirmation
from agent.verify import VerifyTracker
from agent.providers.grok import ask_grok,extract_message,extract_text,extract_tool_calls
from storage.runtime import db

def _print_banner():
    print("="*50);print("       Grok Local Agent");print("="*50);print(f"Workspace : {WORKSPACE}");print("Type your request in natural language.");print("Commands  : exit | quit | clear");print()
def _pretty_result(result):
    if "summary" in result and "counts" in result:
        print(f"      {'✅' if result.get('success') else '❌'} tests: {result['summary']}")
        for failed in result.get("failed_tests",[])[:10]:print(f"         - {failed}")
        return
    if result.get("success"):
        if "items" in result:
            print(f"      📁 {result.get('path','.')} ({result.get('count',0)} items)")
            for item in result["items"][:40]:print(f"         - {item}")
        elif "content" in result:
            content=result["content"];print(f"      📄 Content:\n{content if len(content)<600 else content[:600]+'\n… (truncated)'}")
        elif "stdout" in result or "stderr" in result:
            if result.get("stdout"):print(f"      stdout:\n{result['stdout']}")
            if result.get("stderr"):print(f"      stderr:\n{result['stderr']}")
            print(f"      returncode: {result.get('returncode')}")
        else:print(f"      ✅ {result.get('message',result)}")
    else:print(f"      ❌ {result.get('error',result)}")

def _save(session_id,message):db.save_message(session_id,message)

def run_agent():
    _print_banner()
    session_id="local-default"
    db.create_session(session_id,"Local ShellSage")
    history=db.load_history(session_id)
    verify=VerifyTracker.from_env()
    while True:
        try:user_input=input("You: ").strip()
        except (KeyboardInterrupt,EOFError):print("\nAgent stopped.");break
        if not user_input:continue
        lower=user_input.lower()
        if lower in ("exit","quit","q"):print("Goodbye.");break
        if lower=="clear":
            history=[];db._conn().execute("DELETE FROM messages WHERE session_id=?",(session_id,));print("Conversation history cleared.\n");continue
        user_message={"role":"user","content":user_input};history.append(user_message);_save(session_id,user_message);verify.new_turn()
        task_id=uuid.uuid4().hex
        db.create_task(task_id,session_id,user_input)
        task_status="completed"
        for step in range(1,MAX_STEPS+1):
            response=ask_grok(history)
            if "error" in response:
                print("\n❌ Grok API error:");print(json.dumps(response["error"],indent=2,ensure_ascii=False));print();task_status="failed";break
            message=extract_message(response)
            if not message:
                print("\n⚠️ Empty response from model.");task_status="failed";break
            history.append(message);_save(session_id,message)
            tool_calls=extract_tool_calls(message)
            if not tool_calls:
                nudge=verify.pending_message()
                if nudge:
                    n={"role":"user","content":nudge};history.append(n);_save(session_id,n);continue
                text=extract_text(message)
                if text:print(f"\nAgent: {text}\n")
                break
            for tc in tool_calls:
                name,args,call_id=tc["name"],tc["arguments"],tc["id"]
                print(f"\n[{step}] Tool → {name}\n      Args → {args}")
                risky=(name=="delete_path") or (name=="run_command" and is_risky_command(str(args.get("command",""))))
                if risky and REQUIRE_CONFIRMATION and not ask_confirmation(f"{'delete' if name=='delete_path' else 'run command'}: {args}"):
                    result={"success":False,"error":"User cancelled the action."}
                else:
                    t0=time.perf_counter();result=execute_tool(name,args);log_tool_call(name,args,result,source="local_agent",duration_ms=round((time.perf_counter()-t0)*1000,1),session_id=session_id,task_id=task_id)
                verify.observe(name,result);_pretty_result(result)
                tool_message={"role":"tool","tool_call_id":call_id,"content":json.dumps(result,ensure_ascii=False)}
                history.append(tool_message);_save(session_id,tool_message)
        else:print(f"\n⚠️ Stopped after {MAX_STEPS} steps to prevent infinite loops.\n");task_status="max_steps"
        db.finish_task(task_id,task_status)
if __name__=="__main__":
    try:run_agent()
    except Exception as exc:print(f"\nFatal error: {exc}",file=sys.stderr);sys.exit(1)
