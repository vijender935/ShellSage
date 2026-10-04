'''Shell policy settings (kept separate from config/settings.py).

SHELL_ALLOWLIST        comma-separated command names the agent may run
GIT_ALLOWED_SUBCOMMANDS comma-separated git subcommands the agent may run
SHELL_UNRESTRICTED=1   old behaviour: shell=True, any command (NOT recommended)
'''
from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def _env_list(key: str, default: str) -> frozenset[str]:
    raw = os.getenv(key, "").strip() or default
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


SHELL_ALLOWLIST = _env_list(
    "SHELL_ALLOWLIST",
    "ls,cat,head,tail,wc,grep,find,pwd,echo,diff,git,pytest,python,python3",
)

GIT_ALLOWED_SUBCOMMANDS = _env_list(
    "GIT_ALLOWED_SUBCOMMANDS",
    "status,diff,log,show,branch,rev-parse,add,commit,restore,checkout,stash",
)

SHELL_UNRESTRICTED = os.getenv("SHELL_UNRESTRICTED", "").strip().lower() in _TRUE
