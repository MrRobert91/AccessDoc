import time
from pathlib import Path

import structlog

from app.config import settings
from app.services.analysis.gemma_client import GemmaClient
from app.services.analysis.hierarchy_fixer import HierarchyFixer
from app.services.extraction.ocr_runner import OCRRunner
from app.services.extraction.pdf_extractor import PDFExtractor
from app.services.job_store import job_store
from app.services.observability.activity_logger import activity
from app.services.validation.issue_scanner import scan_pdf
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
            activity.emit(
                job_id, "report", "pipeline_failed",
                f"Pipeline error: {e}",
                level="error", details={"error": str(e)},
            )
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

        try:
            size_mb = original_pdf.stat().st_size / (1024 * 1024)
        except OSError:
            size_mb = 0.0
        activity.emit(
            job_id, "extract", "upload_received",
            f"PDF recibido ({size_mb:.2f} MB)",
            details={"size_mb": round(size_mb, 3)},
        )

        # ─── STAGE 1: EXTRACTION (0% → 15%) ──────────────────
        job_store.update_progress(
            job_id, 5, "extracting", "Extrayendo contenido del PDF..."
        )
        t0 = time.monotonic()
        extractor = PDFExtractor(str(original_pdf))
        extraction = extractor.extract_all()
        extract_ms = int((time.monotonic() - t0) * 1000)

        if extraction.is_password_protected:
            activity.emit(
                job_id, "extract", "pdf_opened",
                "El PDF está protegido con contraseña",
                level="error",
            )
            job_store.fail(
                job_id, "PASSWORD_PROTECTED",
                "El PDF está protegido con contraseña",
            )
            return

        activity.emit(
            job_id, "extract", "pdf_opened",
            f"PDF abierto: {extraction.page_count} páginas",
            duration_ms=extract_ms,
            details={
                "pages": extraction.page_count,
                "has_existing_tags": extraction.has_existing_tags,
                "needs_ocr": extraction.needs_ocr,
            },
        )

        for page in extraction.pages:
            activity.emit(
                job_id, "extract", "page_extracted",
                f"Página {page.page_num + 1} extraída: "
                f"{len(page.text_blocks)} bloques, "
                f"{len(page.tables)} tablas, "
                f"{len(page.images)} imágenes",
                page=page.page_num + 1,
                details={
                    "text_blocks": len(page.text_blocks),
                    "tables": len(page.tables),
                    "images": len(page.images),
                },
            )

        if extraction.needs_ocr:
            activity.emit(
                job_id, "extract", "ocr_needed",
                "Se detecta PDF escaneado; se intentará OCR",
                level="warn",
                details={"enable_ocr": settings.enable_ocr},
            )
            if settings.enable_ocr:
                ocr_out = job_dir / "original_ocr.pdf"
                runner = OCRRunner()
                activity.emit(
                    job_id, "ocr", "ocr_started",
                    f"Ejecutando OCR ({runner.languages})",
                    details={"engine": "tesseract", "language": runner.languages},
                )
                ocr_result = runner.run(str(original_pdf), str(ocr_out))
                if ocr_result.ok:
                    activity.emit(
                        job_id, "ocr", "ocr_completed",
                        f"OCR completado en {ocr_result.duration_ms} ms",
                        duration_ms=ocr_result.duration_ms,
                        details={
                            "language": ocr_result.language,
                            "engine": ocr_result.engine,
                        },
                    )
                    original_pdf = ocr_out
                    extractor = PDFExtractor(str(original_pdf))
                    extraction = extractor.extract_all()
                    activity.emit(
                        job_id, "extract", "pdf_opened",
                        f"PDF re-extraído tras OCR: {extraction.page_count} páginas, "
                        f"needs_ocr={extraction.needs_ocr}",
                        details={
                            "pages": extraction.page_count,
                            "needs_ocr": extraction.needs_ocr,
                            "source": "ocr",
                        },
                    )
                else:
                    activity.emit(
                        job_id, "ocr", "ocr_failed",
                        f"OCR falló: {ocr_result.error or 'error desconocido'}",
                        level="warn",
                        duration_ms=ocr_result.duration_ms,
                        details={"error": ocr_result.error},
                    )

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
            activity.emit(
                job_id, "analyze", "page_analysis_started",
                f"Analizando página {i + 1}...",
                page=i + 1,
            )

            text_summary = _build_text_summary(page)
            t_page = time.monotonic()
            page_structure = await gemma.analyze_page_structure(
                page_image_bytes=page.rendered_image or b"",
                extracted_text=text_summary,
                page_num=i,
            )
            page_ms = int((time.monotonic() - t_page) * 1000)

            blocks = page_structure.get("blocks", [])
            for block in blocks:
                role = block.get("role", "P")
                conf = float(block.get("confidence", 0.0) or 0.0)
                text = (block.get("text") or "")[:60]
                activity.emit(
                    job_id, "analyze", "block_classified",
                    f"Página {i + 1} · bloque {block.get('id', '?')} → "
                    f"{role} \"{text}\" ({conf:.2f})",
                    page=i + 1,
                    details={
                        "block_id": block.get("id"),
                        "role": role,
                        "confidence": conf,
                        "text": text,
                    },
                )
                if conf and conf < 0.5:
                    activity.emit(
                        job_id, "analyze", "low_confidence_fallback",
                        f"Confianza baja ({conf:.2f}) en bloque "
                        f"{block.get('id', '?')}",
                        level="warn",
                        page=i + 1,
                        details={"block_id": block.get("id"), "confidence": conf},
                    )

                if (
                    block.get("role") == "Figure"
                    and block.get("alt_text_needed")
                    and not block.get("is_decorative")
                ):
                    job_store.update_progress(
                        job_id, current_pct, "generating_alt_text",
                        f"Generando texto alternativo en pág. {i + 1}...",
                    )
                    t_alt = time.monotonic()
                    try:
                        image_crop = page.get_image_crop(
                            block.get("bbox", (0, 0, 100, 100))
                        )
                        alt_text = await gemma.generate_alt_text(
                            image_bytes=image_crop,
                            surrounding_text=block.get("surrounding_text", ""),
                            language=page_structure.get("language", "es"),
                        )
                        alt_ms = int((time.monotonic() - t_alt) * 1000)
                        block["alt_text"] = alt_text
                        block["was_changed"] = True
                        activity.emit(
                            job_id, "analyze", "alt_text_generated",
                            f"Alt text para {block.get('id')}: "
                            f"\"{alt_text[:50]}\"",
                            page=i + 1,
                            duration_ms=alt_ms,
                            details={
                                "block_id": block.get("id"),
                                "length": len(alt_text),
                            },
                        )
                    except Exception as e:
                        log.warning("alt_text_failed", page=i, error=str(e))
                        block["alt_text"] = "decorative"
                        activity.emit(
                            job_id, "analyze", "alt_text_failed",
                            f"Fallo alt text pág {i + 1}",
                            level="warn",
                            page=i + 1,
                            details={"error": str(e)},
                        )

            if page.tables:
                page_structure["extracted_tables"] = [
                    {
                        "rows": t.rows,
                        "bbox": list(t.bbox) if t.bbox else None,
                        "has_header_row": bool(t.has_header_row),
                    }
                    for t in page.tables
                ]

            activity.emit(
                job_id, "analyze", "page_analysis_completed",
                f"Página {i + 1} analizada: {len(blocks)} bloques, "
                f"{len(page.tables)} tablas",
                page=i + 1,
                duration_ms=page_ms,
                details={"blocks": len(blocks), "tables": len(page.tables)},
            )

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
        activity.emit(
            job_id, "tag", "hierarchy_normalized",
            f"Jerarquía consolidada: {len(document_structure.headings_hierarchy)} "
            f"encabezados, idioma {document_structure.language}",
            details={
                "headings": len(document_structure.headings_hierarchy),
                "language": document_structure.language,
                "title": document_structure.document_title,
            },
        )
        if document_structure.document_title:
            activity.emit(
                job_id, "tag", "title_detected",
                f"Título: {document_structure.document_title[:60]}",
                details={"value": document_structure.document_title},
            )
        activity.emit(
            job_id, "tag", "language_detected",
            f"Idioma: {document_structure.language}",
            details={"value": document_structure.language},
        )

        # ─── STAGE 4: WRITE ACCESSIBLE PDF (70% → 85%) ────────
        job_store.update_progress(
            job_id, 75, "building_tags",
            "Construyendo árbol de etiquetas...",
        )
        writer = AccessiblePDFWriter(str(original_pdf), document_structure)
        t_write = time.monotonic()
        writer.write(str(accessible_pdf))
        write_ms = int((time.monotonic() - t_write) * 1000)
        stats = writer.get_write_stats()

        for page_idx, mcid_count in stats.get("per_page", {}).items():
            if mcid_count > 0:
                activity.emit(
                    job_id, "write", "mcid_assigned",
                    f"Página {page_idx + 1}: {mcid_count} MCIDs asignados",
                    page=page_idx + 1,
                    details={"mcid_count": mcid_count},
                )

        if stats.get("page_labels"):
            activity.emit(
                job_id, "write", "page_labels_set",
                f"/PageLabels añadidos (decimal 1..{extraction.page_count})",
                details={"scheme": "decimal", "pages": extraction.page_count},
            )

        if stats.get("links_tagged", 0) > 0:
            activity.emit(
                job_id, "write", "annotations_tagged",
                f"{stats['links_tagged']} enlace(s) etiquetados como /Link",
                details={"links": stats["links_tagged"]},
            )

        if stats.get("fields_tagged", 0) > 0:
            activity.emit(
                job_id, "write", "form_fields_tagged",
                f"{stats['fields_tagged']} campo(s) de formulario etiquetados",
                details={"fields": stats["fields_tagged"]},
            )

        if stats.get("abbreviations_expanded", 0) > 0:
            activity.emit(
                job_id, "write", "abbreviations_expanded",
                f"{stats['abbreviations_expanded']} abreviatura(s) expandidas (/E)",
                details={"count": stats["abbreviations_expanded"]},
            )

        activity.emit(
            job_id, "write", "pdf_written",
            f"PDF accesible escrito ({stats.get('struct_elems', 0)} StructElems, "
            f"{stats.get('mcid_linked', 0)}/{stats.get('mcid_total', 0)} MCIDs enlazados)",
            duration_ms=write_ms,
            details=stats,
        )

        job_store.update_progress(
            job_id, 85, "building_tags", "PDF accesible generado"
        )

        # ─── STAGE 5: VALIDATION + RETRY (85% → 100%) ─────────
        job_store.update_progress(
            job_id, 88, "validating", "Validando conformidad PDF/UA-1..."
        )
        activity.emit(
            job_id, "validate", "verapdf_started",
            "Validación veraPDF iniciada",
        )
        t_vera = time.monotonic()
        validation = self.verapdf.validate(str(accessible_pdf))
        vera_ms = int((time.monotonic() - t_vera) * 1000)
        activity.emit(
            job_id, "validate", "verapdf_completed",
            f"veraPDF: compliant={validation.compliant}, "
            f"score={validation.score}, "
            f"{validation.rules_passed}/{validation.rules_total} reglas",
            duration_ms=vera_ms,
            details={
                "compliant": validation.compliant,
                "score": validation.score,
                "rules_passed": validation.rules_passed,
                "rules_total": validation.rules_total,
            },
        )
        for f in validation.failures[:50]:
            activity.emit(
                job_id, "validate", "verapdf_rule_failed",
                f"Regla {f.rule_id} fallida: {f.description[:80]}",
                level="warn",
                page=f.page,
                details={
                    "rule_id": f.rule_id,
                    "wcag": f.wcag_criterion,
                    "severity": f.severity,
                },
            )

        retry = opts.get("retry_on_low_score", True)
        if not validation.compliant and retry:
            for attempt in range(2):
                if validation.score >= 70:
                    break
                activity.emit(
                    job_id, "retry", "fix_attempt_started",
                    f"Intento de corrección {attempt + 2}/3",
                    details={"attempt": attempt + 1, "prev_score": validation.score},
                )
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
                    activity.emit(
                        job_id, "retry", "fix_attempt_completed",
                        f"Intento {attempt + 1}: score={validation.score}",
                        details={
                            "attempt": attempt + 1,
                            "new_score": validation.score,
                        },
                    )
                except Exception as e:
                    log.warning("retry_failed", attempt=attempt, error=str(e))
                    activity.emit(
                        job_id, "retry", "fix_attempt_failed",
                        f"Intento {attempt + 1} falló",
                        level="warn",
                        details={"error": str(e)},
                    )
                    break

        after_score = self.score_calc.calculate_after(validation)
        changes = writer.get_applied_changes()
        remaining = validation.get_remaining_issues()

        try:
            scan = scan_pdf(str(accessible_pdf))
            remaining.extend(scan.all)
            if scan.font_issues:
                activity.emit(
                    job_id, "validate", "font_issues_detected",
                    f"{len(scan.font_issues)} fuente(s) sin /ToUnicode",
                    level="warn",
                    details={"count": len(scan.font_issues)},
                )
            if scan.contrast_issues:
                activity.emit(
                    job_id, "validate", "contrast_unverifiable",
                    (
                        f"{scan.contrast_issues[0].count} página(s) con contraste "
                        f"no verificable"
                    ),
                    level="warn",
                    details={"pages": scan.contrast_issues[0].pages_affected},
                )
        except Exception as e:
            log.warning("issue_scan_failed", error=str(e))

        activity.emit(
            job_id, "report", "report_generated",
            f"Remediación completada: score {before_score.overall} → "
            f"{after_score.overall}",
            details={
                "before": before_score.overall,
                "after": after_score.overall,
                "changes": len(changes),
                "remaining": len(remaining),
            },
        )

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
