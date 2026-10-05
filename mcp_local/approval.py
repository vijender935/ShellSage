"""Remote approval policy for single-user destructive operations."""
from __future__ import annotations
import uuid
from core.safety import is_risky_command
from storage.runtime import db
def approval_required(tool:str,args:dict)->bool:
    return tool=="delete_path" or (tool=="run_command" and is_risky_command(str(args.get("command",""))))
def create_approval(task_id,tool,args):
    approval_id=uuid.uuid4().hex
    db.create_approval(approval_id,task_id,tool,args)
    return approval_id
