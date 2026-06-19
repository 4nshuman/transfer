"""Discover and parse VS Code (and forks) Copilot Chat sessions.

Two on-disk formats coexist in `chatSessions/`:

* ``*.json``  — a plain JSON session object (older).
* ``*.jsonl`` — an event-sourced log (newer). Line 0 is
  ``{"kind":"0","v": <snapshot>}``; each later line mutates that state:
  ``kind:"1"`` sets the value at JSON path ``k``; ``kind:"2"`` appends/extends
  the array at path ``k``. We replay the log to rebuild the final session.

Per request we read: ``modelId``, ``timestamp``, ``result.timings`` (latency),
and ``result.usage`` (``promptTokens``/``completionTokens`` — exact tokens, only
in newer sessions). ``customTitle`` is the session label.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urlparse

from .models import Session, Turn
from .platforms import vscode_product_dirs

# Sessions can grow to gigabytes when responses embed large content/images.
# The fields we need for observability (modelId, timestamp, result.usage,
# result.timings) live on *small* event lines; only response-content appends
# are huge. We skip lines above this size before json.loads — this keeps token
# and latency accounting intact while making multi-GB files parse in seconds.
MAX_LINE_BYTES = 8 * 1024 * 1024
# Substrings that mark a line as carrying per-turn usage/latency we must keep.
# A giant line lacking all of these is pure response content and is skipped
# without paying the json.loads cost.
_KEEP_MARKERS = ('"promptTokens"', '"totalElapsed"')
# Plain .json sessions must be read whole; skip pathologically large ones.
MAX_JSON_BYTES = 400 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def load_all() -> list[Session]:
    sessions: list[Session] = []
    for f, editor, folder in discover_session_files():
        s = load_session(f, editor, folder)
        if s is not None:
            sessions.append(s)
    return sessions


def iter_sessions() -> Iterator[Session]:
    yield from load_all()


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_session_files() -> list[tuple[Path, str, str | None]]:
    """Return (sessionFile, editorName, workspaceFolder) for every session."""
    found: list[tuple[Path, str, str | None]] = []
    for editor, product in vscode_product_dirs():
        ws_root = product / "User" / "workspaceStorage"
        for ws_dir in ws_root.iterdir() if ws_root.is_dir() else []:
            cs = ws_dir / "chatSessions"
            if not cs.is_dir():
                continue
            folder = _workspace_folder(ws_dir)
            for f in cs.iterdir():
                if f.suffix in (".json", ".jsonl") and f.is_file():
                    found.append((f, editor, folder))
    return found


def _workspace_folder(ws_dir: Path) -> str | None:
    """Resolve workspaceStorage/<hash>/workspace.json → real folder path."""
    wj = ws_dir / "workspace.json"
    if not wj.is_file():
        return None
    try:
        data = json.loads(wj.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    uri = data.get("folder") or data.get("workspace")
    if not uri:
        return None
    if uri.startswith("file://"):
        return unquote(urlparse(uri).path)
    return uri


# --------------------------------------------------------------------------- #
# File loading
# --------------------------------------------------------------------------- #
def load_session(path: Path, editor: str | None, workspace: str | None) -> Session | None:
    try:
        if path.suffix == ".jsonl":
            raw, fmt = _replay_jsonl(path), "jsonl-events"
        else:
            if path.stat().st_size > MAX_JSON_BYTES:
                return None
            raw, fmt = json.loads(path.read_text(encoding="utf-8")), "json"
    except (ValueError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return _build_session(raw, path, editor, workspace, fmt)


def _replay_jsonl(path: Path) -> dict:
    """Rebuild final session state by replaying the kind 0/1/2 event log."""
    state: dict = {}
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            # Giant lines are response-content appends. Skip the json.loads
            # cost unless the line actually carries usage/latency we need.
            if len(line) > MAX_LINE_BYTES and not any(m in line for m in _KEEP_MARKERS):
                continue
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = str(ev.get("kind"))
            if kind == "0":
                v = ev.get("v")
                if isinstance(v, dict):
                    state = v
                continue
            path_segs = ev.get("k")
            if not isinstance(path_segs, list) or not path_segs:
                continue
            try:
                _apply(state, kind, path_segs, ev.get("v"))
            except (KeyError, IndexError, TypeError):
                continue  # tolerate schema drift; keep what we can
    return state


def _apply(state: dict, kind: str, segs: list, value) -> None:
    """Apply one event. kind '1' = set at path; '2' = append/extend array."""
    cur = state
    for i, seg in enumerate(segs[:-1]):
        nxt = segs[i + 1]
        if isinstance(seg, int):
            while len(cur) <= seg:
                cur.append([] if isinstance(nxt, int) else {})
            cur = cur[seg]
        else:
            if seg not in cur or not isinstance(cur[seg], (dict, list)):
                cur[seg] = [] if isinstance(nxt, int) else {}
            cur = cur[seg]
    last = segs[-1]
    if kind == "2":
        if isinstance(last, int):
            while len(cur) <= last:
                cur.append(None)
            tgt = cur[last]
        else:
            tgt = cur.get(last)
        if isinstance(tgt, list):
            tgt.extend(value) if isinstance(value, list) else tgt.append(value)
            return
        cur[last] = list(value) if isinstance(value, list) else [value]
    else:  # set
        if isinstance(last, int):
            while len(cur) <= last:
                cur.append(None)
            cur[last] = value
        else:
            cur[last] = value


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def _build_session(
    raw: dict, path: Path, editor: str | None, workspace: str | None, fmt: str
) -> Session:
    sess = Session(
        session_id=raw.get("sessionId") or path.stem,
        source="vscode",
        path=str(path),
        title=raw.get("customTitle"),
        editor=editor,
        workspace=workspace,
        created_ms=raw.get("creationDate"),
        last_ms=raw.get("lastMessageDate"),
        fmt=fmt,
    )
    for i, r in enumerate(raw.get("requests") or []):
        if isinstance(r, dict):
            sess.turns.append(_build_turn(i, r))
    return sess


def _build_turn(index: int, r: dict) -> Turn:
    result = r.get("result") or {}
    usage = result.get("usage") or {}
    timings = result.get("timings") or {}
    meta = result.get("metadata") or {}

    pt = usage.get("promptTokens")
    ct = usage.get("completionTokens")

    rounds = meta.get("toolCallRounds")
    tool_calls = len(rounds) if isinstance(rounds, list) else 0

    return Turn(
        index=index,
        request_id=r.get("requestId"),
        timestamp_ms=r.get("timestamp"),
        model=r.get("modelId"),
        prompt=_message_text(r.get("message")),
        response_chars=_response_len(r.get("response")),
        prompt_tokens=pt if isinstance(pt, int) else None,
        completion_tokens=ct if isinstance(ct, int) else None,
        total_elapsed_ms=timings.get("totalElapsed"),
        ttft_ms=timings.get("firstProgress"),
        tool_calls=tool_calls,
    )


def _message_text(message) -> str:
    if isinstance(message, dict):
        if isinstance(message.get("text"), str):
            return message["text"]
        parts = message.get("parts")
        if isinstance(parts, list):
            return " ".join(
                p.get("text", "") for p in parts if isinstance(p, dict)
            ).strip()
    return message if isinstance(message, str) else ""


def _response_len(response) -> int:
    """Best-effort character count of the assistant's rendered response."""
    if not isinstance(response, list):
        return 0
    total = 0
    for part in response:
        if not isinstance(part, dict):
            continue
        val = part.get("value")
        if isinstance(val, str):
            total += len(val)
        elif isinstance(val, dict) and isinstance(val.get("value"), str):
            total += len(val["value"])
    return total
