from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_csv_rows, atomic_write_text, write_json


SCHEMA_VERSION = "0.1.0"
TEXT_LABELS = {"text", "section_header", "list_item", "caption", "formula", "footnote"}
DROP_LABELS = {"page_header", "page_footer"}
KNOWN_JOURNAL_NAMES = [
    "AIChE Journal",
    "Carbon",
    "Chemical Engineering Journal",
    "Chemical Engineering Science",
    "Energy",
    "Fluid Phase Equilibria",
    "Fuel",
    "Journal of Molecular Liquids",
    "Journal of Petroleum Science and Engineering",
    "Microporous and Mesoporous Materials",
    "SPE Reservoir Evaluation & Engineering",
]
ELSEVIER_LOCATE_JOURNALS = {
    "ces": "Chemical Engineering Science",
    "fluid": "Fluid Phase Equilibria",
    "fuel": "Fuel",
    "micromeso": "Microporous and Mesoporous Materials",
    "petrol": "Journal of Petroleum Science and Engineering",
}


@dataclass
class BuildResult:
    paper_id: str
    output_dir: Path
    content_blocks: int
    evidence_items: int
    figures: int
    tables: int
    text_blocks: int
    source_pdf_status: str
    source_pdf_path: str | None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def collapse_spaced_letters(value: str) -> str:
    """Collapse Docling/OCR text like 'j o u r n a l' into 'journal'."""
    tokens = normalize_space(value).split()
    collapsed: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if len(token) == 1 and token.isalpha():
            letters = [token]
            index += 1
            while index < len(tokens) and len(tokens[index]) == 1 and tokens[index].isalpha():
                letters.append(tokens[index])
                index += 1
            if len(letters) >= 3:
                collapsed.append("".join(letters))
            else:
                collapsed.extend(letters)
            continue
        collapsed.append(token)
        index += 1
    return " ".join(collapsed)


def slugify(value: str, max_len: int = 80) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return (value[:max_len].strip("_") or "paper")


def sample_id_from_stem(stem: str) -> str:
    match = re.match(r"^(S\d+)_", stem)
    if match:
        return match.group(1)
    return slugify(stem, 24)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filename_doi_key(value: str) -> str:
    lowered = value.lower()
    match = re.search(r"\bj[._-]([a-z0-9]+)[._-](\d{4})[._-]([a-z0-9]+)", lowered)
    if match:
        return "".join(match.groups())
    return ""


def clean_title_spacing(value: str) -> str:
    title = normalize_space(value)
    replacements = {
        "fl ow": "flow",
        "fl uid": "fluid",
        "microfl uidic": "microfluidic",
        "uidic": "uidic",
    }
    for old, new in replacements.items():
        title = re.sub(rf"\b{re.escape(old)}\b", new, title, flags=re.I)
    return normalize_space(title)


def doi_from_text_or_name(*values: str) -> str:
    blob = " ".join(str(value or "") for value in values)
    explicit = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", blob)
    if explicit:
        return explicit.group(0).rstrip(".")

    lowered = blob.lower()
    elsevier = re.search(
        r"(?:^|[^a-z0-9])j[._-]([a-z0-9]+)[._-]((?:19|20)\d{2})[._-]([a-z0-9]+(?:[._-][a-z0-9]+)*)",
        lowered,
    )
    if elsevier:
        journal, year, article = elsevier.groups()
        article = re.sub(r"[._-]+", ".", article).rstrip(".")
        return f"10.1016/j.{journal}.{year}.{article}".rstrip(".")

    rsc = re.search(r"(?:^|[^A-Z0-9])([A-Z]\d[A-Z]{2}\d{5}[A-Z]?)(?:$|[^A-Z0-9])", blob, flags=re.I)
    if rsc:
        return f"10.1039/{rsc.group(1).upper()}"

    wiley_prefixes = {
        "aic": "10.1002/aic",
        "advs": "10.1002/advs",
    }
    for token, prefix in wiley_prefixes.items():
        match = re.search(rf"(?:^|[^a-z0-9]){token}[._-]([0-9]{{4,}})(?:$|[^0-9])", lowered)
        if match:
            return f"{prefix}.{match.group(1)}"

    spe_suffix = re.search(r"(?:^|[^0-9])(\d{5,6})[-_](PA|MS|SPE)(?:$|[^A-Z0-9])", blob, flags=re.I)
    if spe_suffix:
        paper_no, suffix = spe_suffix.groups()
        return f"10.2118/{paper_no}-{suffix.upper()}"

    return ""


def title_from_paper_line(text_blob: str) -> str:
    match = re.search(
        r"\bPAPER\s+(.+?)(?:\n|\bISSN\b|\b\d{4}-\d{4}\b|$)",
        text_blob,
        flags=re.I | re.S,
    )
    if not match:
        return ""
    title = normalize_space(match.group(1))
    title = re.sub(r"^[A-Z][A-Za-z-]+ et al\s*\.?\s*", "", title, flags=re.I)
    title = re.sub(r"\bPAPER\b", "", title, flags=re.I)
    return clean_title_spacing(title)


def title_from_docling_name(value: str) -> str:
    stem = Path(str(value or "")).stem
    if not stem:
        return ""
    parts = [part for part in re.split(r"_+", stem) if part]
    if parts and re.fullmatch(r"S\d+", parts[0], flags=re.I):
        parts = parts[1:]
    if parts and re.fullmatch(r"(?:19|20)\d{2}|unknown-year", parts[0], flags=re.I):
        parts = parts[1:]
    if parts and re.fullmatch(r"[A-Z][A-Za-z-]{1,30}|unknown", parts[0]):
        parts = parts[1:]

    while parts:
        tail = parts[-1]
        lowered = tail.lower()
        if (
            re.fullmatch(r"j\.[a-z0-9]+\.(?:19|20)\d{2}\.[a-z0-9]+(?:\.[a-z0-9]+)*", lowered)
            or re.fullmatch(r"[a-z]\d[a-z]{2}\d{5}[a-z]?", lowered)
            or re.fullmatch(r"(?:aic|advs)(?:\.\d{4,})?", lowered)
            or lowered.startswith("zot-")
        ):
            parts.pop()
            continue
        break
    title = " ".join(parts).replace("  ", " ").strip(" ._-")
    return clean_title_spacing(title)


def bad_title_candidate(value: str) -> bool:
    title = clean_title_spacing(value)
    lowered = normalize_title(title).replace("_", " ")
    if not title:
        return True
    if len(title) > 220:
        return True
    if title.count(".") >= 2:
        return True
    bad_exact = {
        "miniaturisation for chemistry physics biology materials science and bioengineering",
        "contents lists available at sciencedirect",
        "full length article",
        "article info",
        "abstract",
    }
    if lowered in bad_exact:
        return True
    if is_known_journal_name(title):
        return True
    if lowered.startswith(("journal homepage", "www ", "issn ", "volume ")):
        return True
    return False


def is_known_journal_name(value: str) -> bool:
    normalized = normalize_space(value).lower()
    return normalized in {journal.lower() for journal in KNOWN_JOURNAL_NAMES}


def year_from_text_or_name(docling_name: str, origin_filename: str, header_blob: str, text_blob: str) -> str:
    for value in [docling_name, origin_filename]:
        match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", value)
        if match:
            return match.group(1)

    for value in [header_blob, text_blob]:
        for pattern in [
            r"(?:copyright|©|&|Ó|V C)\s*(?:\D{0,20})\b((?:19|20)\d{2})\b",
            r"\bAvailable online\b.*?\b((?:19|20)\d{2})\b",
            r"\bPublished\b.*?\b((?:19|20)\d{2})\b",
        ]:
            match = re.search(pattern, value, flags=re.I | re.S)
            if match:
                return match.group(1)

    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", header_blob)
    if match:
        return match.group(1)
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text_blob)
    return match.group(1) if match else ""


def content_tokens(value: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "study",
        "review",
        "experimental",
        "molecular",
        "simulation",
        "simulations",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", value)
        if token.lower() not in stopwords
    }


def pdf_candidates(pdf_dirs: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pdf_dir in pdf_dirs:
        if not pdf_dir.exists():
            continue
        paths = [pdf_dir] if pdf_dir.is_file() and pdf_dir.suffix.lower() == ".pdf" else pdf_dir.rglob("*.pdf")
        for path in paths:
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(path)
    return candidates


def find_source_pdf(
    origin_filename: str,
    json_stem: str,
    pdf_dirs: list[Path],
) -> tuple[Path, str] | None:
    if not pdf_dirs:
        return None

    all_candidates = pdf_candidates(pdf_dirs)
    for path in all_candidates:
        if path.name == origin_filename:
            return path, "origin_filename"

    doi_keys = {key for key in [filename_doi_key(origin_filename), filename_doi_key(json_stem)] if key}
    if doi_keys:
        doi_matches = [path for path in all_candidates if filename_doi_key(path.name) in doi_keys]
        if len(doi_matches) == 1:
            return doi_matches[0], "doi_key"

    origin_tokens = content_tokens(origin_filename)
    scored: list[tuple[float, Path]] = []
    for path in all_candidates:
        candidate_tokens = content_tokens(path.name)
        if not origin_tokens or not candidate_tokens:
            continue
        score = len(origin_tokens & candidate_tokens) / max(1, len(origin_tokens))
        if score >= 0.6:
            scored.append((score, path))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and (len(scored) == 1 or scored[0][0] > scored[1][0] + 0.15):
        return scored[0][1], "title_tokens"
    return None


def copy_source_pdf(
    output_dir: Path,
    paper_id: str,
    data: dict[str, Any],
    json_path: Path,
    pdf_dirs: list[Path],
) -> tuple[str, str | None]:
    origin = data.get("origin") or {}
    origin_filename = str(origin.get("filename") or f"{json_path.stem}.pdf")
    if not pdf_dirs:
        return "not_requested", None

    match = find_source_pdf(origin_filename, json_path.stem, pdf_dirs)
    metadata_path = output_dir / "source_pdf.json"
    if not match:
        write_json(
            metadata_path,
            {
                "schema_version": SCHEMA_VERSION,
                "paper_id": paper_id,
                "status": "missing",
                "docling_origin_filename": origin_filename,
                "docling_binary_hash": origin.get("binary_hash"),
                "searched_pdf_dirs": [str(path.resolve()) for path in pdf_dirs],
                "source_pdf": None,
            },
        )
        return "missing", None

    source_path, match_method = match
    target_path = output_dir / "source.pdf"
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "status": "copied",
        "source": "pdf_dir",
        "match_method": match_method,
        "docling_origin_filename": origin_filename,
        "docling_binary_hash": origin.get("binary_hash"),
        "original_filename": source_path.name,
        "original_path": str(source_path.resolve()),
        "copied_path": "source.pdf",
        "size_bytes": target_path.stat().st_size,
        "sha256": sha256_file(target_path),
        "copied_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(metadata_path, metadata)
    return "copied", "source.pdf"


def normalize_title(title: str) -> str:
    title = re.sub(r"^\d+(\.\d+)*\.?\s*", "", title.strip())
    title = re.sub(r"[^A-Za-z0-9]+", "_", title.lower())
    return re.sub(r"_+", "_", title).strip("_") or "section"


def section_kind(title: str, label: str) -> str:
    normalized = normalize_title(title)
    if normalized in {"abstract", "a_b_s_t_r_a_c_t"}:
        return "abstract"
    if "keyword" in normalized:
        return "keywords"
    if "introduction" in normalized:
        return "introduction"
    if any(token in normalized for token in ("method", "experiment", "simulation", "computational")):
        return "methods"
    if any(token in normalized for token in ("result", "discussion", "analysis")):
        return "results_discussion"
    if any(token in normalized for token in ("conclusion", "summary")):
        return "conclusion"
    if "reference" in normalized:
        return "references"
    if label == "front_matter":
        return "front_matter"
    return "body"


def content_type_for_label(label: str) -> str:
    if label == "section_header":
        return "heading_candidate"
    if label == "caption":
        return "caption"
    if label == "formula":
        return "formula"
    if label == "list_item":
        return "list_item"
    if label == "footnote":
        return "footnote"
    return "text"


def is_numbered_section(title: str) -> bool:
    return bool(re.match(r"^\d+(?:\.\d+)*\.?\s+\S", title.strip()))


def is_real_section_header(title: str) -> bool:
    normalized = normalize_title(title)
    if is_numbered_section(title):
        return True
    return normalized in {
        "abstract",
        "a_b_s_t_r_a_c_t",
        "keywords",
        "references",
        "acknowledgements",
        "acknowledgments",
        "conclusion",
        "conclusions",
        "summary",
    }


def is_front_matter_heading(title: str) -> bool:
    normalized = normalize_title(title)
    lowered = title.strip().lower()
    return (
        normalized in {"article_info", "a_r_t_i_c_l_e_i_n_f_o"}
        or lowered.startswith(("http://", "https://", "doi"))
        or "journal homepage" in lowered
    )


def is_text_noise(text: str, label: str, page: int | None) -> bool:
    value = re.sub(r"\s+", " ", text).strip()
    lowered = value.lower()
    if not value:
        return True
    if label in DROP_LABELS:
        return True
    if re.fullmatch(r"\d+", value):
        return True
    if lowered in {"contents lists available at sciencedirect"}:
        return True
    if "journal homepage:" in lowered:
        return True
    if lowered in {"available online", "article info", "a r t i c l e i n f o"}:
        return True
    if page == 1 and re.fullmatch(r"\d{1,2}", value):
        return True
    return False


def level_from_title(title: str) -> int:
    match = re.match(r"^(\d+(?:\.\d+)*)", title.strip())
    if not match:
        return 1
    return len(match.group(1).split("."))


def first_prov(item: dict[str, Any]) -> dict[str, Any]:
    prov = item.get("prov") or []
    if prov and isinstance(prov[0], dict):
        return prov[0]
    return {}


def page_no(item: dict[str, Any]) -> int | None:
    page = first_prov(item).get("page_no")
    return page if isinstance(page, int) else None


def bbox(item: dict[str, Any]) -> dict[str, Any] | None:
    value = first_prov(item).get("bbox")
    return value if isinstance(value, dict) else None


def resolve_ref(data: dict[str, Any], ref: str) -> tuple[str, int, dict[str, Any]] | None:
    match = re.match(r"^#/(texts|pictures|tables|groups)/(\d+)$", ref)
    if not match:
        return None
    kind = match.group(1)
    index = int(match.group(2))
    collection = data.get(kind) or []
    if index < 0 or index >= len(collection):
        return None
    return kind, index, collection[index]


def iter_body_refs(data: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    seen_items: set[str] = set()
    seen_groups: set[str] = set()

    def visit(ref: str) -> None:
        resolved = resolve_ref(data, ref)
        if not resolved:
            return
        kind, _, item = resolved
        if kind == "groups":
            if ref in seen_groups:
                return
            seen_groups.add(ref)
            for child in item.get("children") or []:
                child_ref = child.get("$ref")
                if child_ref:
                    visit(child_ref)
            return
        if ref in seen_items:
            return
        seen_items.add(ref)
        refs.append(ref)

    for child in data.get("body", {}).get("children") or []:
        ref = child.get("$ref")
        if ref:
            visit(ref)
    return refs


def ref_index(ref: str) -> int:
    match = re.search(r"/(\d+)$", ref or "")
    return int(match.group(1)) if match else -1


def ref_to_evidence_id(paper_id: str, ref: str, prefix_map: dict[str, str]) -> str:
    kind = ref.split("/")[1] if ref.startswith("#/") else "items"
    prefix = prefix_map.get(kind, "EV")
    return f"{paper_id}-{prefix}-{ref_index(ref) + 1:04d}"


def caption_text(data: dict[str, Any], refs: list[dict[str, str]]) -> tuple[str, str | None]:
    parts: list[str] = []
    first_id: str | None = None
    for ref_obj in refs or []:
        ref = ref_obj.get("$ref")
        if not ref:
            continue
        resolved = resolve_ref(data, ref)
        if not resolved or resolved[0] != "texts":
            continue
        text = (resolved[2].get("text") or resolved[2].get("orig") or "").strip()
        if text:
            parts.append(text)
            first_id = first_id or ref
    return " ".join(parts), first_id


def unique_cell_texts(grid_row: list[dict[str, Any]]) -> list[str]:
    cells: list[str] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for cell in grid_row:
        key = (
            int(cell.get("start_row_offset_idx", 0)),
            int(cell.get("end_row_offset_idx", 0)),
            int(cell.get("start_col_offset_idx", 0)),
            int(cell.get("end_col_offset_idx", 0)),
            cell.get("text") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        cells.append(str(cell.get("text") or ""))
    return cells


def table_matrix(table: dict[str, Any]) -> list[list[str]]:
    data = table.get("data") or {}
    rows = int(data.get("num_rows") or 0)
    cols = int(data.get("num_cols") or 0)
    matrix = [["" for _ in range(cols)] for _ in range(rows)]
    for cell in data.get("table_cells") or []:
        text = str(cell.get("text") or "")
        r0 = int(cell.get("start_row_offset_idx") or 0)
        r1 = int(cell.get("end_row_offset_idx") or r0 + 1)
        c0 = int(cell.get("start_col_offset_idx") or 0)
        c1 = int(cell.get("end_col_offset_idx") or c0 + 1)
        for row in range(max(0, r0), min(rows, r1)):
            for col in range(max(0, c0), min(cols, c1)):
                matrix[row][col] = text
    return matrix


def markdown_table(matrix: list[list[str]]) -> str:
    if not matrix:
        return ""
    width = max(len(row) for row in matrix)
    rows = [row + [""] * (width - len(row)) for row in matrix]

    def esc(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    lines = ["| " + " | ".join(esc(v) for v in rows[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(esc(v) for v in row) + " |")
    return "\n".join(lines)


def write_table_files(table_dir: Path, table_id: str, matrix: list[list[str]]) -> tuple[str, str]:
    csv_path = table_dir / f"{table_id}.csv"
    md_path = table_dir / f"{table_id}.md"
    atomic_write_csv_rows(csv_path, matrix)
    atomic_write_text(md_path, markdown_table(matrix) + "\n", encoding="utf-8")
    return f"tables/{csv_path.name}", f"tables/{md_path.name}"


def export_image(picture: dict[str, Any], figure_dir: Path, figure_id: str) -> str | None:
    image = picture.get("image") or {}
    uri = image.get("uri") or ""
    mimetype = image.get("mimetype") or "image/png"
    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }.get(mimetype, ".img")
    out_path = figure_dir / f"{figure_id}{ext}"
    if uri.startswith("data:"):
        _, payload = uri.split(",", 1)
        out_path.write_bytes(base64.b64decode(payload))
        return f"figures/{out_path.name}"
    if uri:
        src = Path(uri)
        if src.exists():
            shutil.copy2(src, out_path)
            return f"figures/{out_path.name}"
    return None


def metadata_candidates(data: dict[str, Any], paper_id: str) -> dict[str, Any]:
    first_page_all_texts = [
        t
        for t in data.get("texts", [])
        if page_no(t) == 1
    ]
    first_page_texts = [
        t
        for t in first_page_all_texts
        if page_no(t) == 1 and t.get("label") not in DROP_LABELS
    ]
    text_blob = "\n".join((t.get("text") or t.get("orig") or "") for t in first_page_texts)
    docling_name = str(data.get("name") or paper_id)
    origin_filename = str((data.get("origin") or {}).get("filename") or "")
    doi = doi_from_text_or_name(text_blob, docling_name, origin_filename)
    header_blob = "\n".join(
        (t.get("text") or t.get("orig") or "")
        for t in first_page_all_texts
        if t.get("label") == "page_header"
    )
    furniture_blob = "\n".join((t.get("text") or t.get("orig") or "") for t in first_page_all_texts)
    year = year_from_text_or_name(docling_name, origin_filename, header_blob, text_blob)
    front_values = [(t.get("text") or t.get("orig") or "").strip() for t in first_page_texts]

    def clean_front_value(value: str) -> str:
        return normalize_title(collapse_spaced_letters(value)).replace("_", " ")

    def looks_like_article_title(value: str) -> bool:
        lowered = clean_front_value(value).lower()
        if len(value) < 25:
            return False
        if lowered in {
            "full length article",
            "article info",
            "abstract",
            "a b s t r a c t",
            "contents lists available at sciencedirect",
        }:
            return False
        if lowered in {"articleinfo", "article information"}:
            return False
        if is_known_journal_name(value):
            return False
        if lowered.startswith(("journal homepage", "keywords", "contents lists")):
            return False
        if "elsevier com locate" in lowered or "www elsevier" in lowered:
            return False
        if re.match(r"^\d+(\.\d+)*\.?\s+", value):
            return False
        if "@" in value or "department of " in lowered or "university" in lowered:
            return False
        if re.search(r"\b(journal|fuel|energy|elsevier|science direct)\b", lowered) and len(value.split()) <= 7:
            return False
        return True

    title = ""
    for value in front_values:
        if looks_like_article_title(value):
            title = clean_title_spacing(value)
            break
    if bad_title_candidate(title):
        title = title_from_paper_line(text_blob)
    if bad_title_candidate(title):
        title = title_from_docling_name(docling_name)
    if bad_title_candidate(title):
        title = ""

    journal = ""
    for value in front_values[:25]:
        normalized = normalize_space(value)
        for candidate in KNOWN_JOURNAL_NAMES:
            if normalized.lower() == candidate.lower():
                journal = candidate
                break
        if journal:
            break
    if not journal:
        home_match = re.search(r"journal homepage:\s*(?:www\.)?elsevier\.com/locate/([A-Za-z0-9_-]+)", text_blob, re.I)
        if home_match:
            journal_key = home_match.group(1).lower()
            journal = ELSEVIER_LOCATE_JOURNALS.get(journal_key, journal_key)
    if not journal:
        furniture_lines = [
            normalize_space(collapse_spaced_letters(line))
            for line in furniture_blob.splitlines()
            if normalize_space(line)
        ]
        for candidate in KNOWN_JOURNAL_NAMES:
            if any(
                candidate.lower() == line.lower()
                or (len(candidate.split()) >= 3 and re.search(rf"\b{re.escape(candidate)}\b", line, re.I))
                for line in furniture_lines
            ):
                journal = candidate
                break

    return {
        "title": title,
        "doi": doi,
        "year": year,
        "journal": journal,
        "docling_name": docling_name,
        "first_page_text": text_blob[:5000],
    }


def build_clean_package(
    json_path: Path,
    md_path: Path | None,
    output_root: Path,
    pdf_dirs: list[Path] | None = None,
) -> BuildResult:
    data = load_json(json_path)
    paper_id = sample_id_from_stem(json_path.stem)
    output_dir = output_root / paper_id
    figure_dir = output_dir / "figures"
    table_dir = output_dir / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)
    source_pdf_status, source_pdf_path = copy_source_pdf(output_dir, paper_id, data, json_path, pdf_dirs or [])

    prefix_map = {"texts": "TXT", "pictures": "FIG", "tables": "TAB"}
    text_evidence: dict[str, dict[str, Any]] = {}
    figure_evidence: dict[str, dict[str, Any]] = {}
    table_evidence: dict[str, dict[str, Any]] = {}
    content_blocks: list[dict[str, Any]] = []
    block_counter = 0
    text_order = 0

    for ref in iter_body_refs(data):
        resolved = resolve_ref(data, ref)
        if not resolved:
            continue
        kind, _, item = resolved
        if kind == "texts":
            label = item.get("label") or "text"
            if label in DROP_LABELS or item.get("content_layer") == "furniture":
                continue
            if label not in TEXT_LABELS:
                continue
            text = (item.get("text") or item.get("orig") or "").strip()
            page = page_no(item)
            if is_text_noise(text, label, page):
                continue

            text_order += 1
            block_counter += 1
            evidence_id = ref_to_evidence_id(paper_id, ref, prefix_map)
            block_id = f"{paper_id}-BLK-{block_counter:04d}"
            content_blocks.append(
                {
                    "block_id": block_id,
                    "evidence_id": evidence_id,
                    "type": content_type_for_label(label),
                    "docling_label": label,
                    "page_no": page,
                    "text": text,
                }
            )
            text_evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "type": "text_block",
                "docling_ref": ref,
                "block_id": block_id,
                "order": text_order,
                "label": label,
                "content_layer": item.get("content_layer"),
                "page_no": page,
                "bbox": bbox(item),
                "text": text,
            }
        elif kind == "pictures":
            block_counter += 1
            evidence_id = ref_to_evidence_id(paper_id, ref, prefix_map)
            block_id = f"{paper_id}-BLK-{block_counter:04d}"
            image_path = export_image(item, figure_dir, evidence_id)
            caption, caption_ref = caption_text(data, item.get("captions") or [])
            page = page_no(item)
            content_blocks.append(
                {
                    "block_id": block_id,
                    "evidence_id": evidence_id,
                    "type": "figure",
                    "page_no": page,
                    "caption": caption,
                    "image_path": image_path,
                }
            )
            size = (item.get("image") or {}).get("size") or {}
            figure_evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "type": "figure",
                "docling_ref": ref,
                "block_id": block_id,
                "page_no": page,
                "bbox": bbox(item),
                "image_path": image_path,
                "caption": caption,
                "caption_evidence_id": ref_to_evidence_id(paper_id, caption_ref, prefix_map) if caption_ref else None,
                "size": size,
            }
        elif kind == "tables":
            block_counter += 1
            evidence_id = ref_to_evidence_id(paper_id, ref, prefix_map)
            block_id = f"{paper_id}-BLK-{block_counter:04d}"
            matrix = table_matrix(item)
            csv_path, md_table_path = write_table_files(table_dir, evidence_id, matrix)
            caption, caption_ref = caption_text(data, item.get("captions") or [])
            page = page_no(item)
            content_blocks.append(
                {
                    "block_id": block_id,
                    "evidence_id": evidence_id,
                    "type": "table",
                    "page_no": page,
                    "caption": caption,
                    "markdown_path": md_table_path,
                    "csv_path": csv_path,
                }
            )
            table_evidence[evidence_id] = {
                "evidence_id": evidence_id,
                "type": "table",
                "docling_ref": ref,
                "block_id": block_id,
                "page_no": page,
                "bbox": bbox(item),
                "caption": caption,
                "caption_evidence_id": ref_to_evidence_id(paper_id, caption_ref, prefix_map) if caption_ref else None,
                "csv_path": csv_path,
                "markdown_path": md_table_path,
                "num_rows": len(matrix),
                "num_cols": max((len(row) for row in matrix), default=0),
            }

    evidence_items = list(text_evidence.values()) + list(figure_evidence.values()) + list(table_evidence.values())
    evidence_items.sort(key=lambda item: (item.get("page_no") or 9999, item.get("order") or 9999, item["evidence_id"]))

    clean_lines: list[str] = []
    for block in content_blocks:
        if block["type"] == "heading_candidate":
            clean_lines.append(f"[Heading candidate: {block['evidence_id']}] {block['text']}")
        elif block["type"] in {"text", "list_item", "caption", "formula", "footnote"}:
            clean_lines.append(block.get("text", ""))
        elif block["type"] == "figure":
            clean_lines.append(f"[Figure: {block['evidence_id']}] {block.get('caption') or ''}".strip())
        elif block["type"] == "table":
            clean_lines.append(f"[Table: {block['evidence_id']}] {block.get('caption') or ''}".strip())
        clean_lines.append("")

    source = {
        "docling_json": str(json_path.resolve()),
        "docling_md": str(md_path.resolve()) if md_path else None,
        "source_pdf": source_pdf_path,
    }
    content_doc = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source": source,
        "blocks": content_blocks,
    }
    evidence_doc = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "items": evidence_items,
    }
    metadata_doc = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "metadata_candidates": metadata_candidates(data, paper_id),
    }

    write_json(output_dir / "content_blocks.json", content_doc)
    write_json(output_dir / "evidence.json", evidence_doc)
    write_json(output_dir / "metadata_candidates.json", metadata_doc)
    atomic_write_text(output_dir / "content.md", "\n".join(clean_lines).strip() + "\n", encoding="utf-8")

    return BuildResult(
        paper_id=paper_id,
        output_dir=output_dir,
        content_blocks=len(content_blocks),
        evidence_items=len(evidence_items),
        figures=len(figure_evidence),
        tables=len(table_evidence),
        text_blocks=len(text_evidence),
        source_pdf_status=source_pdf_status,
        source_pdf_path=source_pdf_path,
    )
