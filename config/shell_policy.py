"""Allowlist-only shell policy configuration."""
from __future__ import annotations
import os

def _env_list(key: str, default: str) -> frozenset[str]:
    raw = os.getenv(key, "").strip() or default
    return frozenset(p.strip() for p in raw.split(",") if p.strip())

SHELL_ALLOWLIST = _env_list("SHELL_ALLOWLIST", "ls,cat,head,tail,wc,grep,find,pwd,echo,diff,git,pytest,python,python3")
GIT_ALLOWED_SUBCOMMANDS = _env_list("GIT_ALLOWED_SUBCOMMANDS", "status,diff,log,show,branch,rev-parse,add,commit,restore,checkout,stash")
