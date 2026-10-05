"""Cloud-hosted MCP server with authentication and approval-gated risky tools."""
from __future__ import annotations
import argparse, os, sys, time
from typing import Any, Callable
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:sys.path.insert(0,_ROOT)
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    from mcp.server import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
from config.settings import WORKSPACE
from core.tools import execute_tool,tool_names
from mcp_local.auth import BearerAuthMiddleware, current_identity
from mcp_local.approval import approval_required,create_approval
from security.audit import log_tool_call
from storage.runtime import db
_TRUE={"1","true","yes","on"}
def _flag(name):return os.getenv(name,"").strip().lower() in _TRUE
ENABLE_SHELL=_flag("ENABLE_SHELL");ENABLE_DELETE=_flag("ENABLE_DELETE");_AUTH_STATE="n/a (stdio)"
_SHELL_TOOLS=frozenset({"run_command","run_tests"})
mcp=FastMCP("Agent",instructions=f"You are connected to a single-user cloud agent. Workspace: {WORKSPACE}. Shell/delete are disabled unless explicitly enabled. Risky shell/delete actions require an approval round-trip. After code changes verify with run_tests and git_diff.",transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True))
def _tool_if(enabled:bool)->Callable:
    def decorator(fn):return mcp.tool()(fn) if enabled else fn
    return decorator
def _run(name:str,args:dict[str,Any],*,source="mcp",approved=False):
    if not approved and approval_required(name,args):
        approval_id=create_approval(None,name,args)
        return {"success":False,"status":"approval_required","approval_id":approval_id,"tool":name,"message":"Approval required. Call approve_action with this approval_id to execute exactly this request."}
    started=time.perf_counter();result=execute_tool(name,args);duration=(time.perf_counter()-started)*1000
    log_tool_call(name,args,result,source=source,duration_ms=round(duration,1))
    return result
@mcp.tool()
def list_files(path=".")->dict[str,Any]:return _run("list_files",{"path":path})
@mcp.tool()
def create_folder(name:str)->dict[str,Any]:return _run("create_folder",{"name":name})
@mcp.tool()
def create_file(path:str,content:str="")->dict[str,Any]:return _run("create_file",{"path":path,"content":content})
@mcp.tool()
def read_file(path:str)->dict[str,Any]:return _run("read_file",{"path":path})
@mcp.tool()
def write_file(path:str,content:str)->dict[str,Any]:return _run("write_file",{"path":path,"content":content})
@mcp.tool()
def copy_file(source:str,destination:str)->dict[str,Any]:return _run("copy_file",{"source":source,"destination":destination})
@mcp.tool()
def move_file(source:str,destination:str)->dict[str,Any]:return _run("move_file",{"source":source,"destination":destination})
@_tool_if(ENABLE_DELETE)
def delete_path(path:str)->dict[str,Any]:return _run("delete_path",{"path":path})
@_tool_if(ENABLE_SHELL)
def run_command(command:str,timeout:int=30)->dict[str,Any]:return _run("run_command",{"command":command,"timeout":timeout})
@_tool_if(ENABLE_SHELL)
def run_tests(path:str="",keyword:str="",fail_fast:bool=False)->dict[str,Any]:return _run("run_tests",{"path":path,"keyword":keyword,"fail_fast":fail_fast})
@mcp.tool()
def approve_action(approval_id:str)->dict[str,Any]:
    pending=db.consume_approval(approval_id)
    if not pending:return {"success":False,"error":"Approval not found, already resolved, or expired."}
    if pending.get("identity") != current_identity(): return {"success":False,"error":"Approval belongs to a different authenticated client."}
    started=time.perf_counter();result=execute_tool(pending["tool"],pending["arguments"]);duration=(time.perf_counter()-started)*1000
    log_tool_call(pending["tool"],pending["arguments"],result,source="mcp_approved",duration_ms=round(duration,1))
    return {"success":bool(result.get("success")),"approval_id":approval_id,"tool":pending["tool"],"result":result}
@mcp.tool()
def reject_action(approval_id:str)->dict[str,Any]:
    return {"success":db.reject_approval(approval_id),"approval_id":approval_id}
@mcp.tool()
def git_status()->dict[str,Any]:return _run("git_status",{})
@mcp.tool()
def git_diff(path="",staged=False)->dict[str,Any]:return _run("git_diff",{"path":path,"staged":staged})
@mcp.tool()
def git_log(count=10)->dict[str,Any]:return _run("git_log",{"count":count})
@mcp.tool()
def agent_status()->str:
    exposed=[n for n in tool_names() if not(n in _SHELL_TOOLS and not ENABLE_SHELL) and not(n=="delete_path" and not ENABLE_DELETE)]
    return f"Agent is online.\nWorkspace: {WORKSPACE}\nAuth: {_AUTH_STATE}\nShell: {'ENABLED' if ENABLE_SHELL else 'disabled'}\nDelete: {'ENABLED' if ENABLE_DELETE else 'disabled'}\nTools: {', '.join(exposed)}"
def main():
    global _AUTH_STATE
    parser=argparse.ArgumentParser();parser.add_argument("--http",action="store_true");parser.add_argument("--host",default=os.getenv("HOST","0.0.0.0"));parser.add_argument("--port",type=int,default=int(os.getenv("PORT","8000")));args=parser.parse_args()
    if not args.http:mcp.run(transport="stdio");return
    token=os.getenv("AGENT_API_TOKEN","").strip()
    if not token:sys.exit("Refusing to start: AGENT_API_TOKEN is not set.")
    max_body=int(os.getenv("MAX_HTTP_BODY_BYTES","1048576"))
    rpm=int(os.getenv("HTTP_REQUESTS_PER_MINUTE","60"))
    app=BearerAuthMiddleware(mcp.streamable_http_app(),token,max_body_bytes=max_body,requests_per_minute=rpm);_AUTH_STATE="ENABLED (Bearer header only; rate/body limits)"
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,access_log=False)
if __name__=="__main__":main()
