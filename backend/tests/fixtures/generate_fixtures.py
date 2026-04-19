"""
Generate synthetic PDF fixtures for tests.
Run: python tests/fixtures/generate_fixtures.py
(Also invoked automatically by a session-scoped pytest fixture in conftest.)
"""
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
)
from reportlab.lib.enums import TA_LEFT
import io
from PIL import Image as PILImage, ImageDraw

FIXTURES_DIR = Path(__file__).parent


def _placeholder_image(text: str = "CHART", size=(200, 150)) -> bytes:
    img = PILImage.new("RGB", size, color=(70, 130, 180))
    draw = ImageDraw.Draw(img)
    try:
        w, h = draw.textsize(text)
    except AttributeError:
        w, h = 80, 20
    draw.text(((size[0] - w) / 2, (size[1] - h) / 2), text, fill="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_simple_pdf() -> Path:
    """A PDF with a clear title, a subheading, body paragraphs, and one image."""
    path = FIXTURES_DIR / "simple.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"],
        fontSize=24, spaceAfter=20, textColor=colors.HexColor("#1e293b"),
    )
    h2_style = ParagraphStyle(
        "Section", parent=styles["Heading2"],
        fontSize=16, spaceAfter=12,
    )
    story = [
        Paragraph("Annual Report 2024", title_style),
        Paragraph("Introduction", h2_style),
        Paragraph(
            "This is the introduction paragraph. It contains enough "
            "body text at a normal font size so the extractor can "
            "determine the mode font size to be the body size.",
            styles["BodyText"]
        ),
        Spacer(1, 0.2 * inch),
        Paragraph("Financial Results", h2_style),
        Paragraph(
            "Revenue grew significantly in every quarter, with a strong "
            "rebound in Q4 driven by new product launches and improved "
            "market conditions across all operating regions.",
            styles["BodyText"]
        ),
        Spacer(1, 0.2 * inch),
        RLImage(io.BytesIO(_placeholder_image("Q4 CHART")),
                width=2 * inch, height=1.5 * inch),
    ]
    doc.build(story)
    return path


def make_multicolumn_pdf() -> Path:
    """Two-column document with headings and body text."""
    path = FIXTURES_DIR / "multicolumn.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    page_w, page_h = A4

    c.setFont("Helvetica-Bold", 22)
    c.drawString(72, page_h - 72, "Research Paper")

    left_x = 72
    right_x = page_w / 2 + 10
    top_y = page_h - 120

    c.setFont("Helvetica-Bold", 14)
    c.drawString(left_x, top_y, "Abstract")
    c.setFont("Helvetica", 11)
    for i, line in enumerate([
        "This research explores how large",
        "language models with vision can",
        "repair document accessibility at",
        "scale. The method improves PDFs",
        "substantially without manual work.",
    ]):
        c.drawString(left_x, top_y - 20 - i * 14, line)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(right_x, top_y, "Methods")
    c.setFont("Helvetica", 11)
    for i, line in enumerate([
        "We used Gemma 4 via OpenRouter,",
        "combined with PyMuPDF extraction",
        "and pikepdf write-back, validated",
        "by veraPDF against ISO 14289.",
    ]):
        c.drawString(right_x, top_y - 20 - i * 14, line)

    c.save()
    return path


def make_complex_tables_pdf() -> Path:
    """PDF with a table having a short header row and longer data rows."""
    path = FIXTURES_DIR / "complex_tables.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    data = [
        ["Name", "Age", "City"],
        ["Alexander Smith", "28 years old", "Barcelona, Spain"],
        ["Maria Rodriguez-Martinez", "35 years old", "Madrid, Spain"],
        ["Roberto Gonzalez-Pereira", "42 years old", "Valencia, Spain"],
    ]
    table = Table(data, colWidths=[2 * inch, 1.5 * inch, 2 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story = [Paragraph("Employee Directory", styles["Heading1"]), Spacer(1, 0.3 * inch), table]
    doc.build(story)
    return path


def make_scanned_pdf() -> Path:
    """PDF containing an image only (no selectable text)."""
    path = FIXTURES_DIR / "scanned.pdf"
    img_bytes = _placeholder_image("SCANNED PAGE", size=(800, 1100))
    c = canvas.Canvas(str(path), pagesize=A4)
    page_w, page_h = A4
    img_reader = io.BytesIO(img_bytes)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(img_reader), 50, 50, page_w - 100, page_h - 100)
    c.save()
    return path


def make_all() -> dict:
    return {
        "simple.pdf": make_simple_pdf(),
        "multicolumn.pdf": make_multicolumn_pdf(),
        "complex_tables.pdf": make_complex_tables_pdf(),
        "scanned.pdf": make_scanned_pdf(),
    }


if __name__ == "__main__":
    for name, p in make_all().items():
        print(f"Generated: {p} ({p.stat().st_size} bytes)")
