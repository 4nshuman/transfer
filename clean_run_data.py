#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


GENERATED_FILE_PATTERNS = (
    "observations.jsonl",
    "*-observations.jsonl",
    "all-sources-observations.jsonl",
    "session_rundown.jsonl",
    "session_rundown.csv",
    "session_detailed_rundown.jsonl",
    "session_detailed_rundown.csv",
    "session_detailed_rundown.md",
    "session_labels_*.csv",
)


def generated_files(root: Path) -> list[Path]:
    matches = set()
    for pattern in GENERATED_FILE_PATTERNS:
        for path in root.glob(pattern):
            if path.is_file():
                matches.add(path)
    return sorted(matches)


def cache_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("__pycache__") if path.is_dir())


def find_targets(root: Path) -> list[Path]:
    return generated_files(root) + cache_dirs(root)


def clean_targets(targets: list[Path], apply: bool) -> list[dict[str, str]]:
    actions = []
    for path in targets:
        action = {"path": str(path), "type": "directory" if path.is_dir() else "file"}
        if apply:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            action["status"] = "deleted"
        else:
            action["status"] = "would_delete"
        actions.append(action)
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean generated Copilot observability run data.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--apply", action="store_true", help="Delete files. Without this flag, only previews changes.")
    args = parser.parse_args()

    root = args.root.resolve()
    actions = clean_targets(find_targets(root), args.apply)
    print(
        json.dumps(
            {
                "root": str(root),
                "mode": "delete" if args.apply else "dry-run",
                "count": len(actions),
                "actions": actions,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
