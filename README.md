# Agent — Cloud MCP Agent for Grok

Cloud-hosted **file + shell agent** exposed through a Streamable HTTP MCP endpoint. It is designed to run directly on Render, so it does not require Termux, Ubuntu/proot, ngrok, or Cloudflare Tunnel.

```
Grok → Render → MCP server → sandboxed workspace / shell
```

## Architecture

```
Agent/
├── core/
│   ├── workspace.py      # Path sandbox
│   ├── safety.py         # Risky command detection
│   └── tools/
│       ├── filesystem.py
│       ├── shell.py
│       └── __init__.py   # Tool registry
├── mcp_local/
│   ├── server.py         # Streamable HTTP MCP server
│   └── auth.py           # Bearer-token middleware
├── security/
│   ├── confirmation.py   # Local-agent confirmation
│   └── audit.py          # JSONL audit logging
├── agent/                # Optional local Grok agent
├── config/settings.py
├── tests/                # pytest suite (workspace sandbox + auth)
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
| `delete_path` | Delete a file/folder recursively | **off** — set `ENABLE_DELETE=1` |
| `run_command` | Run a shell command in the workspace | **off** — set `ENABLE_SHELL=1` |
| `agent_status` | Return service status | on |

Clipboard/Android/Termux integrations have been removed from the cloud version.

## Security model

- **Authentication:** Bearer token required in HTTP mode (see above).
- **Least privilege:** shell and delete tools are not exposed unless explicitly enabled.
- **Path sandbox:** every file operation goes through `safe_path()`, which resolves symlinks and blocks `..` / absolute-path escapes (covered by tests).
- **Audit log:** JSONL audit logging remains enabled by default.

**Note:** the risky-command detector in `core/safety.py` is a heuristic, not a security boundary. If you enable `ENABLE_SHELL=1`, treat anyone holding the token as having shell access to the container, and keep the workspace free of secrets.

## Workspace

By default the cloud service uses:

`/app/workspace`

You can override it with:

`AGENT_WORKSPACE=/some/path`

Additional allowed roots can be supplied through `AGENT_EXTRA_ROOTS` using the platform path separator.

## Optional local Grok agent

The `agent/` package remains available for running the xAI/Grok multi-step loop separately. The Render MCP service itself does not require an xAI API key.

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
