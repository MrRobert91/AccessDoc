from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from app.config import settings


@dataclass
class JobProgress:
    status: str = "pending"
    progress_pct: int = 0
    current_step: str = "Iniciando..."
    pages_processed: Optional[int] = None
    pages_total: Optional[int] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Job:
    job_id: str
    original_filename: str
    original_path: str
    options: dict
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(
        default_factory=lambda: datetime.utcnow() + timedelta(hours=settings.job_ttl_hours)
    )
    progress: JobProgress = field(default_factory=JobProgress)
    result: Optional[dict] = None
    accessible_pdf_path: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def status(self) -> str:
        return self.progress.status

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
