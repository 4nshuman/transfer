from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agent_tools.schema import FIELDS


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def write_rows(rows: list[dict[str, Any]], path: Path, output_format: str) -> None:
    if output_format == "csv":
        write_csv(rows, path)
    else:
        write_jsonl(rows, path)
