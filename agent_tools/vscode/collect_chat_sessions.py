from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from agent_tools.json_helpers import first_present, json_dumps, print_json
from agent_tools.schema import blank_row, to_int, token_total
from agent_tools.write_output import write_rows


def find_vscode_chat_debug_files(workspace_storage_dir: Path) -> list[Path]:
    if not workspace_storage_dir.exists():
        return []
    files = []
    for path in workspace_storage_dir.rglob("*.jsonl"):
        parts = set(path.parts)
        if path.name == "main.jsonl" and "GitHub.copilot-chat" in parts and "debug-logs" in parts:
            files.append(path)
    return sorted(files)


def collect_vscode_chat_sessions(workspace_storage_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in find_vscode_chat_debug_files(workspace_storage_dir):
        rows.extend(parse_chat_debug_file(path))
    return rows


def parse_chat_debug_file(path: Path) -> list[dict[str, Any]]:
    records = read_debug_records(path)
    tool_calls = summarize_tool_calls(records)
    session_labels = extract_session_labels(path, records)
    workspace = workspace_for_debug_file(path)
    rows = []

    for line_number, record in records:
        if record.get("type") != "llm_request":
            continue
        rows.append(row_from_llm_request(path, line_number, record, tool_calls, session_labels, workspace))

    return rows


def read_debug_records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                records.append((line_number, {"type": "parse_error", "status": "error"}))
                continue
            if isinstance(value, dict):
                records.append((line_number, value))
    return records


def summarize_tool_calls(records: list[tuple[int, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for _, record in records:
        if record.get("type") != "tool_call":
            continue
        parent_id = str(record.get("parentSpanId") or record.get("sid", ""))
        by_parent.setdefault(parent_id, []).append(
            {
                "id": str(record.get("spanId", "")),
                "name": str(record.get("name", "")),
                "status": str(record.get("status", "")),
                "duration_ms": to_int(record.get("dur")),
            }
        )
    return by_parent


def row_from_llm_request(
    path: Path,
    line_number: int,
    record: dict[str, Any],
    tool_calls: dict[str, list[dict[str, Any]]],
    session_labels: dict[str, str],
    workspace: str,
) -> dict[str, Any]:
    attrs = record.get("attrs") if isinstance(record.get("attrs"), dict) else {}
    session_id = str(record.get("sid", ""))
    input_tokens = first_present(attrs, "inputTokens", "input_tokens", "promptTokens", "prompt_tokens")
    output_tokens = first_present(attrs, "outputTokens", "output_tokens", "completion_tokens")

    row = blank_row("vscode_chat_debug", f"{path}:{line_number}")
    row.update(
        {
            "run_id": str(first_present(attrs, "responseId", "requestId") or record.get("spanId", "")),
            "session_id": session_id,
            "session_label": session_labels.get(session_id, ""),
            "timestamp": timestamp_from_ms(record.get("ts")),
            "agent_name": str(first_present(attrs, "debugName", "agentId") or record.get("name", "")),
            "model": str(first_present(attrs, "model") or model_from_name(str(record.get("name", "")))),
            "input_tokens": to_int(input_tokens),
            "output_tokens": to_int(output_tokens),
            "total_tokens": token_total(input_tokens, output_tokens),
            "cached_tokens": to_int(first_present(attrs, "cachedTokens", "cached_tokens")),
            "duration_ms": to_int(record.get("dur")),
            "tool_calls": json_dumps(tool_calls.get(str(record.get("parentSpanId") or session_id), [])),
            "error_status": error_status(record, attrs),
            "workspace": workspace,
            "field_confidence": "high",
        }
    )
    return row


def extract_session_labels(path: Path, records: list[tuple[int, dict[str, Any]]]) -> dict[str, str]:
    labels = {}
    for _, record in records:
        if record.get("type") != "child_session_ref":
            continue
        attrs = record.get("attrs") if isinstance(record.get("attrs"), dict) else {}
        if attrs.get("label") != "title":
            continue
        child_log_file = attrs.get("childLogFile")
        if not isinstance(child_log_file, str):
            continue
        label = read_title_label(path.parent / child_log_file)
        if label:
            labels[str(record.get("sid", ""))] = label
    return labels


def read_title_label(path: Path) -> str:
    if not path.exists():
        return ""
    for _, record in read_debug_records(path):
        if record.get("type") != "agent_response":
            continue
        attrs = record.get("attrs") if isinstance(record.get("attrs"), dict) else {}
        label = response_text(attrs.get("response"))
        if label:
            return label
    return ""


def response_text(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value.strip()
    return first_text(value)


def first_text(value: Any) -> str:
    if isinstance(value, dict):
        text = value.get("content") or value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for child in value.values():
            found = first_text(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_text(child)
            if found:
                return found
    return ""


def timestamp_from_ms(value: Any) -> str:
    count = to_int(value)
    if count == "":
        return ""
    return datetime.fromtimestamp(count / 1000, UTC).isoformat().replace("+00:00", "Z")


def model_from_name(name: str) -> str:
    if name.startswith("chat:"):
        return name.split(":", 1)[1]
    return ""


def error_status(record: dict[str, Any], attrs: dict[str, Any]) -> str:
    status = str(record.get("status", ""))
    if status and status != "ok":
        return status
    return str(first_present(attrs, "error", "errorMessage", "message"))


def workspace_for_debug_file(path: Path) -> str:
    workspace_dir = workspace_storage_dir_for_file(path)
    if not workspace_dir:
        return ""
    workspace_file = workspace_dir / "workspace.json"
    if not workspace_file.exists():
        return ""
    try:
        data = json.loads(workspace_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return workspace_from_json(data)


def workspace_storage_dir_for_file(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name == "GitHub.copilot-chat":
            return parent.parent
    return None


def workspace_from_json(data: dict[str, Any]) -> str:
    folder = data.get("folder")
    if isinstance(folder, str):
        return file_uri_to_path(folder)
    workspace = data.get("workspace")
    if isinstance(workspace, str):
        return file_uri_to_path(workspace)
    return ""


def file_uri_to_path(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect VS Code Copilot Chat debug session observability.")
    parser.add_argument("workspace_storage_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    args = parser.parse_args()

    rows = collect_vscode_chat_sessions(args.workspace_storage_dir)
    if args.output:
        write_rows(rows, args.output, args.format)
        print_json({"output": str(args.output), "rows": len(rows), "format": args.format})
    else:
        print_json(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
