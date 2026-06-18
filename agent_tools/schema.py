from __future__ import annotations

from typing import Any


FIELDS = [
    "source",
    "run_id",
    "session_id",
    "session_label",
    "timestamp",
    "agent_name",
    "parent_agent_name",
    "model",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_tokens",
    "duration_ms",
    "tool_calls",
    "error_status",
    "workspace",
    "user",
    "field_confidence",
    "raw_source_ref",
]


def blank_row(source: str, raw_source_ref: str = "") -> dict[str, Any]:
    row = {field: "" for field in FIELDS}
    row["source"] = source
    row["raw_source_ref"] = raw_source_ref
    return row


def to_int(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return ""


def token_total(input_tokens: Any, output_tokens: Any) -> int | str:
    input_count = to_int(input_tokens)
    output_count = to_int(output_tokens)
    if input_count == "" or output_count == "":
        return ""
    return input_count + output_count


def cached_total(*values: Any) -> int | str:
    total = 0
    seen = False
    for value in values:
        count = to_int(value)
        if count != "":
            total += count
            seen = True
    return total if seen else ""
