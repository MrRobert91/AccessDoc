from app.models.accessibility import AccessibilityScore, BlockChange
from app.services.job_store import job_store
from app.services.observability.activity_logger import ActivityLogger
from app.services.reporting.report_builder import ReportBuilder


def _setup_job(job_id: str) -> None:
    job_store._jobs.pop(job_id, None)
    job_store.create(
        job_id=job_id,
        original_filename="ejemplo.pdf",
        original_path="/tmp/ejemplo.pdf",
        options={},
    )
    before = AccessibilityScore(
        overall=20, pdfua1_compliant=False, wcag21_aa_compliant=False,
    )
    after = AccessibilityScore(
        overall=88, pdfua1_compliant=True, wcag21_aa_compliant=True,
    )
    changes = [
        BlockChange(
            block_id="b0", page_num=1,
            change_type="heading_tagged", criterion="1.3.1",
            before="(untagged)", after="<H1> Título", confidence=0.95,
            pdfua_rule="7.1-1", wcag_level="A",
        ),
        BlockChange(
            block_id="b1", page_num=1,
            change_type="link_tagged", criterion="2.4.4",
            before="(untagged link)", after="Enlace a example.com",
            confidence=0.6, pdfua_rule="7.18.5", wcag_level="A",
        ),
    ]
    job_store.complete(
        job_id=job_id,
        accessible_pdf_path="/tmp/accesible.pdf",
        before_score=before,
        after_score=after,
        changes=changes,
        remaining_issues=[],
        page_count=2,
        model_used="google/gemma-4-31b-it:free",
    )


def test_render_html_contains_core_sections():
    _setup_job("html-test-1")
    logger = ActivityLogger()
    logger.emit("html-test-1", "extract", "upload_received", "Recibido")
    logger.emit("html-test-1", "write", "page_labels_set", "PageLabels añadidos")

    job = job_store.get("html-test-1")
    html = ReportBuilder().render_html(job)

    assert "<html" in html.lower()
    assert "Reporte de accesibilidad" in html
    assert "ejemplo.pdf" in html
    assert ">88<" in html  # after score
    assert ">20<" in html  # before score
    assert "heading_tagged" in html.replace("_", "_")
    assert "link_tagged" in html
    assert "1.3.1" in html
    assert "2.4.4" in html
    assert "PageLabels añadidos" in html
    job_store._jobs.pop("html-test-1", None)


def test_render_html_marks_low_confidence_rows():
    _setup_job("html-test-2")
    job = job_store.get("html-test-2")
    html = ReportBuilder().render_html(job)
    # Low-confidence row (0.6) should carry the css class
    assert "low-confidence" in html
    job_store._jobs.pop("html-test-2", None)


def test_render_html_escapes_user_content():
    _setup_job("html-test-3")
    job = job_store.get("html-test-3")
    job.result["changes_applied"][0]["after"] = "<script>alert(1)</script>"
    html = ReportBuilder().render_html(job)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    job_store._jobs.pop("html-test-3", None)
