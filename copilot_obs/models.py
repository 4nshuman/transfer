"""Normalized data model shared across all Copilot surfaces.

Every parser (VS Code, Copilot CLI, ...) maps its raw artifact onto these
dataclasses so the CLI and aggregations stay surface-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _dt(ms: int | None) -> datetime | None:
    if not ms:
        return None
    # Copilot stores epoch milliseconds; render in local time for the user.
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()


@dataclass
class Turn:
    """One user query + Copilot response within a session."""

    index: int
    request_id: str | None = None
    timestamp_ms: int | None = None
    model: str | None = None
    prompt: str = ""
    response_chars: int = 0
    # Token accounting. Present (exact) in newer VS Code .jsonl sessions via
    # result.usage; None when the artifact does not record it.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_estimated: bool = False
    # Latency. From result.timings in VS Code sessions.
    total_elapsed_ms: int | None = None
    ttft_ms: int | None = None
    tool_calls: int = 0

    @property
    def when(self) -> datetime | None:
        return _dt(self.timestamp_ms)

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


@dataclass
class Session:
    """A labeled Copilot conversation — one entry in the sessions window."""

    session_id: str
    source: str  # "vscode" | "copilot-cli" | ...
    path: str  # the artifact file on disk
    title: str | None = None
    editor: str | None = None  # "Code", "Code - Insiders", "Cursor", ...
    workspace: str | None = None  # resolved folder path, if known
    created_ms: int | None = None
    last_ms: int | None = None
    turns: list[Turn] = field(default_factory=list)
    fmt: str = ""  # "json" | "jsonl-events" | "sqlite" | ...

    # --- derived label ---------------------------------------------------
    @property
    def label(self) -> str:
        if self.title:
            return self.title
        # VS Code shows the first user message when there is no custom title.
        for t in self.turns:
            if t.prompt.strip():
                line = t.prompt.strip().splitlines()[0]
                return (line[:60] + "…") if len(line) > 60 else line
        return "(untitled)"

    # --- timestamps ------------------------------------------------------
    @property
    def created(self) -> datetime | None:
        return _dt(self.created_ms)

    @property
    def last_activity(self) -> datetime | None:
        ts = [t.timestamp_ms for t in self.turns if t.timestamp_ms]
        return _dt(max(ts)) if ts else _dt(self.last_ms or self.created_ms)

    # --- aggregates ------------------------------------------------------
    @property
    def num_turns(self) -> int:
        return len(self.turns)

    @property
    def models(self) -> list[str]:
        seen: dict[str, None] = {}
        for t in self.turns:
            if t.model:
                seen.setdefault(t.model, None)
        return list(seen)

    @property
    def prompt_tokens(self) -> int:
        return sum(t.prompt_tokens or 0 for t in self.turns)

    @property
    def completion_tokens(self) -> int:
        return sum(t.completion_tokens or 0 for t in self.turns)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def has_exact_tokens(self) -> bool:
        return any(
            t.prompt_tokens is not None and not t.tokens_estimated for t in self.turns
        )

    @property
    def total_elapsed_ms(self) -> int:
        return sum(t.total_elapsed_ms or 0 for t in self.turns)

    def to_dict(self, *, include_turns: bool = True) -> dict:
        d = {
            "sessionId": self.session_id,
            "source": self.source,
            "label": self.label,
            "title": self.title,
            "editor": self.editor,
            "workspace": self.workspace,
            "format": self.fmt,
            "path": self.path,
            "created": self.created.isoformat() if self.created else None,
            "lastActivity": self.last_activity.isoformat()
            if self.last_activity
            else None,
            "numTurns": self.num_turns,
            "models": self.models,
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "totalTokens": self.total_tokens,
            "tokensExact": self.has_exact_tokens,
            "totalElapsedMs": self.total_elapsed_ms,
        }
        if include_turns:
            d["turns"] = [
                {
                    "index": t.index,
                    "requestId": t.request_id,
                    "when": t.when.isoformat() if t.when else None,
                    "model": t.model,
                    "promptTokens": t.prompt_tokens,
                    "completionTokens": t.completion_tokens,
                    "totalTokens": t.total_tokens,
                    "tokensEstimated": t.tokens_estimated,
                    "elapsedMs": t.total_elapsed_ms,
                    "ttftMs": t.ttft_ms,
                    "toolCalls": t.tool_calls,
                    "prompt": t.prompt,
                    "responseChars": t.response_chars,
                }
                for t in self.turns
            ]
        return d
