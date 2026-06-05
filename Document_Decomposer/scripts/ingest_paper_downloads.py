from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_csv_dicts, write_json
from docdecomp.package_builder import content_tokens


SCHEMA_VERSION = "0.1.0"


def default_source_dir() -> Path:
    return ROOT.parent / "paper_pool" / "paper"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register PDFs from paper_pool with hash dedupe and stable Sxx staging."
    )
    parser.add_argument(
        "--source-dir",
        action="append",
        default=[],
        help="Directory or PDF file to scan. May be repeated. Defaults to ../paper_pool/paper.",
    )
    parser.add_argument("--manifest", default=str(ROOT / "data" / "ingest" / "paper_manifest.json"))
    parser.add_argument("--staging-dir", default=str(ROOT / "data" / "ingest" / "pdfs"))
    parser.add_argument("--report", default=str(ROOT / "reports" / "paper_ingest_report.csv"))
    parser.add_argument("--limit", type=int, default=None, help="Scan only the first N PDFs after sorting.")
    parser.add_argument("--start-index", type=int, default=None, help="First S number to use for new papers.")
    parser.add_argument("--no-stage", action="store_true", help="Do not copy new PDFs into the staging dir.")
    parser.add_argument("--force-stage", action="store_true", help="Re-copy staged PDFs even when they exist.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned ingest actions without writing files.")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        shutil.copy2(source, temp_path)
        temp_path.replace(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def s_number(paper_id: str) -> int | None:
    match = re.fullmatch(r"S(\d+)", paper_id)
    return int(match.group(1)) if match else None


def paper_id_from_stem(stem: str) -> str | None:
    match = re.match(r"^(S\d+)(?:_|$)", stem)
    return match.group(1) if match else None


def iter_pdfs(source_paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    results: list[Path] = []
    for source in source_paths:
        if not source.exists():
            continue
        paths = [source] if source.is_file() and source.suffix.lower() == ".pdf" else source.rglob("*.pdf")
        for path in paths:
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            results.append(path)
    return sorted(results, key=lambda item: str(item.resolve()).lower())


def collect_reserved_ids(manifest: dict[str, Any]) -> set[str]:
    reserved: set[str] = set()
    for paper in manifest.get("papers") or []:
        paper_id = str(paper.get("paper_id") or "")
        if paper_id:
            reserved.add(paper_id)

    for path in (ROOT / "library").iterdir() if (ROOT / "library").exists() else []:
        if path.is_dir() and re.fullmatch(r"S\d+", path.name):
            reserved.add(path.name)

    for folder in [
        ROOT / "data" / "docling" / "json",
        ROOT / "data" / "docling" / "md",
        ROOT / "data" / "docling_validation",
    ]:
        if not folder.exists():
            continue
        for path in folder.glob("*.*"):
            paper_id = paper_id_from_stem(path.stem)
            if paper_id:
                reserved.add(paper_id)
    return reserved


def collect_existing_hash_refs(manifest: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    refs: dict[str, list[dict[str, str]]] = {}

    for paper in manifest.get("papers") or []:
        sha = str(paper.get("sha256") or "")
        if sha:
            refs.setdefault(sha, []).append(
                {
                    "source": "manifest",
                    "paper_id": str(paper.get("paper_id") or ""),
                    "path": str(paper.get("original_path") or ""),
                }
            )

    library_dir = ROOT / "library"
    if library_dir.exists():
        for paper_dir in sorted(path for path in library_dir.iterdir() if path.is_dir()):
            source_pdf = load_json_if_exists(paper_dir / "source_pdf.json")
            sha = str(source_pdf.get("sha256") or "")
            if sha:
                refs.setdefault(sha, []).append(
                    {
                        "source": "library",
                        "paper_id": paper_dir.name,
                        "path": str(source_pdf.get("original_path") or paper_dir / "source.pdf"),
                    }
                )
    return refs


def filename_doi_key_loose(value: str) -> str:
    lowered = value.lower()
    match = re.search(r"j[._-]([a-z0-9]+)[._-](\d{4})[._-]([a-z0-9]+)", lowered)
    if match:
        return "".join(match.groups())
    match = re.search(r"10[._-]1016[._-]j[._-]([a-z0-9]+)[._-](\d{4})[._-]([a-z0-9]+)", lowered)
    if match:
        return "".join(match.groups())
    return ""


def identity_key(path: Path) -> str:
    doi_key = filename_doi_key_loose(path.name)
    if doi_key:
        return f"doi:{doi_key}"
    tokens = sorted(content_tokens(path.stem))
    if len(tokens) >= 4:
        return "tokens:" + "-".join(tokens[:16])
    return ""


def add_identity_ref(refs: dict[str, list[str]], value: str, paper_id: str) -> None:
    key = identity_key(Path(value))
    if key and paper_id:
        refs.setdefault(key, [])
        if paper_id not in refs[key]:
            refs[key].append(paper_id)


def collect_external_identity_refs() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}

    library_dir = ROOT / "library"
    if library_dir.exists():
        for paper_dir in sorted(path for path in library_dir.iterdir() if path.is_dir()):
            paper_id = paper_dir.name
            metadata = load_json_if_exists(paper_dir / "metadata_candidates.json").get("metadata_candidates") or {}
            source_pdf = load_json_if_exists(paper_dir / "source_pdf.json")
            for value in [
                str(source_pdf.get("original_filename") or ""),
                str(source_pdf.get("docling_origin_filename") or ""),
                str(metadata.get("docling_name") or ""),
                str(metadata.get("title") or ""),
            ]:
                add_identity_ref(refs, value, paper_id)

    for folder in [
        ROOT / "data" / "docling" / "json",
        ROOT / "data" / "docling" / "md",
        ROOT / "data" / "docling_validation",
    ]:
        if not folder.exists():
            continue
        for path in folder.glob("*.*"):
            paper_id = paper_id_from_stem(path.stem)
            if paper_id:
                add_identity_ref(refs, path.stem, paper_id)
    return refs


def collect_identity_refs(manifest: dict[str, Any]) -> dict[str, list[str]]:
    refs = collect_external_identity_refs()
    for paper in manifest.get("papers") or []:
        key = str(paper.get("identity_key") or "")
        paper_id = str(paper.get("paper_id") or "")
        if key and paper_id:
            refs.setdefault(key, [])
            if paper_id not in refs[key]:
                refs[key].append(paper_id)
    return refs


def token_duplicate_candidates(
    path: Path,
    records: list[dict[str, Any]],
    threshold: float = 0.72,
    exclude_paper_id: str = "",
) -> list[str]:
    candidate_tokens = content_tokens(path.stem)
    if not candidate_tokens:
        return []
    matches: list[str] = []
    for record in records:
        paper_id = str(record.get("paper_id") or "")
        if not paper_id or paper_id == exclude_paper_id:
            continue
        values = [
            str(record.get("original_filename") or ""),
            str(record.get("staged_pdf") or ""),
            str(record.get("identity_key") or ""),
        ]
        best = 0.0
        for value in values:
            existing_tokens = content_tokens(value)
            if not existing_tokens:
                continue
            overlap = len(candidate_tokens & existing_tokens) / max(1, min(len(candidate_tokens), len(existing_tokens)))
            best = max(best, overlap)
        if best >= threshold:
            matches.append(paper_id)
    return matches


def identity_for_record(record: dict[str, Any]) -> str:
    for value in [
        str(record.get("original_filename") or ""),
        str(record.get("staged_pdf") or ""),
        str(record.get("original_path") or ""),
    ]:
        key = identity_key(Path(value))
        if key:
            return key
    return ""


def refresh_manifest_identity(papers: list[dict[str, Any]]) -> None:
    external_refs = collect_external_identity_refs()
    for record in papers:
        paper_id = str(record.get("paper_id") or "")
        if not paper_id:
            continue
        identity = identity_for_record(record)
        if identity:
            record["identity_key"] = identity

    for record in papers:
        paper_id = str(record.get("paper_id") or "")
        if not paper_id:
            continue
        identity = str(record.get("identity_key") or "")
        possible_duplicates: list[str] = []
        if identity:
            possible_duplicates.extend(item for item in external_refs.get(identity, []) if item != paper_id)

        original_filename = str(record.get("original_filename") or "")
        if original_filename:
            for duplicate_id in token_duplicate_candidates(
                Path(original_filename),
                papers,
                exclude_paper_id=paper_id,
            ):
                if duplicate_id not in possible_duplicates:
                    possible_duplicates.append(duplicate_id)
        record["possible_duplicate_of"] = possible_duplicates


def next_paper_id(used: set[str], current: int) -> tuple[str, int]:
    number = current
    while True:
        paper_id = f"S{number:02d}"
        number += 1
        if paper_id not in used:
            used.add(paper_id)
            return paper_id, number


def safe_stem(paper_id: str, original_stem: str, max_len: int = 150) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", original_stem)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-") or "paper"
    if cleaned.startswith(f"{paper_id}_"):
        stem = cleaned
    else:
        stem = f"{paper_id}_{cleaned}"
    return stem[:max_len].rstrip("._-")


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def existing_max_s_number(ids: set[str]) -> int:
    numbers = [number for number in (s_number(paper_id) for paper_id in ids) if number is not None]
    return max(numbers, default=0)


def build_manifest(
    manifest: dict[str, Any],
    source_dirs: list[Path],
    staging_dir: Path,
    start_index: int | None,
    limit: int | None,
    dry_run: bool,
    no_stage: bool,
    force_stage: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    now = utc_now()
    papers = list(manifest.get("papers") or [])
    refresh_manifest_identity(papers)
    reserved_ids = collect_reserved_ids(manifest)
    hash_refs = collect_existing_hash_refs(manifest)
    identity_refs = collect_identity_refs(manifest)
    next_number = start_index if start_index is not None else existing_max_s_number(reserved_ids) + 1

    pdfs = iter_pdfs(source_dirs)
    if limit is not None:
        pdfs = pdfs[:limit]

    rows: list[dict[str, Any]] = []
    for pdf_path in pdfs:
        resolved = pdf_path.resolve()
        sha = sha256_file(pdf_path)
        size_bytes = pdf_path.stat().st_size
        identity = identity_key(pdf_path)
        duplicate_refs = hash_refs.get(sha) or []
        if duplicate_refs:
            first_ref = duplicate_refs[0]
            rows.append(
                {
                    "paper_id": first_ref.get("paper_id", ""),
                    "status": f"duplicate_{first_ref.get('source', 'known')}",
                    "original_filename": pdf_path.name,
                    "original_path": str(resolved),
                    "sha256": sha,
                    "size_bytes": size_bytes,
                    "staged_pdf": "",
                    "identity_key": identity,
                    "possible_duplicate_of": "",
                    "duplicate_of": first_ref.get("paper_id", ""),
                }
            )
            continue

        paper_id, next_number = next_paper_id(reserved_ids, next_number)
        staged_name = f"{safe_stem(paper_id, pdf_path.stem)}.pdf"
        staged_path = staging_dir / staged_name
        suffix = 2
        while staged_path.exists() and sha256_file(staged_path) != sha:
            staged_path = staging_dir / f"{safe_stem(paper_id, pdf_path.stem, 140)}_{suffix}.pdf"
            suffix += 1

        possible_duplicates = list(identity_refs.get(identity, [])) if identity else []
        for duplicate_id in token_duplicate_candidates(pdf_path, papers):
            if duplicate_id not in possible_duplicates:
                possible_duplicates.append(duplicate_id)
        record = {
            "paper_id": paper_id,
            "status": "active",
            "sha256": sha,
            "size_bytes": size_bytes,
            "original_filename": pdf_path.name,
            "original_path": str(resolved),
            "staged_pdf": relative_or_absolute(staged_path),
            "identity_key": identity,
            "possible_duplicate_of": possible_duplicates,
            "first_seen_at": now,
            "last_seen_at": now,
        }
        papers.append(record)
        hash_refs.setdefault(sha, []).append({"source": "manifest", "paper_id": paper_id, "path": str(resolved)})
        if identity:
            identity_refs.setdefault(identity, []).append(paper_id)

        if not dry_run and not no_stage:
            if force_stage or not staged_path.exists():
                atomic_copy_file(pdf_path, staged_path)

        status = "new_possible_duplicate" if possible_duplicates else "new"
        rows.append(
            {
                "paper_id": paper_id,
                "status": status,
                "original_filename": pdf_path.name,
                "original_path": str(resolved),
                "sha256": sha,
                "size_bytes": size_bytes,
                "staged_pdf": relative_or_absolute(staged_path),
                "identity_key": identity,
                "possible_duplicate_of": ";".join(possible_duplicates),
                "duplicate_of": "",
            }
        )

    updated = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": now,
        "source_dirs": [str(path.resolve()) for path in source_dirs],
        "staging_dir": relative_or_absolute(staging_dir),
        "papers": papers,
    }
    return updated, rows


def main() -> int:
    args = parse_args()
    source_dirs = [Path(path) for path in args.source_dir] or [default_source_dir()]
    manifest_path = Path(args.manifest)
    staging_dir = Path(args.staging_dir)
    report_path = Path(args.report)

    manifest = load_json_if_exists(manifest_path)
    updated, rows = build_manifest(
        manifest=manifest,
        source_dirs=source_dirs,
        staging_dir=staging_dir,
        start_index=args.start_index,
        limit=args.limit,
        dry_run=args.dry_run,
        no_stage=args.no_stage,
        force_stage=args.force_stage,
    )

    fieldnames = [
        "paper_id",
        "status",
        "original_filename",
        "original_path",
        "sha256",
        "size_bytes",
        "staged_pdf",
        "identity_key",
        "possible_duplicate_of",
        "duplicate_of",
    ]
    if args.dry_run:
        print(f"[dry-run] Manifest: {manifest_path}")
        print(f"[dry-run] Report: {report_path}")
    else:
        write_json(manifest_path, updated)
        atomic_write_csv_dicts(report_path, fieldnames, rows)
        print(f"Manifest: {manifest_path}")
        print(f"Report: {report_path}")

    new_count = sum(1 for row in rows if str(row["status"]).startswith("new"))
    duplicate_count = sum(1 for row in rows if str(row["status"]).startswith("duplicate"))
    possible_duplicate_count = sum(1 for row in rows if row.get("possible_duplicate_of"))
    manifest_possible_duplicate_count = sum(
        1 for paper in updated.get("papers", []) if paper.get("possible_duplicate_of")
    )
    print(
        f"Scanned PDFs: {len(rows)}; new={new_count}; exact_duplicates={duplicate_count}; "
        f"possible_duplicates={possible_duplicate_count}; "
        f"manifest_possible_duplicates={manifest_possible_duplicate_count}"
    )
    for row in rows[:20]:
        print(
            f"{row['status']}: {row['paper_id'] or '-'} {row['original_filename']} "
            f"sha256={str(row['sha256'])[:12]} staged={row['staged_pdf'] or '-'}"
        )
    if len(rows) > 20:
        print(f"... {len(rows) - 20} more rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
