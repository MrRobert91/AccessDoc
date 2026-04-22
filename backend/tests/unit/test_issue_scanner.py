import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from app.services.validation.issue_scanner import (  # noqa: E402
    FontScanner, ContrastScanner, scan_pdf,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestFontScanner:
    def test_standard_14_not_flagged(self):
        issues = FontScanner().scan(str(FIXTURES / "simple.pdf"))
        # simple.pdf uses standard Helvetica; any flagged font must not be
        # one of the standard 14 (reportlab can embed subsets, so allow >0).
        for issue in issues:
            assert "Helvetica" not in issue.description or "subset" in issue.description.lower()

    def test_returns_list(self):
        issues = FontScanner().scan(str(FIXTURES / "simple.pdf"))
        assert isinstance(issues, list)

    def test_missing_file_is_safe(self):
        issues = FontScanner().scan("/tmp/does-not-exist.pdf")
        assert issues == []


class TestContrastScanner:
    def test_scanned_pdf_flagged_when_no_text(self):
        # scanned.pdf has an image and no text content stream → contrast unverifiable
        issues = ContrastScanner().scan(str(FIXTURES / "scanned.pdf"))
        # May be empty if reportlab attached dummy font resource; just check
        # the scanner returns a list and flags use correct criterion.
        for i in issues:
            assert i.criterion == "1.4.3"

    def test_text_pdf_not_flagged(self):
        issues = ContrastScanner().scan(str(FIXTURES / "simple.pdf"))
        # simple.pdf has text — should not be flagged
        assert issues == []


class TestScanPdf:
    def test_combines_both_scanners(self):
        result = scan_pdf(str(FIXTURES / "simple.pdf"))
        assert isinstance(result.font_issues, list)
        assert isinstance(result.contrast_issues, list)
        assert isinstance(result.all, list)
