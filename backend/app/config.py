from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    gemma_model_accurate: str = "google/gemma-4-31b-it:free"
    gemma_model_fast: str = "google/gemma-4-26b-a4b-it:free"
    max_file_size_mb: int = 50
    job_ttl_hours: int = 1
    max_concurrent_jobs: int = 5
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    verapdf_path: str = "verapdf"
    tmp_dir: str = "/tmp/accessdoc"

    enable_mcid_tagging: bool = True
    enable_ocr: bool = True
    enable_annotations_tagging: bool = False
    enable_form_tagging: bool = False
    activity_buffer_max: int = 2000
    activity_rate_limit_per_sec: int = 50

    model_config = {"env_file": ".env"}


settings = Settings()
