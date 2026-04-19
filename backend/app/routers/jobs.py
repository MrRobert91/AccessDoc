import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.services.job_store import job_store
from app.services.pipeline import AccessibilityPipeline

router = APIRouter(tags=["Jobs"])
pipeline = AccessibilityPipeline()


@router.post("/jobs", status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    options: str = Form(default="{}"),
):
    content_type = file.content_type or ""
    filename = file.filename or "document.pdf"
    if not (filename.lower().endswith(".pdf") or "pdf" in content_type):
        raise HTTPException(400, detail={
            "error_code": "INVALID_FILE_TYPE",
            "message": "Solo se aceptan archivos PDF",
            "timestamp": _now(),
        })

    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(400, detail={
            "error_code": "FILE_TOO_LARGE",
            "message": f"El archivo supera el límite de {settings.max_file_size_mb}MB",
            "timestamp": _now(),
        })
    if len(content) < 10:
        raise HTTPException(400, detail={
            "error_code": "CORRUPTED_PDF",
            "message": "El archivo parece estar vacío o corrupto",
            "timestamp": _now(),
        })

    try:
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError:
        opts = {}

    job_id = str(uuid.uuid4())
    job_dir = Path(settings.tmp_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    original_path = job_dir / "original.pdf"
    original_path.write_bytes(content)

    job = job_store.create(
        job_id=job_id,
        original_filename=filename,
        original_path=str(original_path),
        options=opts,
    )

    background_tasks.add_task(pipeline.run, job_id)

    return {
        "job_id": job_id,
        "status": "pending",
        "estimated_seconds": _estimate_seconds(len(content)),
        "sse_url": f"/api/v1/jobs/{job_id}/progress",
        "expires_at": job.expires_at.isoformat(),
    }


@router.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str):
    if not job_store.exists(job_id):
        raise HTTPException(404, detail={
            "error_code": "JOB_NOT_FOUND",
            "message": f"Job {job_id} not found",
            "timestamp": _now(),
        })

    async def event_stream():
        last_pct = -1
        while True:
            job = job_store.get(job_id)
            if not job:
                yield _sse("failed", {
                    "job_id": job_id,
                    "error_code": "JOB_EXPIRED",
                    "message": "El job ha expirado",
                })
                break

            if job.progress.progress_pct != last_pct:
                last_pct = job.progress.progress_pct
                yield _sse("progress", {
                    "job_id": job_id,
                    "status": job.status,
                    "progress_pct": job.progress.progress_pct,
                    "current_step": job.progress.current_step,
                    "pages_processed": job.progress.pages_processed,
                    "pages_total": job.progress.pages_total,
                    "timestamp": job.progress.updated_at.isoformat(),
                })

            if job.status == "completed":
                yield _sse("completed", {
                    "job_id": job_id,
                    "result_url": f"/api/v1/jobs/{job_id}/result",
                })
                break

            if job.status == "failed":
                yield _sse("failed", {
                    "job_id": job_id,
                    "error_code": job.error_code or "INTERNAL_ERROR",
                    "message": job.error_message or "Error interno",
                })
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(404, detail={
            "error_code": "JOB_NOT_FOUND",
            "message": "Job not found",
            "timestamp": _now(),
        })
    if job.status == "failed":
        raise HTTPException(500, detail={
            "error_code": job.error_code or "INTERNAL_ERROR",
            "message": job.error_message or "Job failed",
            "timestamp": _now(),
        })
    if job.status != "completed" or not job.result:
        raise HTTPException(202, detail={"message": "Job still in progress"})
    return job.result


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _estimate_seconds(file_bytes: int) -> int:
    return max(15, int(file_bytes / (1024 * 1024) * 8) + 10)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"
