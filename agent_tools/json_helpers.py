from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return ""


def find_first(value: Any, *keys: str) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, "") and not isinstance(value[key], (dict, list)):
                return value[key]
        for child in value.values():
            found = find_first(child, *keys)
            if found != "":
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_first(child, *keys)
            if found != "":
                return found
    return ""


def json_dumps(value: Any) -> str:
    if value in ("", None):
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                records.append(
                    {
                        "type": "parse.error",
                        "timestamp": "",
                        "data": {"error": str(exc), "line": line_number},
                    }
                )
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))
