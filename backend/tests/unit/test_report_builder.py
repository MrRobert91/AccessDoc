from app.models.accessibility import AccessibilityScore, BlockChange
from app.services.job_store import job_store
from app.services.observability.activity_logger import ActivityLogger
from app.services.reporting.report_builder import ReportBuilder


def _setup_completed_job(job_id: str) -> None:
    job_store._jobs.pop(job_id, None)
    job_store.create(
        job_id=job_id,
        original_filename="doc.pdf",
        original_path="/tmp/doc.pdf",
        options={},
    )
    before = AccessibilityScore(
        overall=15, pdfua1_compliant=False, wcag21_aa_compliant=False,
    )
    after = AccessibilityScore(
        overall=92, pdfua1_compliant=True, wcag21_aa_compliant=True,
    )
    changes = [
        BlockChange(
            block_id="b0", page_num=1,
            change_type="heading_tagged", criterion="1.3.1",
            pdfua_rule="7.1-1",
        ),
        BlockChange(
            block_id="b1", page_num=2,
            change_type="alt_text_added", criterion="1.1.1",
            pdfua_rule="7.18.1",
        ),
        BlockChange(
            block_id="b2", page_num=1,
            change_type="heading_tagged", criterion="1.3.1",
            pdfua_rule="7.1-1",
        ),
    ]
    job_store.complete(
        job_id=job_id,
        accessible_pdf_path="/tmp/acc.pdf",
        before_score=before,
        after_score=after,
        changes=changes,
        remaining_issues=[],
        page_count=3,
        model_used="google/gemma-4-31b-it:free",
    )


def test_report_groups_changes_by_page():
    _setup_completed_job("report-test-1")
    logger = ActivityLogger()
    logger.emit("report-test-1", "extract", "upload_received", "ok")

    job = job_store.get("report-test-1")
    report = ReportBuilder().build(job)

    assert report["job_id"] == "report-test-1"
    assert report["page_count"] == 3
    assert "1" in report["changes_by_page"]
    assert len(report["changes_by_page"]["1"]) == 2
    assert len(report["changes_by_page"]["2"]) == 1
    job_store._jobs.pop("report-test-1", None)


def test_report_groups_by_criterion_and_includes_activity():
    _setup_completed_job("report-test-2")
    logger = ActivityLogger()
    logger.emit("report-test-2", "validate", "verapdf_completed", "done")

    job = job_store.get("report-test-2")
    report = ReportBuilder().build(job)

    assert "1.3.1" in report["changes_by_criterion"]
    assert len(report["changes_by_criterion"]["1.3.1"]) == 2
    assert "1.1.1" in report["changes_by_criterion"]
    assert report["scores"]["after"]["overall"] == 92
    assert len(report["activity_log"]) >= 1
    assert report["activity_log"][0]["code"] == "verapdf_completed"
    job_store._jobs.pop("report-test-2", None)


def test_report_summary_counts_change_types():
    _setup_completed_job("report-test-3")
    job = job_store.get("report-test-3")
    report = ReportBuilder().build(job)
    assert report["changes_summary"]["heading_tagged"] == 2
    assert report["changes_summary"]["alt_text_added"] == 1
    job_store._jobs.pop("report-test-3", None)


def test_report_has_verbose_summary_with_explanations():
    _setup_completed_job("report-test-4")
    job = job_store.get("report-test-4")
    report = ReportBuilder().build(job)

    detailed = report["changes_summary_detailed"]
    assert isinstance(detailed, list)
    by_type = {row["change_type"]: row for row in detailed}

    heading_row = by_type["heading_tagged"]
    assert heading_row["count"] == 2
    assert heading_row["title"]
    assert heading_row["why"]
    assert heading_row["wcag"] == "1.3.1"

    alt_row = by_type["alt_text_added"]
    assert alt_row["wcag"] == "1.1.1"
    assert alt_row["pdfua"] == "7.18.1"

    job_store._jobs.pop("report-test-4", None)


def test_report_has_narrative_sections():
    _setup_completed_job("report-test-5")
    job = job_store.get("report-test-5")
    report = ReportBuilder().build(job)

    narrative = report["narrative"]
    headings = [s["heading"] for s in narrative]
    assert "El documento original" in headings
    assert "Qué detectamos" in headings
    assert "Qué hicimos, paso a paso" in headings
    assert "Qué queda pendiente" in headings
    assert "Resultado" in headings

    steps_section = next(s for s in narrative if s["heading"] == "Qué hicimos, paso a paso")
    assert len(steps_section["steps"]) >= 2
    first = steps_section["steps"][0]
    assert first["number"] == 1
    assert first["title"]

    result_section = next(s for s in narrative if s["heading"] == "Resultado")
    joined = " ".join(result_section["paragraphs"])
    assert "15" in joined and "92" in joined

    job_store._jobs.pop("report-test-5", None)


def test_report_builds_glossary_from_used_criteria():
    _setup_completed_job("report-test-6")
    job = job_store.get("report-test-6")
    report = ReportBuilder().build(job)

    glossary = report["glossary"]
    wcag_codes = [c["code"] for c in glossary["wcag"]]
    assert "1.1.1" in wcag_codes
    assert "1.3.1" in wcag_codes
    pdfua_rules = [r["rule"] for r in glossary["pdfua"]]
    assert "7.18.1" in pdfua_rules

    job_store._jobs.pop("report-test-6", None)


def test_activity_event_carries_explanation():
    job_store._jobs.pop("explain-test-1", None)
    job_store.create(
        job_id="explain-test-1",
        original_filename="x.pdf",
        original_path="/tmp/x.pdf",
        options={},
    )
    logger = ActivityLogger()
    event = logger.emit(
        "explain-test-1", "write", "form_fields_tagged",
        "2 campo(s) etiquetados", details={"fields": 2},
    )
    assert event is not None
    assert event.details and "explanation" in event.details
    exp = event.details["explanation"]
    assert exp["title"]
    assert exp["wcag"] == "4.1.2"
    assert exp["pdfua"] == "7.18.4"
    job_store._jobs.pop("explain-test-1", None)
