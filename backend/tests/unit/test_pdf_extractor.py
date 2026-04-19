import pytest
from pathlib import Path
from app.services.extraction.pdf_extractor import (
    PDFExtractor, _statistical_mode, _detect_header_row
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestStatisticalMode:
    def test_returns_most_frequent_value(self):
        assert _statistical_mode([12.0, 12.0, 14.0, 12.0, 16.0]) == 12.0

    def test_handles_single_value(self):
        assert _statistical_mode([11.5]) == 11.5

    def test_handles_empty_list(self):
        assert _statistical_mode([]) == 12.0

    def test_groups_similar_sizes(self):
        result = _statistical_mode([12.0, 12.2, 12.4, 16.0, 16.0, 16.0])
        assert result in [12.0, 12.5, 16.0]


class TestDetectHeaderRow:
    def test_detects_header_when_first_row_is_shorter(self):
        table = [
            ["Name", "Age"],
            ["Alexander Smith", "28 years old"],
            ["Maria Rodriguez-Martinez", "35 years"],
        ]
        assert _detect_header_row(table) is True

    def test_no_header_when_all_rows_similar_length(self):
        table = [
            ["Alexander", "Maria"],
            ["Roberto", "Lucia"],
            ["Fernando", "Carmen"],
        ]
        assert _detect_header_row(table) is False

    def test_handles_empty_table(self):
        assert _detect_header_row([]) is False

    def test_handles_single_row(self):
        assert _detect_header_row([["only row"]]) is False


class TestPDFExtractor:
    def test_extracts_text_from_simple_pdf(self):
        pdf_path = FIXTURES / "simple.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        assert result.page_count >= 1
        assert not result.is_password_protected
        assert len(result.pages[0].text_blocks) > 0

    def test_renders_page_as_png(self):
        pdf_path = FIXTURES / "simple.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        assert result.pages[0].rendered_image is not None
        assert result.pages[0].rendered_image[:4] == b"\x89PNG"

    def test_identifies_heading_candidates(self):
        pdf_path = FIXTURES / "simple.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        # The title "Annual Report 2024" is 24pt; body is 10pt
        # → at least one heading candidate must exist
        candidates = [
            b for b in result.pages[0].text_blocks if b.is_heading_candidate
        ]
        assert len(candidates) >= 1

    def test_detects_scanned_pdf_needs_ocr(self):
        pdf_path = FIXTURES / "scanned.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        assert result.needs_ocr is True

    def test_extracts_tables_from_complex_tables(self):
        pdf_path = FIXTURES / "complex_tables.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        assert len(result.pages[0].tables) >= 1
        first_table = result.pages[0].tables[0]
        assert first_table.has_header_row is True

    def test_page_data_has_dimensions(self):
        pdf_path = FIXTURES / "simple.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        page = result.pages[0]
        assert page.width > 0
        assert page.height > 0
        assert page.body_font_size > 0

    def test_get_image_crop_returns_png_bytes(self):
        pdf_path = FIXTURES / "simple.pdf"
        extractor = PDFExtractor(str(pdf_path))
        result = extractor.extract_all()
        page = result.pages[0]
        # Crop a small region
        crop = page.get_image_crop((10, 10, 100, 100))
        assert crop[:4] == b"\x89PNG"
