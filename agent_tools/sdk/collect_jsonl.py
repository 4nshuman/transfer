from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from agent_tools.json_helpers import first_present, json_dumps, print_json, read_jsonl
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


def event_type(event: dict[str, Any]) -> str:
    return str(first_present(event, "type", "event_type", "eventName", "name"))


def event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = first_present(event, "data", "attributes", "body", "payload")
    return data if isinstance(data, dict) else {}


def event_session_id(event: dict[str, Any], default: str = "") -> str:
    data = event_data(event)
    session_id = first_present(
        event,
        "sessionId",
        "session_id",
        "sessionID",
        "conversationId",
        "conversation_id",
    )
    if session_id:
        return str(session_id)
    session_id = first_present(
        data,
        "sessionId",
        "session_id",
        "sessionID",
        "conversationId",
        "conversation_id",
    )
    return str(session_id or default)


def event_session_label(event: dict[str, Any]) -> str:
    data = event_data(event)
    return clean_label(first_present(data, *LABEL_KEYS) or first_present(event, *LABEL_KEYS))


def clean_label(value: Any) -> str:
    if value in (None, "") or isinstance(value, (dict, list)):
        return ""
    label = " ".join(str(value).split())
    if len(label) > 120:
        return label[:117].rstrip() + "..."
    return label


def summarize_tool_calls(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_session: dict[str, dict[str, dict[str, Any]]] = {}
    for event in events:
        kind = event_type(event)
        if not kind.startswith("tool."):
            continue

        data = event_data(event)
        session_id = event_session_id(event, "unknown")
        tool_call_id = str(
            first_present(data, "toolCallId", "tool_call_id", "callId", "call_id", "id")
            or event.get("id", "")
            or len(by_session.get(session_id, {}))
        )
        session_tools = by_session.setdefault(session_id, {})
        tool = session_tools.setdefault(
            tool_call_id,
            {
                "id": tool_call_id,
                "name": str(first_present(data, "toolName", "tool_name", "name") or ""),
                "status": "",
                "error": "",
            },
        )
        if not tool["name"]:
            tool["name"] = str(first_present(data, "toolName", "tool_name", "name") or "")
        if kind.endswith("_start") or kind.endswith(".start") or kind.endswith("started"):
            tool["status"] = "started"
        elif kind.endswith("_complete") or kind.endswith(".complete") or kind.endswith("completed"):
            success = first_present(data, "success", "ok")
            tool["status"] = "success" if success is True else "error" if success is False else "completed"
        elif "error" in kind or "failed" in kind:
            tool["status"] = "error"
        error = first_present(data, "error", "errorMessage", "message")
        if error:
            tool["error"] = str(error)

    return {session_id: list(tools.values()) for session_id, tools in by_session.items()}


def session_errors(events: list[dict[str, Any]]) -> dict[str, str]:
    errors = {}
    for event in events:
        kind = event_type(event)
        if "error" not in kind and "failed" not in kind:
            continue
        data = event_data(event)
        session_id = event_session_id(event, "unknown")
        message = first_present(data, "error", "errorMessage", "message", "reason")
        errors[session_id] = str(message or kind)
    return errors


def session_labels(events: list[dict[str, Any]]) -> dict[str, str]:
    labels = {}
    for event in events:
        label = event_session_label(event)
        if label:
            labels[event_session_id(event, "unknown")] = label
    return labels


def selected_agents(events: list[dict[str, Any]]) -> dict[str, str]:
    agents = {}
    for event in events:
        if event_type(event) not in ("subagent.selected", "subagent.started"):
            continue
        data = event_data(event)
        agent_name = first_present(data, "agentName", "agent_name", "agentDisplayName")
        if agent_name:
            agents[event_session_id(event, "unknown")] = str(agent_name)
    return agents


def collect_sdk_jsonl(path: Path) -> list[dict[str, Any]]:
    events = read_jsonl(path)
    tools_by_session = summarize_tool_calls(events)
    errors_by_session = session_errors(events)
    labels_by_session = session_labels(events)
    agents_by_session = selected_agents(events)
    rows = []

    for index, event in enumerate(events, start=1):
        kind = event_type(event)
        data = event_data(event)
        raw_ref = f"{path}:{index}"

        if kind == "assistant.usage":
            rows.append(_usage_row(path, event, data, raw_ref, tools_by_session, errors_by_session, labels_by_session, agents_by_session))
        elif kind in ("session.error", "subagent.failed", "parse.error"):
            rows.append(_error_row(path, event, data, raw_ref, labels_by_session, agents_by_session))

    return rows


def _usage_row(
    path: Path,
    event: dict[str, Any],
    data: dict[str, Any],
    raw_ref: str,
    tools_by_session: dict[str, list[dict[str, Any]]],
    errors_by_session: dict[str, str],
    labels_by_session: dict[str, str],
    agents_by_session: dict[str, str],
) -> dict[str, Any]:
    session_id = event_session_id(event, path.stem)
    input_tokens = first_present(data, "inputTokens", "input_tokens", "prompt_tokens")
    output_tokens = first_present(data, "outputTokens", "output_tokens", "completion_tokens")
    cached_tokens = first_present(data, "cachedTokens", "cached_tokens")
    if cached_tokens == "":
        cached_tokens = cached_total(
            first_present(data, "cacheReadTokens", "cache_read_tokens"),
            first_present(data, "cacheWriteTokens", "cache_write_tokens"),
        )

    row = blank_row("sdk_jsonl", raw_ref)
    row.update(
        {
            "run_id": str(first_present(data, "apiCallId", "api_call_id", "providerCallId", "provider_call_id") or event.get("id", "")),
            "session_id": session_id,
            "session_label": event_session_label(event) or labels_by_session.get(session_id, ""),
            "timestamp": str(first_present(event, "timestamp", "time") or first_present(data, "timestamp")),
            "agent_name": str(first_present(data, "agentName", "agent_name") or agents_by_session.get(session_id, "")),
            "parent_agent_name": str(first_present(data, "parentAgentName", "parent_agent_name")),
            "model": str(first_present(data, "model", "modelName", "model_name")),
            "input_tokens": to_int(input_tokens),
            "output_tokens": to_int(output_tokens),
            "total_tokens": token_total(input_tokens, output_tokens),
            "cached_tokens": cached_tokens,
            "duration_ms": to_int(first_present(data, "durationMs", "duration_ms", "duration")),
            "tool_calls": json_dumps(tools_by_session.get(session_id, [])),
            "error_status": errors_by_session.get(session_id, ""),
            "workspace": str(first_present(data, "workspace", "cwd", "gitRoot", "repository")),
            "user": str(first_present(data, "user", "login", "username")),
            "field_confidence": "high",
        }
    )
    return row


def _error_row(
    path: Path,
    event: dict[str, Any],
    data: dict[str, Any],
    raw_ref: str,
    labels_by_session: dict[str, str],
    agents_by_session: dict[str, str],
) -> dict[str, Any]:
    session_id = event_session_id(event, path.stem)
    row = blank_row("sdk_jsonl", raw_ref)
    row.update(
        {
            "run_id": str(event.get("id", "")),
            "session_id": session_id,
            "session_label": event_session_label(event) or labels_by_session.get(session_id, ""),
            "timestamp": str(first_present(event, "timestamp", "time")),
            "agent_name": str(first_present(data, "agentName", "agent_name") or agents_by_session.get(session_id, "")),
            "error_status": str(first_present(data, "error", "errorMessage", "message", "reason") or event_type(event)),
            "field_confidence": "high",
        }
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Copilot SDK JSONL observability.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    args = parser.parse_args()

    rows = collect_sdk_jsonl(args.path)
    if args.output:
        write_rows(rows, args.output, args.format)
        print_json({"output": str(args.output), "rows": len(rows), "format": args.format})
    else:
        print_json(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
