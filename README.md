# Copilot Observability Agent

Python-only collector for GitHub Copilot observability records.

The goal is intentionally narrow: provide one Copilot custom agent plus small
Python tools that collect records from known Copilot surfaces, normalize them
into one schema, and write JSONL or CSV.

## Layout

```text
agents/
  observability-agent.agent.md
agent_tools/
  cli/
    collect_sessions.py
    inspect_store.py
  discovery/
    discover_sources.py
  sdk/
    collect_jsonl.py
  vscode/
    collect_chat_sessions.py
    collect_logs.py
  json_helpers.py
  platform_paths.py
  schema.py
  write_output.py
copilot_observability.py
load_agent.py
```

`agents/observability-agent.agent.md` is the actual Copilot agent profile. The
files under `agent_tools/` are the tools the agent can run with the shell
execute tool. `copilot_observability.py` is only a thin wrapper for combined
collection.

`load_agent.py` copies agent files from `agents/` into `~/.copilot/agents` so
Copilot can discover them locally.

## Current Scope

Implemented now:

- Discover local/configured Copilot sources.
- Collect Copilot SDK event JSONL with `assistant.usage`, tool, subagent, and error events.
- Collect simple Copilot CLI session JSON/JSONL files from a session-state directory.
- Collect VS Code Copilot diagnostic log events from Copilot-related log files.
- Collect VS Code Copilot Chat debug sessions from workspace storage.
- Normalize records into one common schema.
- Write JSONL or CSV.

Discovery-only for now:

- Copilot CLI SQLite session store.
- GitHub cloud agent API.
- Xcode logs.
- Enterprise audit logs.
- Copilot usage metrics reports.

Those sources need real samples or credentials before implementing parsers. The
collector leaves unsupported fields blank rather than guessing.

## Normalized Fields

Every output row uses these fields:

```text
source
run_id
session_id
session_label
timestamp
agent_name
parent_agent_name
model
input_tokens
output_tokens
total_tokens
cached_tokens
duration_ms
tool_calls
error_status
workspace
user
field_confidence
raw_source_ref
```

`field_confidence` is important because not all Copilot surfaces expose the
same data. SDK events can expose token and duration fields directly. IDE logs
often only expose troubleshooting details.

## Usage

Discover available sources:

```sh
python3 copilot_observability.py discover
```

Discovery uses platform-specific default paths. It checks VS Code-style data
under `~/Library/Application Support` on macOS, `%APPDATA%` on Windows, and
`$XDG_CONFIG_HOME` or `~/.config` on Linux. If discovery returns a path, pass
that path to the matching collector instead of hardcoding an OS-specific value.

Load local agents into Copilot:

```sh
python3 load_agent.py
```

Preview without writing:

```sh
python3 load_agent.py --dry-run
```

Preview cleanup of generated run files:

```sh
python3 clean_run_data.py
```

Delete generated run files and Python cache directories:

```sh
python3 clean_run_data.py --apply
```

Preview cleanup of raw local Copilot logs and debug/session data:

```sh
python3 clean_copilot_surface_data.py
```

Delete raw local Copilot logs and debug/session data:

```sh
python3 clean_copilot_surface_data.py --apply
```

Close VS Code, Copilot CLI, and other Copilot surfaces before running the raw
surface cleanup with `--apply`; active tools may recreate files immediately.

Collect SDK telemetry JSONL:

```sh
python3 copilot_observability.py collect \
  --sdk-jsonl path/to/sdk-events.jsonl \
  --output observations.jsonl
```

Collect Copilot CLI session files:

```sh
python3 copilot_observability.py collect \
  --cli-state-dir ~/.copilot/session-state \
  --output observations.jsonl
```

Collect VS Code Copilot diagnostic logs:

```sh
python3 copilot_observability.py collect \
  --vscode-logs-dir "$HOME/Library/Application Support/Code/logs" \
  --output vscode-observations.jsonl
```

Windows PowerShell:

```powershell
python copilot_observability.py collect `
  --vscode-logs-dir "$env:APPDATA\Code\logs" `
  --output vscode-observations.jsonl
```

Collect VS Code Copilot Chat debug sessions:

```sh
python3 copilot_observability.py collect \
  --vscode-workspace-storage-dir "$HOME/Library/Application Support/Code/User/workspaceStorage" \
  --output vscode-chat-observations.jsonl
```

Windows PowerShell:

```powershell
python copilot_observability.py collect `
  --vscode-workspace-storage-dir "$env:APPDATA\Code\User\workspaceStorage" `
  --output vscode-chat-observations.jsonl
```

Combine implemented local sources:

```sh
python3 copilot_observability.py collect \
  --cli-state-dir ~/.copilot/session-state \
  --vscode-logs-dir "$HOME/Library/Application Support/Code/logs" \
  --vscode-workspace-storage-dir "$HOME/Library/Application Support/Code/User/workspaceStorage" \
  --output observations.jsonl
```

Windows PowerShell:

```powershell
python copilot_observability.py collect `
  --cli-state-dir "$HOME\.copilot\session-state" `
  --vscode-logs-dir "$env:APPDATA\Code\logs" `
  --vscode-workspace-storage-dir "$env:APPDATA\Code\User\workspaceStorage" `
  --output observations.jsonl
```

Write CSV instead of JSONL:

```sh
python3 copilot_observability.py collect \
  --sdk-jsonl path/to/sdk-events.jsonl \
  --output observations.csv \
  --format csv
```

Inspect the Copilot CLI SQLite store tables:

```sh
python3 copilot_observability.py inspect-store ~/.copilot/session-store.db
```

The tools can also be run directly:

```sh
python3 -m agent_tools.discovery.discover_sources
python3 -m agent_tools.sdk.collect_jsonl path/to/sdk-events.jsonl
python3 -m agent_tools.cli.collect_sessions ~/.copilot/session-state
python3 -m agent_tools.vscode.collect_logs PATH_FROM_DISCOVERY
python3 -m agent_tools.vscode.collect_chat_sessions PATH_FROM_DISCOVERY
python3 -m agent_tools.cli.inspect_store ~/.copilot/session-store.db
```

VS Code log rows are diagnostic. They can usually provide timestamp, severity,
request ID, user, and error/warning text when present. They should not be
treated as a reliable source for input tokens, output tokens, cached tokens,
model duration, or tool calls.

CLI session-state rows use Copilot's saved title metadata when present. If a
session title is not available, the collector falls back to the workspace
summary or the first user message so the session can still be identified.

VS Code chat-debug rows are structured session telemetry. They can provide
session id, session label, response id, model, token counts, duration,
workspace, and tool-call summaries when those fields are present in the debug
JSONL. The collector does not store prompt or response text in normalized
output.

## Validation

Run:

```sh
python3 -m unittest discover -s tests
```

The tests enforce that Python code files stay at or below 350 lines.

## Design Notes

This project intentionally avoids:

- background services
- plugin systems
- factories/interfaces
- external dependencies
- speculative source adapters
- undocumented API scraping

The implementation should stay boring and local until real source samples prove
that more structure is necessary.

## Official Documentation Used

- Copilot SDK streaming events: https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/streaming-events
- Copilot SDK OpenTelemetry: https://docs.github.com/en/copilot/how-tos/copilot-sdk/observability/opentelemetry
- Copilot CLI session data: https://docs.github.com/en/copilot/concepts/agents/copilot-cli/chronicle
- Cloud agent task API: https://docs.github.com/en/rest/agent-tasks/agent-tasks
- IDE logs: https://docs.github.com/en/copilot/how-tos/troubleshoot-copilot/view-logs
- Agentic audit logs: https://docs.github.com/en/copilot/reference/agentic-audit-log-events
- Copilot usage metrics API: https://docs.github.com/en/rest/copilot/copilot-usage-metrics
