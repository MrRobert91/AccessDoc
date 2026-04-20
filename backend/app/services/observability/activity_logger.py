import asyncio
import threading
from typing import Optional

import structlog

from app.config import settings
from app.models.activity import ActivityEvent, VALID_LEVELS, VALID_PHASES
from app.services.job_store import job_store

log = structlog.get_logger()


class ActivityLogger:
    """
    Central publisher for granular pipeline activity events.

    emit() is callable from sync or async context. Each event is:
      1. appended to the Job's activity buffer (capped)
      2. pushed to every live SSE subscriber queue for that job
    """

    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.Lock()
        self._loops: dict[str, asyncio.AbstractEventLoop] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock:
            self._subs.setdefault(job_id, []).append(q)
            try:
                self._loops[job_id] = asyncio.get_event_loop()
            except RuntimeError:
                pass
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            if job_id in self._subs:
                self._subs[job_id] = [s for s in self._subs[job_id] if s is not q]
                if not self._subs[job_id]:
                    del self._subs[job_id]
                    self._loops.pop(job_id, None)

    def emit(
        self,
        job_id: str,
        phase: str,
        code: str,
        message: str,
        level: str = "info",
        page: Optional[int] = None,
        duration_ms: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> Optional[ActivityEvent]:
        if phase not in VALID_PHASES:
            log.warning("activity_invalid_phase", phase=phase, code=code)
        if level not in VALID_LEVELS:
            level = "info"

        job = job_store.get(job_id)
        if not job:
            return None

        with self._lock:
            seq = job.activity_cursor
            job.activity_cursor = seq + 1
            event = ActivityEvent(
                seq=seq,
                job_id=job_id,
                phase=phase,
                code=code,
                message=message,
                level=level,
                page=page,
                duration_ms=duration_ms,
                details=details,
            )
            job.activity.append(event)
            cap = settings.activity_buffer_max
            if len(job.activity) > cap:
                dropped = len(job.activity) - cap
                job.activity = job.activity[dropped:]

            subs = list(self._subs.get(job_id, []))
            loop = self._loops.get(job_id)

        log.info(
            "activity",
            job_id=job_id, phase=phase, code=code,
            level=level, page=page, seq=seq,
        )

        for q in subs:
            self._push(q, event, level, loop)

        return event

    def events_since(self, job_id: str, since_seq: int) -> list[ActivityEvent]:
        job = job_store.get(job_id)
        if not job:
            return []
        return [e for e in job.activity if e.seq > since_seq]

    def _push(
        self,
        q: asyncio.Queue,
        event: ActivityEvent,
        level: str,
        loop: Optional[asyncio.AbstractEventLoop],
    ) -> None:
        try:
            q.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        if level in ("warn", "error"):
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                log.warning("activity_queue_drop", job_id=event.job_id, code=event.code)


activity = ActivityLogger()
