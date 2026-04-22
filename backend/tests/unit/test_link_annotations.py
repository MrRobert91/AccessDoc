import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from app.services.writing.pdf_writer import AccessiblePDFWriter  # noqa: E402
from app.services.analysis.hierarchy_fixer import DocumentStructure  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _empty_structure() -> DocumentStructure:
    return DocumentStructure(
        pages=[{"page_num": 0, "language": "es", "blocks": []}],
        document_title="Referencias",
        language="es",
        headings_hierarchy=[],
        page_count=1,
    )


class TestLinkAnnotationsTagger:
    def test_link_struct_elems_created(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "links.pdf"), _empty_structure(),
        )
        out = tmp_path / "links_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            link_elems = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/Link"))
        assert len(link_elems) >= 1, "no /Link StructElems found"

    def test_link_has_objr(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "links.pdf"), _empty_structure(),
        )
        out = tmp_path / "links_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            link_elems = list(_find_elems_by_type(pdf.Root.StructTreeRoot, "/Link"))
            assert link_elems
            first = link_elems[0]
            k = first.get("/K")
            assert k is not None
            try:
                kids = list(k)
            except TypeError:
                kids = [k]
            objr = None
            for child in kids:
                if isinstance(child, pikepdf.Dictionary) and str(child.get("/Type", "")) == "/OBJR":
                    objr = child
                    break
            assert objr is not None, "no /OBJR found inside /Link"
            assert "/Obj" in objr
            assert "/Pg" in objr

    def test_annotation_has_struct_parent_and_contents(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "links.pdf"), _empty_structure(),
        )
        out = tmp_path / "links_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            page = pdf.pages[0]
            annots = page.get("/Annots") or []
            link_annots = [
                a for a in annots
                if isinstance(a, pikepdf.Dictionary) and str(a.get("/Subtype", "")) == "/Link"
            ]
            assert link_annots, "fixture should have link annotations"
            for a in link_annots:
                assert "/StructParent" in a
                assert "/Contents" in a and str(a["/Contents"]).strip()

    def test_parent_tree_updated_with_new_keys(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "links.pdf"), _empty_structure(),
        )
        out = tmp_path / "links_tagged.pdf"
        writer.write(str(out))
        with pikepdf.open(str(out)) as pdf:
            struct_root = pdf.Root.StructTreeRoot
            next_key = int(struct_root.ParentTreeNextKey)
            # After tagging links, ParentTreeNextKey must be > num pages
            assert next_key > len(pdf.pages)
            nums = struct_root.ParentTree.Nums
            keys = [int(nums[i]) for i in range(0, len(nums), 2)]
            # Keys must include at least one value beyond the page indices
            assert any(k >= len(pdf.pages) for k in keys)

    def test_records_link_tagged_change(self, tmp_path):
        writer = AccessiblePDFWriter(
            str(FIXTURES / "links.pdf"), _empty_structure(),
        )
        writer.write(str(tmp_path / "links_tagged.pdf"))
        types = {c.change_type for c in writer.get_applied_changes()}
        assert "link_tagged" in types


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
