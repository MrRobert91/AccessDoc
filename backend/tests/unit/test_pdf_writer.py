import pytest
from pathlib import Path
import pikepdf

from app.services.writing.pdf_writer import AccessiblePDFWriter
from app.services.analysis.hierarchy_fixer import DocumentStructure

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _minimal_structure() -> DocumentStructure:
    pages = [
        {
            "page_num": 0,
            "language": "es",
            "blocks": [
                {
                    "id": "p0_b0",
                    "role": "H1",
                    "text": "Annual Report 2024",
                    "reading_order_position": 0,
                    "was_changed": True,
                    "confidence": 0.95,
                },
                {
                    "id": "p0_b1",
                    "role": "P",
                    "text": "Introduction paragraph",
                    "reading_order_position": 1,
                    "was_changed": False,
                    "confidence": 0.9,
                },
                {
                    "id": "p0_b2",
                    "role": "Figure",
                    "text": "",
                    "alt_text": "Quarterly revenue chart",
                    "reading_order_position": 2,
                    "was_changed": True,
                    "confidence": 0.88,
                },
                {
                    "id": "p0_b3",
                    "role": "Artifact",
                    "text": "Page 1",
                    "reading_order_position": 3,
                    "was_changed": False,
                },
            ],
        }
    ]
    return DocumentStructure(
        pages=pages,
        document_title="Annual Report 2024",
        language="es",
        headings_hierarchy=[
            {"text": "Annual Report 2024", "level": 1, "page": 0}
        ],
        page_count=1,
    )


class TestAccessiblePDFWriter:
    def test_writes_output_file(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        assert out.exists()
        assert out.stat().st_size > 0

    def test_sets_document_title_metadata(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            with pdf.open_metadata() as meta:
                assert str(meta.get("dc:title", "")) == "Annual Report 2024"

    def test_sets_language_metadata(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            with pdf.open_metadata() as meta:
                assert "es" in str(meta.get("dc:language", ""))

    def test_marks_document_as_tagged(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            assert "/MarkInfo" in pdf.Root
            assert bool(pdf.Root.MarkInfo.Marked) is True

    def test_builds_struct_tree_root(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            assert "/StructTreeRoot" in pdf.Root

    def test_sets_display_doc_title_preference(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            assert "/ViewerPreferences" in pdf.Root
            assert bool(pdf.Root.ViewerPreferences.DisplayDocTitle) is True

    def test_applied_changes_include_title_and_language(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        change_types = {c.change_type for c in writer.get_applied_changes()}
        assert "title_set" in change_types
        assert "language_set" in change_types

    def test_applied_changes_include_alt_text_for_figure(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        change_types = [c.change_type for c in writer.get_applied_changes()]
        assert "alt_text_added" in change_types

    def test_bookmark_added_when_headings_present(self, tmp_path):
        structure = _minimal_structure()
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        change_types = [c.change_type for c in writer.get_applied_changes()]
        assert "bookmark_added" in change_types

    def test_skips_decorative_figures(self, tmp_path):
        structure = _minimal_structure()
        structure.pages[0]["blocks"].append({
            "id": "p0_b4",
            "role": "Figure",
            "text": "",
            "alt_text": "decorative",
            "reading_order_position": 4,
            "was_changed": True,
        })
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), structure)
        out = tmp_path / "accessible.pdf"
        writer.write(str(out))
        # Should not crash; decorative figure gets skipped (no Alt entry)
        assert out.exists()
