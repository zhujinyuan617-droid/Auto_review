import unittest
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from paper_downloader import (
    DEFAULT_PDF_URL_TEMPLATE,
    article_page_url,
    build_pdf_url,
    build_target_filename,
    find_existing_pdf,
    parse_ris,
    resolve_project_path,
    target_pdf_path,
)


SAMPLE_RIS = """TY  - JOUR
TI  - Portable path handling in literature workflows
AU  - Smith, Alex
T2  - Example Journal
PY  - 2026
DO  - 10.1016/j.ces.2026.123498
UR  - https://www.sciencedirect.com/science/article/pii/S0009250926002101
ER  -
"""


class PaperDownloaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.ris_path = Path(cls.temp_dir.name) / "sample.ris"
        cls.ris_path.write_text(SAMPLE_RIS, encoding="utf-8")
        cls.articles = parse_ris(cls.ris_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_parse_ris_count_and_first_record(self):
        self.assertEqual(len(self.articles), 1)
        first = self.articles[0]
        self.assertEqual(first.doi, "10.1016/j.ces.2026.123498")
        self.assertEqual(first.pii, "S0009250926002101")

    def test_build_sciencedirect_pdf_url(self):
        first = self.articles[0]
        self.assertEqual(
            article_page_url(first),
            "https://www.sciencedirect.com/science/article/pii/S0009250926002101",
        )
        self.assertEqual(
            build_pdf_url(first, DEFAULT_PDF_URL_TEMPLATE),
            "https://www.sciencedirect.com/science/article/pii/"
            "S0009250926002101/pdfft?isDTMRedir=true&download=true",
        )

    def test_target_filename_is_pdf_and_windows_safe(self):
        filename = build_target_filename(
            self.articles[0],
            "{year}_{first_author}_{short_title}_{doi_suffix}.pdf",
        )
        self.assertTrue(filename.endswith(".pdf"))
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, filename)

    def test_find_existing_pdf_uses_target_filename(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            article = self.articles[0]
            template = "{year}_{first_author}_{short_title}_{doi_suffix}.pdf"
            self.assertIsNone(find_existing_pdf(download_dir, article, template))
            expected = target_pdf_path(download_dir, article, template)
            expected.write_bytes(b"%PDF-1.4\n")
            self.assertEqual(find_existing_pdf(download_dir, article, template), expected)

    def test_resolve_project_path_uses_project_root_for_relative_values(self):
        self.assertEqual(resolve_project_path("paper"), ROOT / "paper")


if __name__ == "__main__":
    unittest.main()
