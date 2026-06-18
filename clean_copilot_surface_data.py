#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


VSCODE_APP_NAMES = ("Code", "Code - Insiders", "VSCodium")
CHAT_DATA_NAMES = ("debug-logs", "transcripts", "chat-session-resources")


def add_existing(targets: dict[Path, str], path: Path, group: str) -> None:
    if path.exists():
        targets[path.resolve()] = group


def cli_targets(home: Path) -> dict[Path, str]:
    targets: dict[Path, str] = {}
    session_state = home / ".copilot" / "session-state"
    if session_state.exists():
        for path in session_state.iterdir():
            if path.is_dir():
                targets[path.resolve()] = "cli_session_state"

    copilot_dir = home / ".copilot"
    for name in (
        "session-store.db",
        "session-store.db-shm",
        "session-store.db-wal",
        "vscode.session.metadata.cache.json",
    ):
        add_existing(targets, copilot_dir / name, "cli_session_metadata")
    return targets


def vscode_targets(home: Path) -> dict[Path, str]:
    targets: dict[Path, str] = {}
    for app_name in VSCODE_APP_NAMES:
        app_dir = home / "Library" / "Application Support" / app_name
        add_vscode_log_targets(targets, app_dir / "logs")
        add_vscode_workspace_targets(targets, app_dir / "User" / "workspaceStorage")
    return targets


def add_vscode_log_targets(targets: dict[Path, str], logs_dir: Path) -> None:
    if not logs_dir.exists():
        return
    for path in logs_dir.rglob("*"):
        name = path.name.lower()
        path_text = str(path).lower()
        if path.is_dir() and path.name == "GitHub.copilot-chat":
            targets[path.resolve()] = "vscode_diagnostic_logs"
        elif path.is_file() and (
            name == "agentsessionsoutput.log"
            or "github copilot" in name
            or "github.copilot" in path_text
        ):
            targets[path.resolve()] = "vscode_diagnostic_logs"


def add_vscode_workspace_targets(targets: dict[Path, str], storage_dir: Path) -> None:
    if not storage_dir.exists():
        return
    for chat_dir in storage_dir.glob("*/GitHub.copilot-chat"):
        if not chat_dir.is_dir():
            continue
        for name in CHAT_DATA_NAMES:
            add_existing(targets, chat_dir / name, f"vscode_chat_{name}")


def xcode_targets(home: Path) -> dict[Path, str]:
    targets: dict[Path, str] = {}
    add_existing(targets, home / "Library" / "Logs" / "GitHubCopilot", "xcode_logs")
    return targets


def find_targets(home: Path) -> list[dict[str, str]]:
    targets: dict[Path, str] = {}
    for group in (cli_targets(home), vscode_targets(home), xcode_targets(home)):
        targets.update(group)

    pruned = prune_nested_paths(sorted(targets))
    return [
        {
            "path": str(path),
            "surface": targets[path],
            "type": "directory" if path.is_dir() else "file",
        }
        for path in pruned
    ]


def prune_nested_paths(paths: list[Path]) -> list[Path]:
    kept: list[Path] = []
    for path in paths:
        if any(is_relative_to(path, parent) for parent in kept):
            continue
        kept.append(path)
    return kept


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def delete_targets(targets: list[dict[str, str]], home: Path, apply: bool) -> list[dict[str, str]]:
    actions = []
    for target in targets:
        path = Path(target["path"])
        action = dict(target)
        if not is_relative_to(path, home):
            action["status"] = "skipped_outside_home"
        elif apply:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            action["status"] = "deleted"
        else:
            action["status"] = "would_delete"
        actions.append(action)
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean raw local Copilot logs and debug/session data.")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--apply", action="store_true", help="Delete files. Without this flag, only previews changes.")
    args = parser.parse_args()

    home = args.home.resolve()
    targets = find_targets(home)
    actions = delete_targets(targets, home, args.apply)
    print(
        json.dumps(
            {
                "home": str(home),
                "mode": "delete" if args.apply else "dry-run",
                "count": len(actions),
                "actions": actions,
                "note": "Close Copilot surfaces before --apply so they do not immediately recreate files.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
