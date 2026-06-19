# POC - Copilot Observability Agent

## Overview

This POC evaluated whether GitHub Copilot usage can be observed locally by reading the artifacts Copilot already writes on disk, without depending on a Copilot API, a running editor, or manual session review. The outcome was positive: the project can discover local Copilot chat sessions, parse session history, identify the model used, show per-query timestamps and latency, and report exact token usage where Copilot records it.

## Background & Problem Statement

The work was initiated because Copilot usage is difficult to inspect after the fact. The visible VS Code session list does not provide a clean usage report across sessions, models, prompts, timings, and token consumption. The early assumption that `.copilotmd` files were the main artifact was incorrect; those are only request-log identifiers. The real data lives in VS Code-family `workspaceStorage` session files and related logs.

## Objectives & Scope

- Prove that local Copilot artifacts can be used for session observability.
- Discover Copilot Chat sessions across VS Code-family editors.
- Parse both older `.json` session files and newer `.jsonl` event-sourced session logs.
- Extract session title, workspace, model, query time, latency, prompt tokens, completion tokens, and total tokens.
- Keep the implementation local-first and API-free.
- Stay explicit about missing or unavailable token data instead of guessing.

Out of scope:

- Full cloud-side Copilot billing reconciliation.
- Guaranteed support for every editor, fork, or install mode.
- Exact token recovery for old sessions that never stored token fields.
- Deep JetBrains/Xcode usage extraction, because their logs appear less structured for per-request accounting.

## Tools/Technologies Evaluated

| Tool / Technology | Purpose | Why It Was Considered | Learning |
|---|---|---|---|
| VS Code `workspaceStorage` | Main source for Copilot Chat sessions | Stores the actual session list and per-session files | This is the primary source of truth for Copilot Chat observability. |
| `chatSessions/*.json` | Older Copilot session format | Some machines still contain historical sessions in this format | Useful for history, but often lacks exact token usage. |
| `chatSessions/*.jsonl` | Newer event-sourced Copilot session format | Contains richer per-turn metadata including usage and timings | Must be replayed event-by-event; cannot be parsed as one JSON document. |
| `result.usage` fields | Token accounting | Needed to report prompt and completion token usage | Exact tokens are available only when Copilot recorded these fields. |
| `result.timings` fields | Latency accounting | Needed to show total elapsed time and time-to-first-progress | Gives useful per-query performance visibility. |
| VS Code-family editor roots | Cross-editor discovery | Code, Insiders, VSCodium, Cursor, and Windsurf reuse similar storage layouts | Default roots can be scanned, but custom/portable installs remain a gap. |
| `workspace.json` | Hash-to-workspace mapping | Workspace folders are stored under hashed directories | Required to map a session back to a human-readable project folder. |
| Copilot diagnostic logs | Request-level troubleshooting | Helped clarify `.copilotmd` identifiers and log locations | Useful for diagnostics, but not the main structured session source. |
| OpenTelemetry file exporter | Future exact usage source | Could provide exact tokens and latency across more surfaces | Best future path for broader, reliable observability. |
| Copilot CLI session store | Future non-editor surface | Copilot CLI has its own local state and possible SQLite/events files | Worth adding later, but separate from the VS Code parser. |

## Findings and Recommendations

| Area | Finding | Tradeoff / Risk | Recommendation |
|---|---|---|---|
| Source of truth | `chatSessions` files are the real Copilot Chat session artifacts. | Diagnostic logs alone are incomplete for structured reporting. | Keep `chatSessions` as the primary ingestion source. |
| `.copilotmd` assumption | `.copilotmd` is not a real file artifact; it is a request identifier in logs. | Building around it leads to a dead-end collector. | Keep this clearly documented to avoid repeating the mistake. |
| Session format | Newer `.jsonl` sessions are event-sourced. | Simple JSON parsing fails or misses final state. | Continue replaying `kind:0`, `kind:1`, and `kind:2` events. |
| Token reporting | Exact tokens exist only in newer sessions with `result.usage`. | Older sessions cannot be truthfully counted without estimation. | Keep `tokensExact` and show missing values as not recorded. |
| Large files | Real Copilot sessions can become very large. | Naive parsing can be slow or memory-heavy. | Continue streaming line-by-line and skipping huge non-metric content lines. |
| Platform coverage | Default VS Code-family paths are discoverable across macOS, Windows, and Linux. | Portable installs, custom user-data dirs, and unsupported forks may be missed. | Describe support as default-root coverage, not exhaustive machine coverage. |
| Data model | A normalized `Session` / `Turn` model keeps the CLI surface-agnostic. | Each new Copilot surface still needs its own parser. | Keep parser-specific ingestion separate from reporting. |
| Future expansion | OpenTelemetry is the cleanest path for exact cross-surface usage. | It is opt-in and not enabled by default. | Prioritize OpenTelemetry support before weaker log-only integrations. |

Final recommendation: continue with this local-artifact approach for VS Code-family Copilot Chat observability. It is practical, low-friction, and already exposes the key metrics. The main product caveat is that token reporting must remain honest: exact when present, absent when not recorded, and estimated only if explicitly implemented later.

## Artifacts Produced

- `README.md` - project explanation, usage examples, storage locations, caveats, and extension plan.
- `copilot_obs/platforms.py` - cross-platform discovery of VS Code-family editor roots.
- `copilot_obs/vscode.py` - discovery and parsing of VS Code Copilot Chat session files.
- `copilot_obs/models.py` - normalized `Session` and `Turn` data model.
- `copilot_obs/cli.py` - CLI commands for listing, showing, filtering, and exporting sessions.
- `python -m copilot_obs list` - command to list all discovered sessions.
- `python -m copilot_obs show <sessionId|prefix>` - command to inspect per-query session details.
- `python -m copilot_obs export --out sessions.json` - command to export structured session data.

## References

- `README.md`
- `copilot_obs/platforms.py`
- `copilot_obs/vscode.py`
- `copilot_obs/models.py`
- `copilot_obs/cli.py`
- VS Code workspace storage layout: `<Editor>/User/workspaceStorage/<hash>/chatSessions/`
- Copilot diagnostic log pattern: `GitHub.copilot-chat/GitHub Copilot Chat.log`
- Future reference path: Copilot OpenTelemetry file exporter configuration.
