"""
Lightweight post-write scanners that surface PDF/UA issues not covered by
structural tagging: FR-A13 (fonts without /ToUnicode), FR-A14 (low
contrast on raster content). Results are emitted as RemainingIssue so
they appear in /report and the UI alongside veraPDF failures.
"""
from dataclasses import dataclass

import pikepdf
import structlog

from app.models.accessibility import RemainingIssue

log = structlog.get_logger()


@dataclass
class ScanResult:
    font_issues: list[RemainingIssue]
    contrast_issues: list[RemainingIssue]

    @property
    def all(self) -> list[RemainingIssue]:
        return [*self.font_issues, *self.contrast_issues]


class FontScanner:
    """FR-A13: detect embedded fonts that lack /ToUnicode mapping."""

    def scan(self, pdf_path: str) -> list[RemainingIssue]:
        pages_affected: dict[str, set[int]] = {}
        try:
            with pikepdf.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    resources = page.get("/Resources")
                    if resources is None:
                        continue
                    fonts = resources.get("/Font") if isinstance(
                        resources, pikepdf.Dictionary
                    ) else None
                    if fonts is None or not isinstance(fonts, pikepdf.Dictionary):
                        continue
                    for font_name, font_obj in fonts.items():
                        if not isinstance(font_obj, pikepdf.Dictionary):
                            continue
                        if font_obj.get("/ToUnicode") is not None:
                            continue
                        base = str(
                            font_obj.get("/BaseFont")
                            or font_obj.get("/Name")
                            or str(font_name)
                        ).lstrip("/")
                        if _is_standard_14(base):
                            continue
                        pages_affected.setdefault(base, set()).add(page_idx + 1)
        except Exception as e:
            log.warning("font_scan_failed", error=str(e))
            return []

        issues: list[RemainingIssue] = []
        for base, pages in pages_affected.items():
            pages_sorted = sorted(pages)
            issues.append(RemainingIssue(
                criterion="1.3.1",
                severity="minor",
                description=(
                    f"Fuente sin /ToUnicode: {base} "
                    f"(no se puede extraer texto de forma fiable)"
                ),
                count=len(pages_sorted),
                pages_affected=pages_sorted,
            ))
        return issues


class ContrastScanner:
    """
    FR-A14: flag pages whose text-vs-background contrast cannot be
    guaranteed — specifically, scanned / image-only pages where the
    writer cannot measure luminance of the glyph strokes.

    v1 heuristic: if a page has zero selectable text after OCR, we mark
    it as "contrast no verificable". Raster luminance sampling would
    require Pillow + rendered thumbs and is deferred.
    """

    def scan(self, pdf_path: str) -> list[RemainingIssue]:
        unverifiable_pages: list[int] = []
        try:
            with pikepdf.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    try:
                        text = page.get("/Contents")
                    except Exception:
                        text = None
                    resources = page.get("/Resources")
                    has_text_font = False
                    if isinstance(resources, pikepdf.Dictionary):
                        fonts = resources.get("/Font")
                        has_text_font = bool(
                            fonts is not None
                            and isinstance(fonts, pikepdf.Dictionary)
                            and len(fonts) > 0
                        )
                    if text is None and not has_text_font:
                        unverifiable_pages.append(page_idx + 1)
        except Exception as e:
            log.warning("contrast_scan_failed", error=str(e))
            return []

        if not unverifiable_pages:
            return []

        return [RemainingIssue(
            criterion="1.4.3",
            severity="minor",
            description=(
                "Contraste no verificable automáticamente "
                "(página sin texto seleccionable tras OCR)"
            ),
            count=len(unverifiable_pages),
            pages_affected=unverifiable_pages,
        )]


def scan_pdf(pdf_path: str) -> ScanResult:
    return ScanResult(
        font_issues=FontScanner().scan(pdf_path),
        contrast_issues=ContrastScanner().scan(pdf_path),
    )


_STANDARD_14 = {
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}


def _is_standard_14(base: str) -> bool:
    bare = base.split("+", 1)[-1]
    return bare in _STANDARD_14
