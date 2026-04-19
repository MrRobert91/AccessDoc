from pydantic import BaseModel
from typing import Optional


class ProcessingOptions(BaseModel):
    language_override: Optional[str] = None
    ocr_enabled: bool = True
    model_size: str = "accurate"
    retry_on_low_score: bool = True
