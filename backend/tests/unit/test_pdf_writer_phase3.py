import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from app.services.writing.pdf_writer import AccessiblePDFWriter  # noqa: E402
from app.services.analysis.hierarchy_fixer import DocumentStructure  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _structure_with_figure_bbox() -> DocumentStructure:
    pages = [{
        "page_num": 0,
        "language": "es",
        "blocks": [
            {
                "id": "p0_b0",
                "role": "H1",
                "text": "Portada",
                "reading_order_position": 0,
                "was_changed": True,
                "confidence": 0.95,
            },
            {
                "id": "p0_b1",
                "role": "Figure",
                "text": "",
                "alt_text": "Portada con logotipo AccessDoc",
                "bbox": (50, 50, 300, 200),
                "actual_text": "AccessDoc",
                "reading_order_position": 1,
                "was_changed": True,
                "confidence": 0.88,
            },
        ],
    }]
    return DocumentStructure(
        pages=pages,
        document_title="Portada",
        language="es",
        headings_hierarchy=[{"text": "Portada", "level": 1, "page": 0}],
        page_count=1,
    )


def _structure_with_foreign_block() -> DocumentStructure:
    pages = [{
        "page_num": 0,
        "language": "es",
        "blocks": [
            {
                "id": "p0_b0",
                "role": "H1",
                "text": "Documento",
                "reading_order_position": 0,
                "was_changed": True,
                "confidence": 0.95,
            },
            {
                "id": "p0_b1",
                "role": "P",
                "text": "A quote in English for testing purposes.",
                "language": "en",
                "reading_order_position": 1,
                "was_changed": False,
                "confidence": 0.9,
            },
        ],
    }]
    return DocumentStructure(
        pages=pages,
        document_title="Documento",
        language="es",
        headings_hierarchy=[{"text": "Documento", "level": 1, "page": 0}],
        page_count=1,
    )


class TestPageLabels:
    def test_page_labels_present(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        out = tmp_path / "pl.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            assert "/PageLabels" in pdf.Root
            nums = pdf.Root.PageLabels.Nums
            assert int(nums[0]) == 0
            style = nums[1]
            assert str(style["/S"]) == "/D"
            assert int(style["/St"]) == 1

    def test_page_labels_records_change(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        writer.write(str(tmp_path / "pl.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "page_labels_set" in types


class TestFigureEnhancements:
    def test_figure_has_bbox_and_layout_attributes(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        out = tmp_path / "fig.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            figs = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/Figure"))
        assert figs, "no /Figure struct elem found"
        fig = figs[0]
        a = fig.get("/A")
        assert a is not None
        # /A can be dict or array-of-dicts; normalize to first dict
        attrs = a if isinstance(a, pikepdf.Dictionary) else a[0]
        assert str(attrs["/O"]) == "/Layout"
        assert str(attrs["/Placement"]) == "/Block"
        assert "/BBox" in attrs

    def test_figure_has_actual_text(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        out = tmp_path / "fig.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            figs = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/Figure"))
        assert "/ActualText" in figs[0]
        assert str(figs[0]["/ActualText"]) == "AccessDoc"


class TestPerBlockLang:
    def test_foreign_language_applies_lang(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_foreign_block(),
        )
        out = tmp_path / "lang.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            paras = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/P"))
        assert paras, "no /P struct elem found"
        langs = [str(p.get("/Lang")) for p in paras if p.get("/Lang") is not None]
        assert any("en" in l for l in langs)

    def test_same_language_does_not_apply_lang(self, tmp_path):
        struct = _structure_with_foreign_block()
        struct.pages[0]["blocks"][1]["language"] = "es"
        writer = AccessiblePDFWriter(str(FIXTURES / "simple.pdf"), struct)
        out = tmp_path / "lang_same.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            paras = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/P"))
        for p in paras:
            assert p.get("/Lang") is None


class TestExtendedXMP:
    def test_xmp_has_description_and_creator(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        out = tmp_path / "meta.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            with pdf.open_metadata() as meta:
                assert str(meta.get("dc:description", ""))
                assert "AccessDoc" in str(meta.get("xmp:CreatorTool", ""))
                assert str(meta.get("pdf:Producer", ""))

    def test_records_xmp_change(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"),
            _structure_with_figure_bbox(),
        )
        writer.write(str(tmp_path / "meta.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "xmp_extended" in types


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
