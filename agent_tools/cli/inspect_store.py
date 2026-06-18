from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from agent_tools.json_helpers import print_json


def inspect_sqlite_tables(path: Path) -> list[str]:
    if not path.exists():
        return []
    with sqlite3.connect(path) as connection:
        cursor = connection.execute("select name from sqlite_master where type = 'table' order by name")
        return [row[0] for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="List tables in a Copilot CLI SQLite session store.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    print_json({"path": str(args.path), "tables": inspect_sqlite_tables(args.path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
