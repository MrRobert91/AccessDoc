import shutil

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    verapdf_ok = bool(shutil.which(settings.verapdf_path))
    try:
        stat = shutil.disk_usage(settings.tmp_dir)
        disk_mb = stat.free // (1024 * 1024)
    except Exception:
        disk_mb = 0

    openrouter_ok = bool(settings.openrouter_api_key)

    status = "healthy"
    if not openrouter_ok:
        status = "degraded"
    if not verapdf_ok:
        status = "degraded"
    if disk_mb < 100:
        status = "degraded"

    return {
        "status": status,
        "version": "1.0.0",
        "dependencies": {
            "openrouter": "up" if openrouter_ok else "down",
            "verapdf": "up" if verapdf_ok else "down",
            "disk_space_mb": disk_mb,
        },
    }
