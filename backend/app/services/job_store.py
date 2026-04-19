import threading
from datetime import datetime
from typing import Optional

from app.models.job import Job
from app.models.accessibility import AccessibilityScore, BlockChange, RemainingIssue


class JobStore:
    """Thread-safe in-memory job store with TTL cleanup."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(
        self,
        job_id: str,
        original_filename: str,
        original_path: str,
        options: dict,
    ) -> Job:
        job = Job(
            job_id=job_id,
            original_filename=original_filename,
            original_path=original_path,
            options=options,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.is_expired:
                del self._jobs[job_id]
                return None
            return job

    def exists(self, job_id: str) -> bool:
        return self.get(job_id) is not None

    def update_progress(
        self,
        job_id: str,
        pct: int,
        status: str,
        step: str,
        pages_processed: Optional[int] = None,
        pages_total: Optional[int] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress.status = status
            job.progress.progress_pct = pct
            job.progress.current_step = step
            if pages_processed is not None:
                job.progress.pages_processed = pages_processed
            if pages_total is not None:
                job.progress.pages_total = pages_total
            job.progress.updated_at = datetime.utcnow()

    def complete(
        self,
        job_id: str,
        accessible_pdf_path: str,
        before_score: AccessibilityScore,
        after_score: AccessibilityScore,
        changes: list[BlockChange],
        remaining_issues: list[RemainingIssue],
        page_count: int,
        model_used: str,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.accessible_pdf_path = accessible_pdf_path
            job.progress.status = "completed"
            job.progress.progress_pct = 100
            job.progress.current_step = "Completado"
            job.result = {
                "job_id": job_id,
                "status": "completed",
                "original_filename": job.original_filename,
                "page_count": page_count,
                "before_score": before_score.__dict__,
                "after_score": after_score.__dict__,
                "changes_applied": [c.__dict__ for c in changes],
                "changes_summary": _summarize_changes(changes),
                "remaining_issues": [r.__dict__ for r in remaining_issues],
                "download_url": f"/api/v1/jobs/{job_id}/download",
                "report_url": f"/api/v1/jobs/{job_id}/report",
                "processed_at": datetime.utcnow().isoformat(),
                "processing_time_seconds": (
                    datetime.utcnow() - job.created_at
                ).total_seconds(),
                "model_used": model_used,
            }

    def fail(self, job_id: str, error_code: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress.status = "failed"
            job.progress.current_step = message
            job.error_code = error_code
            job.error_message = message

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [jid for jid, j in self._jobs.items() if j.is_expired]
            for jid in expired:
                del self._jobs[jid]
            return len(expired)


def _summarize_changes(changes: list[BlockChange]) -> dict:
    summary: dict[str, int] = {}
    for c in changes:
        summary[c.change_type] = summary.get(c.change_type, 0) + 1
    return summary


job_store = JobStore()
