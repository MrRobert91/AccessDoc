from collections import defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models.job import Job
from app.services.observability.explanations import (
    for_change_type,
    issue_hint,
    pdfua_info,
    wcag_info,
)
from app.services.reporting.narrative import build_narrative


TEMPLATES_DIR = Path(__file__).parent / "templates"


class ReportBuilder:
    """
    Assembles the detailed remediation report (FR-R1) by reading the job
    state plus the activity buffer. `build()` returns a JSON-ready dict;
    `render_html()` renders the same payload with a Jinja2 template (FR-R2).

    Each applied change is enriched with a plain-language ``explanation``
    object, each remaining issue with a ``hint`` + expanded criterion, and
    the job gets a top-level ``narrative`` — a chronological, human-readable
    account of what happened during remediation.
    """

    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.globals["pdfua_rules"] = _pdfua_rules
        self._env.globals["change_types"] = _change_types

    def build(self, job: Job) -> dict:
        result = job.result or {}
        raw_changes = result.get("changes_applied", [])
        changes = [_enrich_change(c) for c in raw_changes]

        by_page: dict[int, list[dict]] = defaultdict(list)
        by_criterion: dict[str, list[dict]] = defaultdict(list)
        for change in changes:
            page = change.get("page_num") or change.get("page") or 0
            criterion = change.get("criterion") or "unknown"
            by_page[int(page)].append(change)
            by_criterion[str(criterion)].append(change)

        summary_counts = result.get("changes_summary") or _summarize(changes)
        changes_summary_detailed = _verbose_summary(summary_counts, changes)
        remaining = [
            _enrich_issue(i)
            for i in result.get("remaining_issues", [])
        ]
        activity_log = [self._serialize(e) for e in job.activity]

        glossary = _build_glossary(changes, remaining, activity_log)

        narrative = build_narrative(
            filename=job.original_filename,
            page_count=result.get("page_count", 0),
            before_score=result.get("before_score"),
            after_score=result.get("after_score"),
            changes=changes,
            remaining=remaining,
            activity=activity_log,
            processing_time=result.get("processing_time_seconds"),
        )

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
            "changes_applied": changes,
            "changes_summary": summary_counts,
            "changes_summary_detailed": changes_summary_detailed,
            "remaining_issues": remaining,
            "activity_log": activity_log,
            "narrative": narrative,
            "glossary": glossary,
            "download_url": f"/api/v1/jobs/{job.job_id}/download",
            "report_html_url": f"/api/v1/jobs/{job.job_id}/report.html",
        }

    def render_html(self, job: Job) -> str:
        data = self.build(job)
        before = (data["scores"]["before"] or {}).get("overall", 0) or 0
        after = (data["scores"]["after"] or {}).get("overall", 0) or 0
        context = {
            **data,
            "before_score": before,
            "after_score": after,
            "delta": after - before,
        }
        return self._env.get_template("report.html").render(**context)

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


def _verbose_summary(counts: dict, changes: list[dict]) -> list[dict]:
    """Turn {type: count} into [{type, count, title, why, impact, examples}]."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for c in changes:
        by_type[c.get("change_type", "other")].append(c)

    rows: list[dict] = []
    for change_type, count in counts.items():
        exp = for_change_type(change_type) or {}
        examples = []
        for c in by_type.get(change_type, [])[:3]:
            examples.append({
                "page": c.get("page_num") or c.get("page"),
                "before": c.get("before"),
                "after": c.get("after"),
            })
        rows.append({
            "change_type": change_type,
            "count": count,
            "title": exp.get("title") or _humanize(change_type),
            "what": exp.get("what"),
            "why": exp.get("why"),
            "impact": exp.get("impact"),
            "wcag": exp.get("wcag"),
            "pdfua": exp.get("pdfua"),
            "examples": examples,
        })
    rows.sort(key=lambda r: -r["count"])
    return rows


def _enrich_change(change: dict) -> dict:
    """Attach explanation object to a BlockChange dict, preserving the rest."""
    out = dict(change)
    exp = for_change_type(change.get("change_type", ""))
    if exp:
        out["explanation"] = exp
    return out


def _enrich_issue(issue: dict) -> dict:
    out = dict(issue)
    criterion = issue.get("criterion")
    info = wcag_info(criterion) if criterion else None
    if info:
        out["criterion_name"] = info.get("name")
        out["criterion_level"] = info.get("level")
        out["criterion_plain"] = info.get("plain")
    rule = issue.get("rule") or issue.get("pdfua_rule")
    rule_text = pdfua_info(rule) if rule else None
    if rule_text:
        out["pdfua_plain"] = rule_text
    hint = issue_hint(criterion)
    if hint:
        out["hint"] = hint
    return out


def _build_glossary(
    changes: list[dict],
    remaining: list[dict],
    activity: list[dict],
) -> dict:
    """Deduplicated WCAG + PDF/UA references used in this specific report."""
    wcag_seen: dict[str, dict] = {}
    pdfua_seen: dict[str, str] = {}

    def _scan(criterion: str | None, rule: str | None):
        if criterion and criterion not in wcag_seen:
            info = wcag_info(criterion)
            if info:
                wcag_seen[criterion] = {"code": criterion, **info}
        if rule and rule not in pdfua_seen:
            text = pdfua_info(rule)
            if text:
                pdfua_seen[rule] = text

    for c in changes:
        _scan(c.get("criterion"), c.get("pdfua_rule"))
    for i in remaining:
        _scan(i.get("criterion"), i.get("rule") or i.get("pdfua_rule"))
    for a in activity:
        exp = (a.get("details") or {}).get("explanation") or {}
        _scan(exp.get("wcag"), exp.get("pdfua"))

    return {
        "wcag": sorted(wcag_seen.values(), key=lambda x: x["code"]),
        "pdfua": [{"rule": k, "plain": v} for k, v in sorted(pdfua_seen.items())],
    }


def _humanize(raw: str) -> str:
    return raw.replace("_", " ").capitalize()


def _pdfua_rules(changes: list[dict]) -> str:
    seen: list[str] = []
    for c in changes:
        r = c.get("pdfua_rule")
        if r and r not in seen:
            seen.append(r)
    return ", ".join(seen)


def _change_types(changes: list[dict]) -> str:
    seen: list[str] = []
    for c in changes:
        t = c.get("change_type")
        if t and t not in seen:
            seen.append(t)
    return ", ".join(t.replace("_", " ") for t in seen)


report_builder = ReportBuilder()
