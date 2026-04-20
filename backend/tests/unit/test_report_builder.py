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
