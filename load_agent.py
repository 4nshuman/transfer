#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def default_source_dir() -> Path:
    return Path(__file__).resolve().parent / "agents"


def default_target_dir() -> Path:
    return Path.home() / ".copilot" / "agents"


def find_agent_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    return sorted(path for path in source_dir.glob("*.agent.md") if path.is_file())


def load_agents(source_dir: Path, target_dir: Path, dry_run: bool = False) -> list[dict[str, str]]:
    actions = []
    agent_files = find_agent_files(source_dir)
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    for source in agent_files:
        target = target_dir / source.name
        status = "created"
        if target.exists():
            status = "unchanged" if target.read_bytes() == source.read_bytes() else "updated"
        if not dry_run and status != "unchanged":
            shutil.copy2(source, target)
        actions.append({"source": str(source), "target": str(target), "status": status})

    return actions


def print_actions(actions: list[dict[str, str]], dry_run: bool) -> None:
    prefix = "Would load" if dry_run else "Loaded"
    if not actions:
        print("No agent files found.")
        return
    for action in actions:
        print(f"{prefix} {action['source']} -> {action['target']} ({action['status']})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load local agent files into the Copilot agents directory.")
    parser.add_argument("--source-dir", type=Path, default=default_source_dir())
    parser.add_argument("--target-dir", type=Path, default=default_target_dir())
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    actions = load_agents(args.source_dir, args.target_dir, args.dry_run)
    print_actions(actions, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
