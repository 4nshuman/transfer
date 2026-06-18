from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from agent_tools.json_helpers import print_json
from agent_tools.schema import blank_row
from agent_tools.write_output import write_rows


LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"\[(?P<level>[A-Za-z]+)\]\s+(?P<message>.*)$"
)
REQUEST_ID_RE = re.compile(r"requestId:\s*\[?(?P<id>[0-9a-fA-F-]{36})\]?")
SESSION_ID_RE = re.compile(r"session(?:Id| id)[:=]\s*\[?(?P<id>[A-Za-z0-9_.:-]+)\]?", re.IGNORECASE)
MODEL_RE = re.compile(r"model(?: deployment ID)?[:=]\s*\[(?P<model>[^\]]*)\]", re.IGNORECASE)
USER_RE = re.compile(r"(?:Logged in as|Got Copilot token for)\s+(?P<user>[A-Za-z0-9_.-]+)")
COMPONENT_RE = re.compile(r"^\[(?P<component>[^\]]+)\]\s*(?P<message>.*)$")
HOME_PATH_RE = re.compile(r"(?:/Users|/home)/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE)


def is_vscode_copilot_log(path: Path) -> bool:
    path_text = str(path).lower()
    name = path.name.lower()
    return (
        path.is_file()
        and path.suffix.lower() == ".log"
        and (
            "github.copilot-chat" in path_text
            or "github copilot" in name
            or name == "agentsessionsoutput.log"
        )
    )


def find_vscode_log_files(logs_dir: Path) -> list[Path]:
    if not logs_dir.exists():
        return []
    return sorted(path for path in logs_dir.rglob("*.log") if is_vscode_copilot_log(path))


def collect_vscode_logs(logs_dir: Path, include_info: bool = False) -> list[dict[str, Any]]:
    rows = []
    for path in find_vscode_log_files(logs_dir):
        rows.extend(parse_vscode_log_file(path, include_info))
    return rows


def parse_vscode_log_file(path: Path, include_info: bool = False) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            parsed = parse_vscode_log_line(line.rstrip("\n"))
            if not parsed or not should_keep(parsed, include_info):
                continue
            rows.append(row_from_log_event(path, line_number, parsed))
    return rows


def parse_vscode_log_line(line: str) -> dict[str, str] | None:
    match = LINE_RE.match(line)
    if not match:
        return None

    message = match.group("message").strip()
    component = ""
    component_match = COMPONENT_RE.match(message)
    if component_match:
        component = component_match.group("component")
        message = component_match.group("message").strip()

    return {
        "timestamp": match.group("timestamp").replace(" ", "T", 1),
        "level": match.group("level").lower(),
        "component": component,
        "message": message,
    }


def should_keep(parsed: dict[str, str], include_info: bool) -> bool:
    level = parsed["level"]
    message = parsed["message"].lower()
    if include_info:
        return True
    return level in {"error", "warning", "warn"} or "request done" in message or "failed" in message


def row_from_log_event(path: Path, line_number: int, parsed: dict[str, str]) -> dict[str, Any]:
    message = parsed["message"]
    level = parsed["level"]
    row = blank_row("vscode_logs", f"{path}:{line_number}")
    row.update(
        {
            "run_id": extract_request_id(message),
            "session_id": extract_session_id(message),
            "timestamp": parsed["timestamp"],
            "agent_name": parsed["component"] or "GitHub Copilot Chat",
            "model": extract_model(message),
            "error_status": error_status(level, message),
            "user": extract_user(message),
            "field_confidence": "low",
        }
    )
    return row


def extract_request_id(message: str) -> str:
    match = REQUEST_ID_RE.search(message)
    return match.group("id") if match else ""


def extract_session_id(message: str) -> str:
    match = SESSION_ID_RE.search(message)
    return match.group("id") if match else ""


def extract_model(message: str) -> str:
    match = MODEL_RE.search(message)
    if not match:
        return ""
    return match.group("model").strip()


def extract_user(message: str) -> str:
    match = USER_RE.search(message)
    return match.group("user") if match else ""


def error_status(level: str, message: str) -> str:
    if level not in {"error", "warning", "warn"}:
        return ""
    return f"{level}: {sanitize_message(message)}"


def sanitize_message(message: str) -> str:
    message = HOME_PATH_RE.sub("~", message)
    message = re.sub(r"(token[:=]\s*)[^\s]+", r"\1[redacted]", message, flags=re.IGNORECASE)
    message = re.sub(r"(Bearer\s+)[A-Za-z0-9_.-]+", r"\1[redacted]", message)
    if len(message) > 240:
        return message[:237].rstrip() + "..."
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect VS Code GitHub Copilot diagnostic log events.")
    parser.add_argument("logs_dir", type=Path)
    parser.add_argument("--include-info", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    args = parser.parse_args()

    rows = collect_vscode_logs(args.logs_dir, args.include_info)
    if args.output:
        write_rows(rows, args.output, args.format)
        print_json({"output": str(args.output), "rows": len(rows), "format": args.format})
    else:
        print_json(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
