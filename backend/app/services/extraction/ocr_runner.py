import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger()


@dataclass
class OCRResult:
    ok: bool
    output_path: str | None = None
    duration_ms: int = 0
    engine: str = "tesseract"
    language: str = "spa+eng"
    error: str | None = None
    stdout: str | None = None


class OCRRunner:
    """
    Runs ocrmypdf against a scanned PDF, producing a copy with a hidden text
    layer. Falls back silently (ok=False) when the binary is missing or the
    process returns non-zero — the pipeline continues with the untouched PDF.
    """

    DEFAULT_LANGS = "spa+eng"
    DEFAULT_TIMEOUT_SEC = 180

    def __init__(
        self,
        binary: str = "ocrmypdf",
        languages: str | None = None,
        timeout_sec: int | None = None,
    ):
        self.binary = binary
        self.languages = languages or self.DEFAULT_LANGS
        self.timeout_sec = timeout_sec or self.DEFAULT_TIMEOUT_SEC

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def run(self, input_pdf: str, output_pdf: str) -> OCRResult:
        if not self.available():
            return OCRResult(
                ok=False,
                error=f"{self.binary} not installed",
                language=self.languages,
            )

        Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.binary,
            "--skip-text",
            "--optimize", "0",
            "--language", self.languages,
            "--quiet",
            input_pdf,
            output_pdf,
        ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except FileNotFoundError as e:
            return OCRResult(ok=False, error=str(e), language=self.languages)
        except subprocess.TimeoutExpired as e:
            return OCRResult(
                ok=False,
                error=f"ocrmypdf timeout after {self.timeout_sec}s",
                language=self.languages,
                duration_ms=int((time.monotonic() - t0) * 1000),
                stdout=(e.stdout or "")[-500:] if isinstance(e.stdout, str) else None,
            )

        duration_ms = int((time.monotonic() - t0) * 1000)

        if proc.returncode != 0:
            log.warning(
                "ocrmypdf_failed",
                returncode=proc.returncode,
                stderr=(proc.stderr or "")[-500:],
            )
            return OCRResult(
                ok=False,
                duration_ms=duration_ms,
                language=self.languages,
                error=(proc.stderr or "").strip()[-300:] or f"exit {proc.returncode}",
                stdout=(proc.stdout or "")[-500:],
            )

        return OCRResult(
            ok=True,
            output_path=output_pdf,
            duration_ms=duration_ms,
            language=self.languages,
            stdout=(proc.stdout or "")[-500:],
        )
