import pytest
from datetime import datetime, timedelta
from app.services.job_store import JobStore
from app.models.accessibility import AccessibilityScore, BlockChange


@pytest.fixture
def store():
    return JobStore()


class TestJobStore:
    def test_create_and_get_job(self, store):
        store.create("job-1", "test.pdf", "/tmp/test.pdf", {})
        fetched = store.get("job-1")
        assert fetched is not None
        assert fetched.job_id == "job-1"
        assert fetched.original_filename == "test.pdf"

    def test_get_nonexistent_job_returns_none(self, store):
        assert store.get("does-not-exist") is None

    def test_exists_returns_true_for_existing_job(self, store):
        store.create("job-2", "test.pdf", "/tmp/test.pdf", {})
        assert store.exists("job-2") is True
        assert store.exists("job-999") is False

    def test_update_progress(self, store):
        store.create("job-3", "test.pdf", "/tmp/test.pdf", {})
        store.update_progress("job-3", 50, "analyzing", "Analyzing page 5...")
        job = store.get("job-3")
        assert job.progress.progress_pct == 50
        assert job.progress.status == "analyzing"
        assert job.progress.current_step == "Analyzing page 5..."

    def test_update_progress_with_pages(self, store):
        store.create("job-3b", "test.pdf", "/tmp/test.pdf", {})
        store.update_progress(
            "job-3b", 30, "analyzing", "Page 3 of 10", pages_processed=3, pages_total=10
        )
        job = store.get("job-3b")
        assert job.progress.pages_processed == 3
        assert job.progress.pages_total == 10

    def test_complete_job(self, store):
        store.create("job-4", "test.pdf", "/tmp/test.pdf", {})
        after_score = AccessibilityScore(
            overall=95, pdfua1_compliant=True, wcag21_aa_compliant=True
        )
        before_score = AccessibilityScore(
            overall=20, pdfua1_compliant=False, wcag21_aa_compliant=False
        )
        store.complete(
            job_id="job-4",
            accessible_pdf_path="/tmp/job-4/accessible.pdf",
            before_score=before_score,
            after_score=after_score,
            changes=[BlockChange("b1", 1, "alt_text_added", "1.1.1")],
            remaining_issues=[],
            page_count=5,
            model_used="google/gemma-4-31b-it:free",
        )
        job = store.get("job-4")
        assert job.status == "completed"
        assert job.result is not None
        assert job.result["after_score"]["overall"] == 95
        assert job.result["page_count"] == 5
        assert job.accessible_pdf_path == "/tmp/job-4/accessible.pdf"

    def test_fail_job(self, store):
        store.create("job-5", "test.pdf", "/tmp/test.pdf", {})
        store.fail("job-5", "INTERNAL_ERROR", "Something went wrong")
        job = store.get("job-5")
        assert job.status == "failed"
        assert job.error_code == "INTERNAL_ERROR"
        assert job.error_message == "Something went wrong"

    def test_expired_job_returns_none(self, store):
        store.create("job-6", "test.pdf", "/tmp/test.pdf", {})
        job = store._jobs["job-6"]
        job.expires_at = datetime.utcnow() - timedelta(minutes=1)
        assert store.get("job-6") is None

    def test_cleanup_removes_expired(self, store):
        store.create("job-7", "test.pdf", "/tmp/test.pdf", {})
        store.create("job-8", "test.pdf", "/tmp/test.pdf", {})
        store._jobs["job-7"].expires_at = datetime.utcnow() - timedelta(minutes=1)
        removed = store.cleanup_expired()
        assert removed >= 1
        assert store.get("job-8") is not None

    def test_changes_summary_aggregates_by_type(self, store):
        store.create("job-9", "test.pdf", "/tmp/test.pdf", {})
        after_score = AccessibilityScore(
            overall=80, pdfua1_compliant=True, wcag21_aa_compliant=True
        )
        before_score = AccessibilityScore(
            overall=20, pdfua1_compliant=False, wcag21_aa_compliant=False
        )
        store.complete(
            job_id="job-9",
            accessible_pdf_path="/tmp/job-9/accessible.pdf",
            before_score=before_score,
            after_score=after_score,
            changes=[
                BlockChange("b1", 1, "alt_text_added", "1.1.1"),
                BlockChange("b2", 1, "alt_text_added", "1.1.1"),
                BlockChange("b3", 2, "heading_tagged", "1.3.1"),
            ],
            remaining_issues=[],
            page_count=5,
            model_used="test",
        )
        job = store.get("job-9")
        summary = job.result["changes_summary"]
        assert summary["alt_text_added"] == 2
        assert summary["heading_tagged"] == 1
