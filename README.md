# Agent — Cloud MCP Agent for Grok

Cloud-hosted **file + shell agent** exposed through a Streamable HTTP MCP endpoint. It is designed to run directly on Render, so it does not require Termux, Ubuntu/proot, ngrok, or Cloudflare Tunnel.

```
Grok → Render → MCP server → sandboxed workspace / shell
```

## Architecture

```
Agent/
├── core/
│   ├── workspace.py      # Path sandbox (+ .git protection)
│   ├── safety.py         # Shell command policy (allowlist)
│   └── tools/
│       ├── filesystem.py
│       ├── shell.py
│       ├── git.py        # Read-only git tools
│       ├── verify.py     # run_tests (structured pytest results)
│       └── __init__.py   # Tool registry
├── mcp_local/
│   ├── server.py         # Streamable HTTP MCP server
│   └── auth.py           # Bearer-token middleware
├── security/
│   ├── confirmation.py   # Local-agent confirmation
│   └── audit.py          # JSONL audit logging
├── agent/                # Optional local Grok agent
│   ├── loop.py
│   └── verify.py         # Edit -> test -> fix nudges
├── config/
│   ├── settings.py
│   └── shell_policy.py   # Allowlist settings
├── tests/                # pytest suite (sandbox, auth, shell policy, git, verify)
├── run_mcp_server.py
└── requirements.txt
```

## Render deployment

Use these Render settings:

- **Runtime:** Python
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `python run_mcp_server.py --http --host 0.0.0.0 --port $PORT`
- **Region:** Singapore
- **Plan:** Free (upgrade if you need persistent/high-throughput service)

Render supplies the `PORT` environment variable automatically.

**Required environment variable:** `AGENT_API_TOKEN` (the server refuses to start without it).

After deployment, the MCP endpoint is:

`https://YOUR-SERVICE.onrender.com/mcp`

## Authentication

Set `AGENT_API_TOKEN` to a long random secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Clients authenticate with either:

- Header: `Authorization: Bearer <token>`
- URL (for MCP clients that only accept a URL): `https://YOUR-SERVICE.onrender.com/mcp?token=<token>`

Requests without a valid token get `401`. Access logging is disabled so the `?token=` value is not written to logs.

## Available MCP tools

| Tool | Description | Default |
|---|---|---|
| `list_files` | List files/folders | on |
| `create_folder` | Create a folder | on |
| `create_file` | Create/replace a text file | on |
| `read_file` | Read a text file | on |
| `write_file` | Update a text file | on |
| `copy_file` | Copy a file | on |
| `move_file` | Move/rename a file or folder | on |
| `git_status` | Short git status | on |
| `git_diff` | Git diff (working tree / staged, optional path) | on |
| `git_log` | Recent commits | on |
| `delete_path` | Delete a file/folder recursively | **off** — set `ENABLE_DELETE=1` |
| `run_command` | Run ONE allowlisted command in the workspace | **off** — set `ENABLE_SHELL=1` |
| `run_tests` | Run pytest, return pass/fail + failing tests | **off** — set `ENABLE_SHELL=1` |
| `agent_status` | Return service status | on |

Clipboard/Android/Termux integrations have been removed from the cloud version.

## Shell policy

`run_command` does **not** use a shell. The command is split with `shlex` and run with `shell=False`, so `;`, `&&`, `||`, `|`, redirects, `$(...)` and backticks are rejected (and could never be interpreted anyway).

- Only commands in `SHELL_ALLOWLIST` run (default: `ls cat head tail wc grep find pwd echo diff git pytest python python3`). Absolute/relative paths to binaries (`/bin/rm`, `./x`) are rejected.
- Dangerous arguments are denied: `find -exec/-delete`, `python -c`, `git --hard/--force/-f/-D`, etc.
- `git` is limited to `GIT_ALLOWED_SUBCOMMANDS` (no `push`, `reset`, `clean`, `config`, `clone`, `remote`), global options are refused, and hooks/fsmonitor are disabled.
- Path-like arguments must stay inside the workspace (no `/etc/passwd`, `../x`, `~`, symlink escapes).
- Secrets (anything with `TOKEN`, `SECRET`, `API_KEY`, `PASSWORD`… in its name) are removed from the child process environment.

**Important:** `python` and `pytest` can execute arbitrary code. Remove them from `SHELL_ALLOWLIST` if you do not want that (`run_tests` then stops working). `SHELL_UNRESTRICTED=1` restores the old `shell=True` behaviour (not recommended).

## Verification loop (edit → test → fix)

- `run_tests` runs `pytest -q --tb=short` (override with `TEST_COMMAND`) through the same shell policy and returns a compact result: `success`, `summary`, `counts`, `failed_tests`, `output_tail`. Exit code 5 (no tests collected) is reported as `no_tests`.
- **MCP clients** (Claude, Grok, …) get the tools plus an instruction to verify with `run_tests` + `git_diff` before reporting success.
- **Local agent:** `agent/verify.py` tracks tool calls per user message. If the model tries to finish after changing files without running tests, or after a failing test run, the loop sends it a "verify first" message instead of accepting the answer. Capped by `VERIFY_MAX_NUDGES` (default 2); disable with `AUTO_VERIFY=0`. If the project has no tests or the runner is blocked, the agent is not nagged.

## Security model

- **Authentication:** Bearer token required in HTTP mode.
- **Least privilege:** shell, test-runner and delete tools are not exposed unless explicitly enabled.
- **Path sandbox:** every file operation goes through `safe_path()`, which resolves symlinks, blocks `..` / absolute-path escapes, and refuses anything inside `.git` (a writable `.git/config` or hooks dir would allow code execution through git).
- **Audit log:** JSONL audit logging remains enabled by default.

## Workspace

By default the cloud service uses:

`/app/workspace`

You can override it with:

`AGENT_WORKSPACE=/some/path`

Additional allowed roots can be supplied through `AGENT_EXTRA_ROOTS` using the platform path separator.

## Optional local Grok agent

The `agent/` package remains available for running the xAI/Grok multi-step loop separately. The Render MCP service itself does not require an xAI API key. Note: the local agent uses the same shell policy; set `SHELL_UNRESTRICTED=1` if you need pipes/redirects there.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export AGENT_API_TOKEN=dev-token
python run_mcp_server.py --http --host 0.0.0.0 --port 8000
```

Then connect an MCP client to `http://localhost:8000/mcp` (with `Authorization: Bearer dev-token`).

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
