import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _pdf_helpers import make_pdf

from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.importer import import_pdf
from test_ai_stages import _canned  # reuse the canned-builder


def test_import_pdf_returns_paper_id_and_writes_card(tmp_path: Path):
    pdf = make_pdf(tmp_path / "doc.pdf", ["Intro problem.", "Methods and result Z."])
    library = tmp_path / "library"
    docling_dir = tmp_path / "dj"

    def client_factory(paper_dir: Path):
        return SequencedFakeClient(_canned(paper_dir))

    paper_id = import_pdf(
        pdf_path=pdf, library_dir=library, docling_json_dir=docling_dir,
        extractor=PyMuPDFExtractor(), client_factory=client_factory,
        progress=lambda msg: None,
    )

    assert paper_id == "S1"  # fresh tmp_path library → first allocation is S1
    card = json.loads((library / paper_id / "literature_card.json").read_text(encoding="utf-8"))
    assert card["schema_version"] == "0.3.0"
    assert card["paper"]["title"]
