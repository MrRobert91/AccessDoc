import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.services.job_store import job_store
from app.services.reporting.report_builder import report_builder

router = APIRouter(tags=["Downloads"])


@router.get("/jobs/{job_id}/download")
async def download_accessible_pdf(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, detail={
            "error_code": "JOB_NOT_FOUND",
            "message": f"Job {job_id} not found",
            "timestamp": _now(),
        })
    if job.status != "completed" or not job.accessible_pdf_path:
        raise HTTPException(409, detail={
            "error_code": "JOB_NOT_READY",
            "message": "El job todavía no está completo",
            "timestamp": _now(),
        })

    path = Path(job.accessible_pdf_path)
    if not path.exists():
        raise HTTPException(410, detail={
            "error_code": "FILE_EXPIRED",
            "message": "El archivo accesible ya no está disponible",
            "timestamp": _now(),
        })

    score = 0
    if job.result and job.result.get("after_score"):
        score = int(job.result["after_score"].get("overall", 0))

    stem = Path(job.original_filename).stem or "document"
    download_name = f"{stem}_accessible.pdf"

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=download_name,
        headers={
            "X-Accessibility-Score": str(score),
            "Cache-Control": "no-store",
        },
    )


@router.get("/jobs/{job_id}/report.json")
async def download_report_json(job_id: str):
    job = _require_completed_job(job_id)
    report = report_builder.build(job)
    stem = Path(job.original_filename).stem or "report"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}_accessibility.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/jobs/{job_id}/report.html")
async def download_report_html(job_id: str):
    job = _require_completed_job(job_id)
    html = report_builder.render_html(job)
    stem = Path(job.original_filename).stem or "report"
    return HTMLResponse(
        content=html,
        headers={
            "Content-Disposition": f'inline; filename="{stem}_accessibility.html"',
            "Cache-Control": "no-store",
        },
    )


def _require_completed_job(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, detail={
            "error_code": "JOB_NOT_FOUND",
            "message": f"Job {job_id} not found",
            "timestamp": _now(),
        })
    if job.status != "completed" or not job.result:
        raise HTTPException(409, detail={
            "error_code": "JOB_NOT_READY",
            "message": "El reporte aún no está disponible",
            "timestamp": _now(),
        })
    return job


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"
