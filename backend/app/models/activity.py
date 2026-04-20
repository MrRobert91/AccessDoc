from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


VALID_PHASES = {
    "extract", "ocr", "analyze", "tag",
    "write", "validate", "retry", "report",
}
VALID_LEVELS = {"info", "warn", "error"}


@dataclass
class ActivityEvent:
    """
    A single granular action emitted by the pipeline.

    seq is monotonic per job and serves as the SSE `id` so the client can
    reconnect with `Last-Event-ID` and resume without gaps.
    """

    seq: int
    job_id: str
    phase: str
    code: str
    message: str
    level: str = "info"
    page: Optional[int] = None
    duration_ms: Optional[int] = None
    details: Optional[dict] = None
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "job_id": self.job_id,
            "phase": self.phase,
            "code": self.code,
            "message": self.message,
            "level": self.level,
            "page": self.page,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "ts": self.ts,
        }
