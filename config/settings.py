"""Environment-driven settings for the cloud Agent."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
def _env(key:str,default:str="")->str:return os.getenv(key,default).strip()
def _env_int(key:str,default:int)->int:
    try:return int(os.getenv(key,str(default)))
    except (TypeError,ValueError):return default
_raw_ws=_env("AGENT_WORKSPACE","/app/workspace")
WORKSPACE=Path(_raw_ws).expanduser().resolve() if _raw_ws else (Path.cwd()/ "workspace").resolve()
WORKSPACE.mkdir(parents=True,exist_ok=True)
_extra_raw=_env("AGENT_EXTRA_ROOTS")
ALLOWED_ROOTS=[WORKSPACE]
if _extra_raw:
    for part in _extra_raw.split(os.pathsep):
        if part.strip():
            try:
                p=Path(part.strip()).expanduser().resolve()
                if p not in ALLOWED_ROOTS:ALLOWED_ROOTS.append(p)
            except Exception:pass
XAI_API_KEY=_env("XAI_API_KEY")
GROK_MODEL=_env("GROK_MODEL","grok-4.5")
GROK_BASE_URL=_env("GROK_BASE_URL","https://api.x.ai/v1").rstrip("/")
GROK_CHAT_URL=f"{GROK_BASE_URL}/chat/completions"
MAX_STEPS=_env_int("MAX_STEPS",12)
MAX_FILE_SIZE_BYTES=_env_int("MAX_FILE_SIZE_BYTES",2*1024*1024)
MAX_COMMAND_OUTPUT=_env_int("MAX_COMMAND_OUTPUT",12_000)
COMMAND_TIMEOUT_DEFAULT=_env_int("COMMAND_TIMEOUT_DEFAULT",30)
COMMAND_TIMEOUT_MAX=_env_int("COMMAND_TIMEOUT_MAX",90)
AUDIT_LOG_PATH=_env("AUDIT_LOG_PATH","")
DB_PATH=Path(_env("AGENT_DB_PATH",str(WORKSPACE/".shellsage.sqlite3"))).expanduser().resolve()
RISKY_COMMAND_PATTERNS=("rm ","rm -","rmdir","unlink","dd ","mkfs","apt ","apt-get ","aptitude ","yum ","dnf ","pacman ","pip install","pip3 install","pip uninstall","npm install","npm uninstall","npx ","git push","git reset","git clean","chmod ","chown ","chgrp ","sudo ","su ","curl ","wget ","python -c","python3 -c","bash -c","sh -c","eval ","source ")
