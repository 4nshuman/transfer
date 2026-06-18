#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agent_tools.cli.collect_sessions import collect_cli_sessions
from agent_tools.cli.inspect_store import inspect_sqlite_tables
from agent_tools.discovery.discover_sources import discover_sources
from agent_tools.sdk.collect_jsonl import collect_sdk_jsonl
from agent_tools.vscode.collect_chat_sessions import collect_vscode_chat_sessions
from agent_tools.vscode.collect_logs import collect_vscode_logs
from agent_tools.json_helpers import print_json
from agent_tools.write_output import write_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect GitHub Copilot observability data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Show available local and configured sources.")
    discover.add_argument("--cli-state-dir", type=Path)
    discover.add_argument("--cli-store-db", type=Path)
    discover.add_argument("--sdk-jsonl", type=Path)

    collect = subparsers.add_parser("collect", help="Collect normalized observations.")
    collect.add_argument("--cli-state-dir", type=Path)
    collect.add_argument("--sdk-jsonl", type=Path)
    collect.add_argument("--vscode-logs-dir", type=Path)
    collect.add_argument("--vscode-workspace-storage-dir", type=Path)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")

    inspect_db = subparsers.add_parser("inspect-store", help="List tables in a Copilot CLI SQLite session store.")
    inspect_db.add_argument("path", type=Path)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "discover":
        print_json(discover_sources(args.cli_state_dir, args.cli_store_db, args.sdk_jsonl))
        return 0

    if args.command == "inspect-store":
        print_json({"path": str(args.path), "tables": inspect_sqlite_tables(args.path)})
        return 0

    if args.command == "collect":
        rows = []
        if args.sdk_jsonl:
            rows.extend(collect_sdk_jsonl(args.sdk_jsonl))
        if args.cli_state_dir:
            rows.extend(collect_cli_sessions(args.cli_state_dir))
        if args.vscode_logs_dir:
            rows.extend(collect_vscode_logs(args.vscode_logs_dir))
        if args.vscode_workspace_storage_dir:
            rows.extend(collect_vscode_chat_sessions(args.vscode_workspace_storage_dir))
        write_rows(rows, args.output, args.format)
        print_json({"output": str(args.output), "rows": len(rows), "format": args.format})
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
