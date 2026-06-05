"""Filesystem and serialization helpers for paper_pool."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write text by replacing a temp file inside the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        temp_path.write_text(text, encoding=encoding, newline="")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
