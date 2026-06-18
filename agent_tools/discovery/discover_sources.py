from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from agent_tools.json_helpers import print_json
from agent_tools.vscode.collect_chat_sessions import find_vscode_chat_debug_files
from agent_tools.vscode.collect_logs import find_vscode_log_files


def discover_sources(
    cli_state_dir: Path | None = None,
    cli_store_db: Path | None = None,
    sdk_jsonl: Path | None = None,
) -> list[dict[str, Any]]:
    home = Path.home()
    cli_state_dir = cli_state_dir or home / ".copilot" / "session-state"
    cli_store_db = cli_store_db or home / ".copilot" / "session-store.db"
    vscode_logs_dir = home / "Library" / "Application Support" / "Code" / "logs"
    vscode_workspace_storage_dir = home / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage"
    if sdk_jsonl is None and os.environ.get("COPILOT_SDK_TELEMETRY_FILE"):
        sdk_jsonl = Path(os.environ["COPILOT_SDK_TELEMETRY_FILE"])
    vscode_log_files = find_vscode_log_files(vscode_logs_dir)
    vscode_chat_debug_files = find_vscode_chat_debug_files(vscode_workspace_storage_dir)

    return [
        {
            "source": "cli_session_state",
            "available": cli_state_dir.exists(),
            "path": str(cli_state_dir),
            "collector": "agent_tools.cli.collect_sessions" if cli_state_dir.exists() else "",
        },
        {
            "source": "cli_session_store",
            "available": cli_store_db.exists(),
            "path": str(cli_store_db),
            "collector": "agent_tools.cli.inspect_store" if cli_store_db.exists() else "",
        },
        {
            "source": "sdk_jsonl",
            "available": bool(sdk_jsonl and sdk_jsonl.exists()),
            "path": str(sdk_jsonl or ""),
            "collector": "agent_tools.sdk.collect_jsonl" if sdk_jsonl and sdk_jsonl.exists() else "",
        },
        {
            "source": "github_api",
            "available": bool(os.environ.get("GITHUB_TOKEN")),
            "path": "https://api.github.com",
            "collector": "not_implemented_yet",
        },
        {
            "source": "vscode_logs",
            "available": bool(vscode_log_files),
            "path": str(vscode_logs_dir),
            "collector": "agent_tools.vscode.collect_logs" if vscode_log_files else "",
        },
        {
            "source": "vscode_chat_debug",
            "available": bool(vscode_chat_debug_files),
            "path": str(vscode_workspace_storage_dir),
            "collector": "agent_tools.vscode.collect_chat_sessions" if vscode_chat_debug_files else "",
        },
        {
            "source": "xcode_logs",
            "available": (home / "Library" / "Logs" / "GitHubCopilot").exists(),
            "path": str(home / "Library" / "Logs" / "GitHubCopilot"),
            "collector": "not_implemented_yet",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover available Copilot observability sources.")
    parser.add_argument("--cli-state-dir", type=Path)
    parser.add_argument("--cli-store-db", type=Path)
    parser.add_argument("--sdk-jsonl", type=Path)
    args = parser.parse_args()

    print_json(discover_sources(args.cli_state_dir, args.cli_store_db, args.sdk_jsonl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
