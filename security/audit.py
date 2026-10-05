"""SQLite-backed audit logging with secret-safe redaction."""
from __future__ import annotations
from typing import Any
from storage.runtime import db
_SECRET_NAMES=("TOKEN","SECRET","API_KEY","APIKEY","PASSWORD","PASSWD","CREDENTIAL","AUTHORIZATION")
def _redact(value:Any)->Any:
    if isinstance(value,dict):
        return {k:("[REDACTED]" if any(m in str(k).upper() for m in _SECRET_NAMES) else _redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [_redact(v) for v in value]
    if isinstance(value,str):
        s=value.lower()
        if any(m in s for m in ("authorization:","bearer ","xai_api_key=","token=")):return "[REDACTED]"
        return value if len(value)<=1000 else value[:1000]+"…"
    return value
def log_tool_call(tool:str,args:dict[str,Any],result:dict[str,Any],*,source:str="unknown",duration_ms:float|None=None,session_id:str|None=None,task_id:str|None=None)->None:
    safe_args=_redact(args); safe_result=_redact(result)
    db.record_audit(source,tool,safe_args,safe_result,duration_ms,session_id=session_id,task_id=task_id)
    if task_id or session_id:db.record_tool_call(task_id,session_id,tool,safe_args,safe_result,duration_ms)
