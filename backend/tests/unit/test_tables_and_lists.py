import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from app.services.writing.pdf_writer import AccessiblePDFWriter  # noqa: E402
from app.services.analysis.hierarchy_fixer import DocumentStructure  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _structure_with_table() -> DocumentStructure:
    pages = [{
        "page_num": 0,
        "language": "es",
        "blocks": [
            {
                "id": "p0_b0",
                "role": "H1",
                "text": "Informe",
                "reading_order_position": 0,
                "was_changed": True,
                "confidence": 0.95,
            },
            {
                "id": "p0_b1",
                "role": "Table",
                "text": "",
                "reading_order_position": 1,
                "was_changed": True,
                "confidence": 0.9,
            },
        ],
        "extracted_tables": [{
            "rows": [
                ["Mes", "Ingresos", "Gastos"],
                ["Enero",   "100",    "40"],
                ["Febrero", "120",    "55"],
            ],
            "bbox": [0, 0, 100, 100],
            "has_header_row": True,
        }],
    }]
    return DocumentStructure(
        pages=pages,
        document_title="Informe",
        language="es",
        headings_hierarchy=[{"text": "Informe", "level": 1, "page": 0}],
        page_count=1,
    )


def _structure_with_list() -> DocumentStructure:
    pages = [{
        "page_num": 0,
        "language": "es",
        "blocks": [
            {
                "id": "p0_b0",
                "role": "L",
                "text": "",
                "reading_order_position": 0,
                "was_changed": True,
                "confidence": 0.9,
                "items": [
                    {"label": "•", "body": "manzana"},
                    {"label": "•", "body": "pera"},
                    {"label": "•", "body": "uva"},
                ],
            },
        ],
    }]
    return DocumentStructure(
        pages=pages,
        document_title="Frutas",
        language="es",
        headings_hierarchy=[],
        page_count=1,
    )


class TestTableTagging:
    def test_table_struct_element_created(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_table(),
        )
        out = tmp_path / "t.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            root = pdf.Root.StructTreeRoot
            serialized = _collect_struct_types(root)
        assert "/Table" in serialized
        assert "/TR" in serialized
        assert "/TH" in serialized
        assert "/TD" in serialized

    def test_first_row_th_has_scope_column(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_table(),
        )
        out = tmp_path / "t.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            ths = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/TH"))
        scopes = []
        for th in ths:
            a = th.get("/A")
            if a is not None and "/Scope" in a:
                scopes.append(str(a["/Scope"]))
        assert "/Column" in scopes
        # Row headers for left column of data rows
        assert "/Row" in scopes

    def test_records_table_header_change(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_table(),
        )
        writer.write(str(tmp_path / "t.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "table_header_tagged" in types


class TestListTagging:
    def test_list_struct_element_created(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_list(),
        )
        out = tmp_path / "l.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            collected = _collect_struct_types(pdf.Root.StructTreeRoot)
        assert "/L" in collected
        assert "/LI" in collected
        assert "/Lbl" in collected
        assert "/LBody" in collected

    def test_list_has_numbering_attribute(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_list(),
        )
        out = tmp_path / "l.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            lists = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/L"))
        assert lists, "no /L struct elem found"
        a = lists[0].get("/A")
        assert a is not None
        assert str(a["/ListNumbering"]) == "/Disc"

    def test_records_list_structured_change(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "simple.pdf"), _structure_with_list(),
        )
        writer.write(str(tmp_path / "l.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "list_structured" in types


def _collect_struct_types(elem, acc=None):
    if acc is None:
        acc = set()
    s = elem.get("/S")
    if s is not None:
        acc.add(str(s))
    k = elem.get("/K")
    if k is None:
        return acc
    try:
        iter(k)
    except TypeError:
        return acc
    for child in k:
        if isinstance(child, pikepdf.Dictionary):
            _collect_struct_types(child, acc)
    return acc


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
