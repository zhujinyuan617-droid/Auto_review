import hashlib
from pathlib import Path

from _fake_transport import FakeTransport

from autoreview_app.discovery.records import CitationRecord
from autoreview_app.discovery.download import download_records


class _OASource:
    name = "oa"
    can_search = False
    can_fetch = True

    def search(self, query, transport, rows=20):
        return []

    def fetch(self, record, transport):
        if record.pdf_url:
            return transport.get_bytes(record.pdf_url)
        return None


def test_downloads_pdf_and_reports(tmp_path: Path):
    rec = CitationRecord(title="P1", doi="10.1/a", pdf_url="http://x/a.pdf")
    transport = FakeTransport(byte_responses={"http://x/a.pdf": b"%PDF-1.4 AAA"})

    results = download_records(
        [rec], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path,
    )

    assert len(results) == 1
    r = results[0]
    assert r["status"] == "downloaded"
    saved = Path(r["path"])
    assert saved.exists()
    assert saved.read_bytes() == b"%PDF-1.4 AAA"
    assert r["sha256"] == hashlib.sha256(b"%PDF-1.4 AAA").hexdigest()


def test_duplicate_bytes_are_skipped(tmp_path: Path):
    a = CitationRecord(title="A", doi="10.1/a", pdf_url="http://x/a.pdf")
    b = CitationRecord(title="B", doi="10.1/b", pdf_url="http://x/b.pdf")
    transport = FakeTransport(byte_responses={
        "http://x/a.pdf": b"%PDF same", "http://x/b.pdf": b"%PDF same",
    })

    results = download_records([a, b], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path)

    statuses = [r["status"] for r in results]
    assert statuses == ["downloaded", "duplicate"]
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_no_full_text_when_no_fetcher_succeeds(tmp_path: Path):
    rec = CitationRecord(title="NoPdf", doi="10.1/c")  # no pdf_url
    transport = FakeTransport()
    results = download_records([rec], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path)
    assert results[0]["status"] == "no_full_text"


def test_same_stem_different_bytes_do_not_overwrite(tmp_path: Path):
    # Both DOIs sanitize to the same stem ("10_1_a") but the PDFs differ.
    a = CitationRecord(title="A", doi="10.1/a", pdf_url="http://x/a.pdf")
    b = CitationRecord(title="B", doi="10.1/a.", pdf_url="http://x/b.pdf")
    transport = FakeTransport(byte_responses={
        "http://x/a.pdf": b"%PDF AAA", "http://x/b.pdf": b"%PDF BBB",
    })

    results = download_records([a, b], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path)

    assert [r["status"] for r in results] == ["downloaded", "downloaded"]
    # Two distinct files, neither overwritten.
    paths = [Path(r["path"]) for r in results]
    assert paths[0] != paths[1]
    assert len(list(tmp_path.glob("*.pdf"))) == 2
    # Each reported sha256 still matches the bytes actually on disk.
    for r in results:
        assert hashlib.sha256(Path(r["path"]).read_bytes()).hexdigest() == r["sha256"]
