from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from agent_tools.json_helpers import print_json
from agent_tools.platform_paths import (
    default_cli_state_dir,
    default_cli_store_db,
    default_home,
    vscode_logs_dirs,
    vscode_workspace_storage_dirs,
    xcode_logs_dir,
)
from agent_tools.vscode.collect_chat_sessions import find_vscode_chat_debug_files
from agent_tools.vscode.collect_logs import find_vscode_log_files


def first_available_path(
    candidates: list[Path],
    finder: Callable[[Path], list[Path]],
) -> tuple[Path, list[Path]]:
    fallback = candidates[0] if candidates else Path()
    for path in candidates:
        files = finder(path)
        if files:
            return path, files
    return fallback, []


def discover_sources(
    cli_state_dir: Path | None = None,
    cli_store_db: Path | None = None,
    sdk_jsonl: Path | None = None,
    home: Path | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    current_home = default_home(home)
    current_env = os.environ if env is None else env
    cli_state_dir = cli_state_dir or default_cli_state_dir(current_home)
    cli_store_db = cli_store_db or default_cli_store_db(current_home)
    vscode_logs_dir, vscode_log_files = first_available_path(
        vscode_logs_dirs(current_home, platform, current_env),
        find_vscode_log_files,
    )
    vscode_workspace_storage_dir, vscode_chat_debug_files = first_available_path(
        vscode_workspace_storage_dirs(current_home, platform, current_env),
        find_vscode_chat_debug_files,
    )
    xcode_dir = xcode_logs_dir(current_home, platform)
    if sdk_jsonl is None and current_env.get("COPILOT_SDK_TELEMETRY_FILE"):
        sdk_jsonl = Path(current_env["COPILOT_SDK_TELEMETRY_FILE"])

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
            "available": bool(current_env.get("GITHUB_TOKEN")),
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
            "available": bool(xcode_dir and xcode_dir.exists()),
            "path": str(xcode_dir or ""),
            "collector": "not_implemented_yet" if xcode_dir and xcode_dir.exists() else "",
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
