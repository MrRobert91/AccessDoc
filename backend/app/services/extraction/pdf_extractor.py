import io
from dataclasses import dataclass, field
from typing import Optional

import pymupdf
import pdfplumber
from PIL import Image


@dataclass
class TextBlock:
    text: str
    font_name: str
    font_size: float
    is_bold: bool
    is_italic: bool
    bbox: tuple[float, float, float, float]
    page_num: int
    block_type: str = "text"
    is_heading_candidate: bool = False


@dataclass
class TableData:
    rows: list[list[str]]
    bbox: tuple
    page_num: int
    has_header_row: bool = False


@dataclass
class ImageData:
    image_bytes: bytes
    bbox: tuple
    page_num: int


@dataclass
class PageData:
    page_num: int
    width: float
    height: float
    text_blocks: list[TextBlock]
    tables: list[TableData]
    images: list[ImageData]
    body_font_size: float
    rendered_image: Optional[bytes] = None

    def get_image_crop(self, bbox: tuple) -> bytes:
        if not self.rendered_image:
            raise ValueError("Page not rendered")
        img = Image.open(io.BytesIO(self.rendered_image))
        scale_x = img.width / self.width if self.width else 1.0
        scale_y = img.height / self.height if self.height else 1.0
        x0, y0, x1, y1 = bbox
        crop = img.crop((
            int(x0 * scale_x), int(y0 * scale_y),
            int(x1 * scale_x), int(y1 * scale_y),
        ))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        return buf.getvalue()


@dataclass
class ExtractionResult:
    pages: list[PageData]
    page_count: int
    needs_ocr: bool
    is_password_protected: bool = False
    has_existing_tags: bool = False


class PDFExtractor:
    HEADING_SIZE_RATIO = 1.15
    RENDER_DPI = 150

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self._mupdf = pymupdf.open(pdf_path)

    def extract_all(self) -> ExtractionResult:
        if self._mupdf.is_encrypted:
            return ExtractionResult(
                pages=[], page_count=0,
                needs_ocr=False, is_password_protected=True,
            )

        pages: list[PageData] = []
        total_text_chars = 0

        with pdfplumber.open(self.pdf_path) as plumber_pdf:
            for page_num in range(len(self._mupdf)):
                page_data = self._extract_page(
                    mupdf_page=self._mupdf[page_num],
                    plumber_page=plumber_pdf.pages[page_num],
                    page_num=page_num,
                )
                pages.append(page_data)
                total_text_chars += sum(len(b.text) for b in page_data.text_blocks)

        avg_chars = total_text_chars / max(len(pages), 1)
        needs_ocr = avg_chars < 50

        if needs_ocr and self._has_form_widgets():
            needs_ocr = False

        try:
            catalog = self._mupdf.pdf_catalog()
            has_tags = catalog is not None and "MarkInfo" in str(catalog)
        except Exception:
            has_tags = False

        return ExtractionResult(
            pages=pages,
            page_count=len(pages),
            needs_ocr=needs_ocr,
            has_existing_tags=has_tags,
        )

    def _has_form_widgets(self) -> bool:
        try:
            if getattr(self._mupdf, "is_form_pdf", False):
                return True
            for page in self._mupdf:
                widgets = list(page.widgets() or [])
                if widgets:
                    return True
        except Exception:
            return False
        return False

    def _extract_page(self, mupdf_page, plumber_page, page_num: int) -> PageData:
        words = plumber_page.extract_words(
            extra_attrs=["fontname", "size"],
            use_text_flow=True,
            keep_blank_chars=False,
        )

        font_sizes = [w.get("size", 12) or 12 for w in words]
        body_size = _statistical_mode(font_sizes) if font_sizes else 12.0

        text_blocks: list[TextBlock] = []
        for word in words:
            size = word.get("size", 12) or 12
            fontname = word.get("fontname", "") or ""
            is_bold = any(x in fontname for x in ["Bold", "bold", "Heavy", "Black"])
            is_italic = any(x in fontname for x in ["Italic", "Oblique", "italic"])
            is_heading = (
                size >= body_size * self.HEADING_SIZE_RATIO
                or (is_bold and size >= body_size * 0.95)
            )
            text_blocks.append(TextBlock(
                text=word["text"],
                font_name=fontname,
                font_size=float(size),
                is_bold=is_bold,
                is_italic=is_italic,
                bbox=(
                    float(word["x0"]), float(word["top"]),
                    float(word["x1"]), float(word["bottom"]),
                ),
                page_num=page_num,
                is_heading_candidate=is_heading,
            ))

        tables: list[TableData] = []
        try:
            found_tables = plumber_page.find_tables()
        except Exception:
            found_tables = []
        for table_obj in found_tables:
            extracted = table_obj.extract()
            if extracted:
                tables.append(TableData(
                    rows=[[str(cell or "") for cell in row] for row in extracted],
                    bbox=table_obj.bbox,
                    page_num=page_num,
                    has_header_row=_detect_header_row(extracted),
                ))

        images: list[ImageData] = []
        for img_info in mupdf_page.get_images(full=True):
            xref = img_info[0]
            try:
                img_data = self._mupdf.extract_image(xref)
                rects = mupdf_page.get_image_rects(xref)
                rect = rects[0] if rects else None
                bbox = (rect.x0, rect.y0, rect.x1, rect.y1) if rect else (0, 0, 0, 0)
                images.append(ImageData(
                    image_bytes=img_data["image"],
                    bbox=bbox,
                    page_num=page_num,
                ))
            except Exception:
                continue

        mat = pymupdf.Matrix(self.RENDER_DPI / 72, self.RENDER_DPI / 72)
        pix = mupdf_page.get_pixmap(matrix=mat, alpha=False)
        rendered = pix.tobytes("png")

        return PageData(
            page_num=page_num,
            width=float(plumber_page.width),
            height=float(plumber_page.height),
            text_blocks=text_blocks,
            tables=tables,
            images=images,
            body_font_size=body_size,
            rendered_image=rendered,
        )


def _statistical_mode(values: list[float]) -> float:
    if not values:
        return 12.0
    rounded = [round(v * 2) / 2 for v in values]
    return max(set(rounded), key=rounded.count)


def _detect_header_row(table: list[list]) -> bool:
    if not table or len(table) < 2:
        return False
    first_cells = table[0]
    first_avg = sum(len(str(c or "")) for c in first_cells) / max(len(first_cells), 1)
    data_rows = table[1:]
    data_total = 0.0
    data_count = 0
    for row in data_rows:
        if row:
            data_total += sum(len(str(c or "")) for c in row) / max(len(row), 1)
            data_count += 1
    if data_count == 0:
        return False
    rest_avg = data_total / data_count
    return first_avg < rest_avg * 0.7
