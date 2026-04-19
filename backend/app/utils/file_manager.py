import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from app.config import settings

log = structlog.get_logger()


class FileManager:
    async def cleanup_loop(self) -> None:
        """Background task: remove expired job directories every 10 minutes."""
        while True:
            try:
                await asyncio.sleep(600)
                self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("cleanup_error", error=str(e))

    def cleanup_expired(self) -> int:
        tmp = Path(settings.tmp_dir)
        if not tmp.exists():
            return 0

        cutoff = datetime.utcnow() - timedelta(hours=settings.job_ttl_hours)
        removed = 0
        for job_dir in tmp.iterdir():
            if not job_dir.is_dir():
                continue
            mtime = datetime.utcfromtimestamp(job_dir.stat().st_mtime)
            if mtime < cutoff:
                try:
                    shutil.rmtree(job_dir)
                    removed += 1
                except Exception as e:
                    log.warning("cleanup_failed", dir=str(job_dir), error=str(e))
        if removed:
            log.info("cleanup_complete", removed=removed)
        return removed


file_manager = FileManager()
