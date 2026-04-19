from pathlib import Path

import structlog

from app.config import settings
from app.services.analysis.gemma_client import GemmaClient
from app.services.analysis.hierarchy_fixer import HierarchyFixer
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.job_store import job_store
from app.services.validation.score_calculator import ScoreCalculator
from app.services.validation.verapdf_runner import VeraPDFRunner
from app.services.writing.pdf_writer import AccessiblePDFWriter

log = structlog.get_logger()


class AccessibilityPipeline:
    def __init__(self):
        self.verapdf = VeraPDFRunner(settings.verapdf_path)
        self.score_calc = ScoreCalculator()

    async def run(self, job_id: str) -> None:
        try:
            await self._execute(job_id)
        except Exception as e:
            log.error("pipeline_failed", job_id=job_id, error=str(e), exc_info=True)
            job_store.fail(job_id, "INTERNAL_ERROR", str(e))

    async def _execute(self, job_id: str) -> None:
        job = job_store.get(job_id)
        if not job:
            return

        job_dir = Path(settings.tmp_dir) / job_id
        original_pdf = job_dir / "original.pdf"
        accessible_pdf = job_dir / "accessible.pdf"

        opts = job.options if isinstance(job.options, dict) else {}
        model_size = opts.get("model_size", "accurate")
        gemma = GemmaClient(model_size=model_size)

        # ─── STAGE 1: EXTRACTION (0% → 15%) ──────────────────
        job_store.update_progress(
            job_id, 5, "extracting", "Extrayendo contenido del PDF..."
        )
        extractor = PDFExtractor(str(original_pdf))
        extraction = extractor.extract_all()

        if extraction.is_password_protected:
            job_store.fail(
                job_id, "PASSWORD_PROTECTED",
                "El PDF está protegido con contraseña",
            )
            return

        before_score = self.score_calc.calculate_before(extraction)

        job_store.update_progress(
            job_id, 15, "extracting",
            f"Extraídas {extraction.page_count} páginas",
            pages_total=extraction.page_count,
        )

        # ─── STAGE 2: SEMANTIC ANALYSIS (15% → 70%) ──────────
        page_structures: list[dict] = []
        pct_per_page = 55.0 / max(extraction.page_count, 1)

        for i, page in enumerate(extraction.pages):
            current_pct = 15 + int(i * pct_per_page)
            job_store.update_progress(
                job_id, current_pct, "analyzing",
                f"Analizando página {i + 1} de {extraction.page_count}...",
                pages_processed=i,
                pages_total=extraction.page_count,
            )

            text_summary = _build_text_summary(page)
            page_structure = await gemma.analyze_page_structure(
                page_image_bytes=page.rendered_image or b"",
                extracted_text=text_summary,
                page_num=i,
            )

            for block in page_structure.get("blocks", []):
                if (
                    block.get("role") == "Figure"
                    and block.get("alt_text_needed")
                    and not block.get("is_decorative")
                ):
                    job_store.update_progress(
                        job_id, current_pct, "generating_alt_text",
                        f"Generando texto alternativo en pág. {i + 1}...",
                    )
                    try:
                        image_crop = page.get_image_crop(
                            block.get("bbox", (0, 0, 100, 100))
                        )
                        alt_text = await gemma.generate_alt_text(
                            image_bytes=image_crop,
                            surrounding_text=block.get("surrounding_text", ""),
                            language=page_structure.get("language", "es"),
                        )
                        block["alt_text"] = alt_text
                        block["was_changed"] = True
                    except Exception as e:
                        log.warning("alt_text_failed", page=i, error=str(e))
                        block["alt_text"] = "decorative"

            page_structures.append(page_structure)

        # ─── STAGE 3: CONSOLIDATE STRUCTURE ───────────────────
        job_store.update_progress(
            job_id, 70, "building_tags",
            "Consolidando estructura del documento...",
        )
        fixer = HierarchyFixer()
        document_structure = fixer.consolidate(
            page_structures, extraction.page_count
        )

        # ─── STAGE 4: WRITE ACCESSIBLE PDF (70% → 85%) ────────
        job_store.update_progress(
            job_id, 75, "building_tags",
            "Construyendo árbol de etiquetas...",
        )
        writer = AccessiblePDFWriter(str(original_pdf), document_structure)
        writer.write(str(accessible_pdf))
        job_store.update_progress(
            job_id, 85, "building_tags", "PDF accesible generado"
        )

        # ─── STAGE 5: VALIDATION + RETRY (85% → 100%) ─────────
        job_store.update_progress(
            job_id, 88, "validating", "Validando conformidad PDF/UA-1..."
        )
        validation = self.verapdf.validate(str(accessible_pdf))
        retry = opts.get("retry_on_low_score", True)

        if not validation.compliant and retry:
            for attempt in range(2):
                if validation.score >= 70:
                    break
                job_store.update_progress(
                    job_id, 91 + attempt * 3, "validating",
                    f"Refinando accesibilidad (intento {attempt + 2}/3)...",
                )
                try:
                    corrected = await gemma.fix_accessibility_issues(
                        {"pages": page_structures},
                        [f.__dict__ for f in validation.failures],
                    )
                    new_pages = corrected.get("pages", page_structures)
                    fixed_structure = fixer.consolidate(
                        new_pages, extraction.page_count
                    )
                    writer = AccessiblePDFWriter(
                        str(original_pdf), fixed_structure
                    )
                    writer.write(str(accessible_pdf))
                    validation = self.verapdf.validate(str(accessible_pdf))
                except Exception as e:
                    log.warning("retry_failed", attempt=attempt, error=str(e))
                    break

        after_score = self.score_calc.calculate_after(validation)
        changes = writer.get_applied_changes()
        remaining = validation.get_remaining_issues()

        job_store.update_progress(
            job_id, 100, "validating", "¡Completado!"
        )
        job_store.complete(
            job_id=job_id,
            accessible_pdf_path=str(accessible_pdf),
            before_score=before_score,
            after_score=after_score,
            changes=changes,
            remaining_issues=remaining,
            page_count=extraction.page_count,
            model_used=gemma.model_name,
        )


def _build_text_summary(page) -> str:
    lines = []
    for block in sorted(page.text_blocks, key=lambda b: b.bbox[1]):
        size_info = (
            f"[{block.font_size:.0f}pt]" if block.is_heading_candidate else ""
        )
        bold_info = "[BOLD]" if block.is_bold else ""
        lines.append(f"{size_info}{bold_info} {block.text}".strip())
    return "\n".join(lines[:200])
