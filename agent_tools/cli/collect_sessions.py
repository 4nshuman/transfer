from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_tools.json_helpers import find_first, first_present, json_dumps, print_json, read_json_file, read_jsonl
from agent_tools.schema import blank_row, cached_total, to_int, token_total
from agent_tools.write_output import write_rows


LABEL_KEYS = (
    "sessionLabel",
    "session_label",
    "conversationTitle",
    "conversation_title",
    "customTitle",
    "title",
    "summary",
)


def extract_cli_tool_calls(value: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            kind = str(first_present(node, "type", "event_type", "role", "kind"))
            name = first_present(node, "toolName", "tool_name", "name")
            if "tool" in kind.lower() or first_present(node, "toolCallId", "tool_call_id"):
                calls.append(
                    {
                        "id": str(first_present(node, "toolCallId", "tool_call_id", "id")),
                        "name": str(name or ""),
                        "status": str(first_present(node, "status", "state") or ""),
                        "error": str(first_present(node, "error", "errorMessage", "message") or ""),
                    }
                )
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return calls


def normalize_cli_object(
    value: Any,
    raw_source_ref: str,
    session_id_hint: str = "",
    session_label_hint: str = "",
) -> dict[str, Any]:
    row = blank_row("cli_session", raw_source_ref)
    input_tokens = find_first(value, "inputTokens", "input_tokens", "prompt_tokens")
    output_tokens = find_first(value, "outputTokens", "output_tokens", "completion_tokens")
    cached_tokens = find_first(value, "cachedTokens", "cached_tokens")
    if cached_tokens == "":
        cached_tokens = cached_total(
            find_first(value, "cacheReadTokens", "cache_read_tokens"),
            find_first(value, "cacheWriteTokens", "cache_write_tokens"),
        )

    session_id = find_first(value, "sessionId", "session_id", "sessionID", "conversationId", "conversation_id")
    if not session_id:
        session_id = session_id_hint or find_first(value, "id") or raw_ref_stem(raw_source_ref)

    row.update(
        {
            "run_id": str(find_first(value, "runId", "run_id", "taskId", "task_id") or ""),
            "session_id": str(session_id),
            "session_label": session_label_hint or extract_session_label(value),
            "timestamp": str(find_first(value, "timestamp", "createdAt", "created_at", "startedAt", "started_at")),
            "agent_name": str(find_first(value, "agentName", "agent_name", "agentDisplayName")),
            "parent_agent_name": str(find_first(value, "parentAgentName", "parent_agent_name")),
            "model": str(find_first(value, "model", "modelName", "model_name")),
            "input_tokens": to_int(input_tokens),
            "output_tokens": to_int(output_tokens),
            "total_tokens": token_total(input_tokens, output_tokens),
            "cached_tokens": cached_tokens,
            "duration_ms": to_int(find_first(value, "durationMs", "duration_ms", "duration")),
            "tool_calls": json_dumps(extract_cli_tool_calls(value)),
            "error_status": _session_error(value),
            "workspace": str(find_first(value, "workspace", "cwd", "gitRoot", "repository", "repo")),
            "user": str(find_first(value, "user", "login", "username")),
            "field_confidence": "medium",
        }
    )
    return row


def extract_session_label(value: Any) -> str:
    return clean_label(find_first(value, *LABEL_KEYS))


def clean_label(value: Any) -> str:
    if value in (None, "") or isinstance(value, (dict, list)):
        return ""
    label = " ".join(str(value).split())
    if len(label) > 120:
        return label[:117].rstrip() + "..."
    return label


def raw_ref_stem(raw_source_ref: str) -> str:
    path_text = raw_source_ref
    suffix = raw_source_ref.rsplit(":", 1)
    if len(suffix) == 2 and suffix[1].isdigit():
        path_text = suffix[0]
    return Path(path_text).stem


def _session_error(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(first_present(value, "error", "errorStatus", "error_status", "state", "status") or "")


def session_dir_for_path(session_state_dir: Path, path: Path) -> Path | None:
    try:
        relative = path.relative_to(session_state_dir)
    except ValueError:
        return None
    if len(relative.parts) < 2:
        return None
    candidate = session_state_dir / relative.parts[0]
    return candidate if candidate.is_dir() else None


def session_label_for_dir(session_dir: Path) -> str:
    label = session_label_from_metadata(session_dir / "vscode.metadata.json")
    if label:
        return label
    label = session_label_from_workspace(session_dir / "workspace.yaml")
    if label:
        return label
    return session_label_from_first_user_message(session_dir / "events.jsonl")


def session_label_from_metadata(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return extract_session_label(read_json_file(path))
    except json.JSONDecodeError:
        return ""


def session_label_from_workspace(path: Path) -> str:
    if not path.exists():
        return ""

    summary_lines = []
    in_summary = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not in_summary:
            if not line.startswith("summary:"):
                continue
            value = line.split(":", 1)[1].strip()
            if value and value not in {"|", "|-", ">", ">-"}:
                return clean_label(value)
            in_summary = True
            continue

        if line and not line.startswith((" ", "\t")):
            break
        stripped = line.strip()
        if stripped:
            summary_lines.append(stripped)

    return first_meaningful_label(summary_lines)


def session_label_from_first_user_message(path: Path) -> str:
    if not path.exists():
        return ""

    for record in read_jsonl(path):
        if record.get("type") != "user.message":
            continue
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        label = first_meaningful_label(str(first_present(data, "content", "transformedContent")).splitlines())
        if label:
            return label
    return ""


def first_meaningful_label(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("<") or stripped.startswith("@/"):
            continue
        return clean_label(stripped)
    return clean_label(" ".join(lines))


def collect_cli_sessions(session_state_dir: Path) -> list[dict[str, Any]]:
    if not session_state_dir.exists():
        return []

    rows = []
    labels_by_dir: dict[Path, str] = {}
    for path in sorted(session_state_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        session_dir = session_dir_for_path(session_state_dir, path)
        session_id_hint = session_dir.name if session_dir else ""
        if session_dir and session_dir not in labels_by_dir:
            labels_by_dir[session_dir] = session_label_for_dir(session_dir)
        session_label_hint = labels_by_dir.get(session_dir, "") if session_dir else ""

        if path.suffix.lower() == ".jsonl":
            for index, record in enumerate(read_jsonl(path), start=1):
                rows.append(normalize_cli_object(record, f"{path}:{index}", session_id_hint, session_label_hint))
        else:
            try:
                rows.append(normalize_cli_object(read_json_file(path), str(path), session_id_hint, session_label_hint))
            except json.JSONDecodeError:
                row = blank_row("cli_session", str(path))
                row["session_id"] = session_id_hint
                row["session_label"] = session_label_hint
                row["error_status"] = "invalid json"
                row["field_confidence"] = "high"
                rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Copilot CLI session observability.")
    parser.add_argument("session_state_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    args = parser.parse_args()

    rows = collect_cli_sessions(args.session_state_dir)
    if args.output:
        write_rows(rows, args.output, args.format)
        print_json({"output": str(args.output), "rows": len(rows), "format": args.format})
    else:
        print_json(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
