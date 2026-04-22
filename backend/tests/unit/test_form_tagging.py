import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from app.services.writing.pdf_writer import AccessiblePDFWriter  # noqa: E402
from app.services.analysis.hierarchy_fixer import DocumentStructure  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _empty_structure() -> DocumentStructure:
    return DocumentStructure(
        pages=[{"page_num": 0, "language": "es", "blocks": []}],
        document_title="Formulario",
        language="es",
        headings_hierarchy=[],
        page_count=1,
    )


def _find_elems_by_type(elem, type_name, acc=None):
    if acc is None:
        acc = []
    s = elem.get("/S")
    if s is not None and str(s) == type_name:
        acc.append(elem)
    k = elem.get("/K")
    if k is None:
        return acc
    try:
        iter(k)
    except TypeError:
        return acc
    for child in k:
        if isinstance(child, pikepdf.Dictionary):
            _find_elems_by_type(child, type_name, acc)
    return acc


class TestFormFieldsTagger:
    def test_form_struct_elems_created(self, tmp_path):
        writer = AccessiblePDFWriter(str(FIXTURES / "form.pdf"), _empty_structure())
        out = tmp_path / "form_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            form_elems = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/Form"))
        assert len(form_elems) >= 2, "expected one /Form elem per widget"

    def test_widget_has_tu_and_struct_parent(self, tmp_path):
        writer = AccessiblePDFWriter(str(FIXTURES / "form.pdf"), _empty_structure())
        out = tmp_path / "form_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            widgets = []
            for page in pdf.pages:
                for annot in (page.get("/Annots") or []):
                    if isinstance(annot, pikepdf.Dictionary) and str(annot.get("/Subtype", "")) == "/Widget":
                        widgets.append(annot)
            assert widgets, "fixture should have widgets"
            for w in widgets:
                assert "/TU" in w, "widget missing /TU (accessible name)"
                assert str(w["/TU"]).strip(), "/TU should be non-empty"
                assert "/StructParent" in w

    def test_page_tabs_is_structure_order(self, tmp_path):
        writer = AccessiblePDFWriter(str(FIXTURES / "form.pdf"), _empty_structure())
        out = tmp_path / "form_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            page = pdf.pages[0]
            assert str(page.get("/Tabs", "")) == "/S", "/Tabs must be /S for UA tab order"

    def test_records_form_field_change(self, tmp_path):
        writer = AccessiblePDFWriter(str(FIXTURES / "form.pdf"), _empty_structure())
        writer.write(str(tmp_path / "form_tagged.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "form_field_tagged" in types
