from collections import defaultdict
from dataclasses import asdict, is_dataclass

from app.models.job import Job


class ReportBuilder:
    """
    Assembles the detailed remediation report (FR-R1) by reading the job
    state plus the activity buffer. The result is a single JSON-ready dict.
    """

    def build(self, job: Job) -> dict:
        result = job.result or {}
        changes = result.get("changes_applied", [])

        by_page: dict[int, list[dict]] = defaultdict(list)
        by_criterion: dict[str, list[dict]] = defaultdict(list)
        for change in changes:
            page = change.get("page_num") or change.get("page") or 0
            criterion = change.get("criterion") or "unknown"
            by_page[int(page)].append(change)
            by_criterion[str(criterion)].append(change)

        changes_summary = result.get("changes_summary") or _summarize(changes)
        activity_log = [self._serialize(e) for e in job.activity]

        return {
            "job_id": job.job_id,
            "filename": job.original_filename,
            "status": job.status,
            "processed_at": result.get("processed_at"),
            "processing_time_seconds": result.get("processing_time_seconds"),
            "page_count": result.get("page_count", 0),
            "model_used": result.get("model_used"),
            "scores": {
                "before": result.get("before_score"),
                "after": result.get("after_score"),
            },
            "changes_by_page": {
                str(k): v for k, v in sorted(by_page.items())
            },
            "changes_by_criterion": dict(by_criterion),
            "changes_summary": changes_summary,
            "remaining_issues": result.get("remaining_issues", []),
            "activity_log": activity_log,
            "download_url": f"/api/v1/jobs/{job.job_id}/download",
            "report_html_url": f"/api/v1/jobs/{job.job_id}/report.html",
        }

    @staticmethod
    def _serialize(obj) -> dict:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, dict):
            return obj
        return {"value": str(obj)}


def _summarize(changes: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for c in changes:
        t = c.get("change_type", "other")
        summary[t] = summary.get(t, 0) + 1
    return summary


report_builder = ReportBuilder()
