from __future__ import annotations

import csv
import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence


def _temp_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _temp_path(path)
    try:
        tmp_path.write_text(text, encoding=encoding)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def atomic_write_csv_rows(
    path: Path,
    rows: Iterable[Sequence[Any]],
    encoding: str = "utf-8-sig",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _temp_path(path)
    try:
        with tmp_path.open("w", encoding=encoding, newline="") as handle:
            writer = csv.writer(handle)
            writer.writerows(rows)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def atomic_write_csv_dicts(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, Any]],
    encoding: str = "utf-8-sig",
) -> None:
    if not fieldnames:
        atomic_write_text(path, "", encoding=encoding)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _temp_path(path)
    try:
        with tmp_path.open("w", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
