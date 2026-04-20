import pytest

pikepdf = pytest.importorskip("pikepdf")

from app.services.writing.pdf_writer import _list_numbering, _split_list_item  # noqa: E402


def test_numbering_decimal_when_numeric_markers():
    items = [{"raw": "1. uno"}, {"raw": "2. dos"}]
    assert str(_list_numbering(items)) == "/Decimal"


def test_numbering_disc_for_bullets():
    items = [{"raw": "• uno"}, {"raw": "• dos"}]
    assert str(_list_numbering(items)) == "/Disc"


def test_numbering_roman():
    items = [{"raw": "I. primero"}, {"raw": "II. segundo"}]
    assert str(_list_numbering(items)) == "/UpperRoman"


def test_numbering_alpha_lower():
    items = [{"raw": "a) primero"}, {"raw": "b) segundo"}]
    assert str(_list_numbering(items)) == "/LowerAlpha"


def test_split_prefers_structured_label_body():
    item = {"label": "•", "body": "manzana"}
    assert _split_list_item(item) == ("•", "manzana")


def test_split_bullet_prefix():
    assert _split_list_item({"raw": "• manzana"}) == ("•", "manzana")


def test_split_numeric_prefix():
    assert _split_list_item({"raw": "1. primero"}) == ("1.", "primero")


def test_split_plain_text_no_marker():
    assert _split_list_item({"raw": "texto libre sin marcador"}) == (
        "",
        "texto libre sin marcador",
    )
