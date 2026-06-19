# copilot_obs — local GitHub Copilot session observability

Discover and parse the artifacts GitHub Copilot writes on disk, and report
per-session usage: **session label, model, time of query, time taken, and
tokens consumed** — with no Copilot API or running editor required.

```bash
python -m copilot_obs list                     # all sessions, newest first
python -m copilot_obs list --workspace miraee   # filter by workspace
python -m copilot_obs list --model opus --json  # machine-readable
python -m copilot_obs show <sessionId|prefix>   # per-query breakdown
python -m copilot_obs export --out sessions.json
```

Example `show` output (real session):

```
Title     : Connecting Application to ADK/Livekit for AI Agent
Totals    : 56 queries · 4,142,357 tokens (exact) · 14226s
  #  WHEN              MODEL             PROMPT_TOK  COMPL_TOK   TIME   PROMPT
  0  2026-02-08 21:16  claude-opus-4.6     111,913        514   365s   Now we need to connect...
```

## Where Copilot stores sessions

The "Copilot sessions window" in VS Code is the chat history list. Each entry
is one **session** (with a label); each session contains multiple **queries**;
agent-mode edits spawn child editing-sessions. On disk:

| Artifact | macOS | Windows |
|---|---|---|
| Chat sessions (the list) | `~/Library/Application Support/<Editor>/User/workspaceStorage/<hash>/chatSessions/<id>.{json,jsonl}` | `%APPDATA%\<Editor>\User\workspaceStorage\<hash>\chatSessions\<id>.{json,jsonl}` |
| Edit sub-sessions | `…/workspaceStorage/<hash>/chatEditingSessions/<uuid>/` | same |
| Hash → real folder | `…/workspaceStorage/<hash>/workspace.json` | same |
| Copilot CLI sessions | `~/.copilot/session-state/<id>/events.jsonl` + `~/.copilot/session-store.db` | `%USERPROFILE%\.copilot\…` |
| Diagnostic log | `…/<Editor>/logs/<ts>/window<N>/exthost/GitHub.copilot-chat/GitHub Copilot Chat.log` | `%APPDATA%\<Editor>\logs\…` |

`<Editor>` ∈ `Code`, `Code - Insiders`, `VSCodium`, `Cursor`, `Windsurf` (Linux:
`~/.config/<Editor>/…`). See [platforms.py](copilot_obs/platforms.py).

## Two session formats (both handled)

* **`.json`** — a plain JSON session object (older).
* **`.jsonl`** — an **event-sourced log** (newer). Line 0 is the snapshot
  (`{"kind":"0","v":{…}}`); each later line mutates it (`kind:"1"` sets a value
  at JSON path `k`; `kind:"2"` appends to the array at `k`). We **replay** the
  log to rebuild the session — `json.load` on the whole file does not work.
  See [`_replay_jsonl`](copilot_obs/vscode.py).

Per query we read `modelId`, `timestamp` (time of query), `result.timings`
(`totalElapsed`/`firstProgress` = latency / time-to-first-token), and
`result.usage` (`promptTokens`/`completionTokens`, with a `promptTokenDetails`
category breakdown). `customTitle` is the session label (we fall back to the
first user message when it is null).

## The token caveat (important)

Exact token counts are **only present in newer `.jsonl` sessions** (the Copilot
Chat version that added `result.usage`). On a real machine this covered **~51%
of queries / 99 of 193 non-empty sessions (≈69M tokens)**. Older `.json`
sessions and pre-`usage` turns have no token field — the CLI marks those `-`
(not recorded). The `tokensExact` flag in `--json` distinguishes exact from
absent. (Optional future work: estimate the missing ones by tokenizing prompt +
response, or enable the opt-in OpenTelemetry file exporter — see below.)

## `.copilotmd` is not a file

There are no `*.copilotmd` files on disk. The string only appears as
`ccreq:<8hex>.copilotmd` request-log **identifiers** inside
`GitHub Copilot Chat.log`
(`ccreq:<id>.copilotmd | <status> | <model> | <ms>ms | [copilotLanguageModelWrapper]`).
The real per-session artifact is the `chatSessions` files above. The repo's
original `find_copilotmd_files.py` was based on this misunderstanding and is
superseded by this package.

## Pitfalls handled / known

* **Huge files** — sessions can reach multiple GB when responses embed large
  content. We stream line-by-line and skip giant content lines before
  `json.loads`, but always parse lines carrying `promptTokens`/`totalElapsed`,
  so token/latency fidelity is 100% while a full scan stays ~14s.
* **Format drift** — the session schema is internal/undocumented and changes
  between Copilot releases. Field access is defensive; event replay tolerates
  unknown paths. Re-verify against new versions.
* **Workspace hash orphaning** — renaming a folder or using dev-containers
  orphans history under the old hash; we still list it (workspace may be `-`).

## Extending to other surfaces

The model ([models.py](copilot_obs/models.py)) is surface-agnostic; add a parser
that yields `Session`/`Turn` and wire it into `cli.collect()`:

* **Copilot CLI** — `~/.copilot/session-store.db` (SQLite: `sessions`, `turns`,
  `session_files`, `checkpoints`) + `session-state/<id>/events.jsonl`. Note: the
  DB is absent until a CLI session runs, and reportedly not created on Windows
  WSL2 — fall back to `events.jsonl`.
* **OpenTelemetry (exact tokens + latency, all surfaces)** — set
  `github.copilot.chat.otel.exporterType: "file"` and
  `COPILOT_OTEL_FILE_EXPORTER_PATH` to write JSON-lines with
  `gen_ai.usage.input_tokens` / `output_tokens` and duration histograms. Opt-in,
  off by default.
* **JetBrains** (`idea.log`) / **Xcode** (`~/Library/Logs/GitHubCopilot/`) —
  general logs; little structured per-request usage.
