import pytest
from pathlib import Path

pikepdf = pytest.importorskip("pikepdf")

from pikepdf import Array, Dictionary, Name, String  # noqa: E402

from app.services.writing.abbreviation_expander import (  # noqa: E402
    AbbreviationExpander,
    DEFAULT_EXPANSIONS_ES,
)


def _build_pdf_with_span(tmp_path, actual_text: str) -> str:
    """Create a minimal tagged PDF with one /Span carrying /ActualText."""
    src = Path(__file__).parent.parent / "fixtures" / "simple.pdf"
    with pikepdf.open(str(src)) as pdf:
        struct_root = pdf.make_indirect(Dictionary(
            Type=Name("/StructTreeRoot"),
            K=Array(),
        ))
        pdf.Root.StructTreeRoot = struct_root
        doc_elem = pdf.make_indirect(Dictionary(
            Type=Name("/StructElem"),
            S=Name("/Document"),
            P=struct_root,
            K=Array(),
        ))
        struct_root.K.append(doc_elem)
        span = pdf.make_indirect(Dictionary(
            Type=Name("/StructElem"),
            S=Name("/Span"),
            P=doc_elem,
            K=Array(),
            ActualText=String(actual_text),
        ))
        doc_elem.K.append(span)
        out = tmp_path / "abbrev.pdf"
        pdf.save(str(out))
    return str(out)


class TestAbbreviationExpander:
    def test_known_abbrev_gets_expansion(self, tmp_path):
        path = _build_pdf_with_span(tmp_path, "La ONU aprobó la resolución")
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            result = AbbreviationExpander().expand(pdf)
            pdf.save(path)
        assert result.expansions_applied == 1
        assert any(c.change_type == "abbreviation_expanded" for c in result.changes)

        with pikepdf.open(path) as pdf:
            doc = pdf.Root.StructTreeRoot.K[0]
            span = doc.K[0]
            assert "/E" in span
            assert "Naciones Unidas" in str(span["/E"])

    def test_unknown_word_does_not_set_e(self, tmp_path):
        path = _build_pdf_with_span(tmp_path, "palabras comunes sin acrónimo")
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            result = AbbreviationExpander().expand(pdf)
            pdf.save(path)
        assert result.expansions_applied == 0

    def test_custom_expansion_dict(self, tmp_path):
        path = _build_pdf_with_span(tmp_path, "Proyecto XYZ activo")
        with pikepdf.open(path, allow_overwriting_input=True) as pdf:
            result = AbbreviationExpander({"XYZ": "X Y Z corporation"}).expand(pdf)
            pdf.save(path)
        assert result.expansions_applied == 1

    def test_default_map_contains_common_spanish_acronyms(self):
        assert "ONU" in DEFAULT_EXPANSIONS_ES
        assert "UE" in DEFAULT_EXPANSIONS_ES
