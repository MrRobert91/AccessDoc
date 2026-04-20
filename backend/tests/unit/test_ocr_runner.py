from unittest.mock import patch, MagicMock
import subprocess

from app.services.extraction.ocr_runner import OCRRunner


def test_available_reports_false_when_binary_missing():
    runner = OCRRunner(binary="nonexistent_binary_xxx_for_test")
    assert runner.available() is False


def test_run_returns_error_when_not_available(tmp_path):
    runner = OCRRunner(binary="nonexistent_binary_xxx_for_test")
    out = tmp_path / "out.pdf"
    result = runner.run(str(tmp_path / "in.pdf"), str(out))
    assert result.ok is False
    assert "not installed" in (result.error or "")


def test_run_ok_on_zero_exit(tmp_path):
    runner = OCRRunner()
    in_pdf = tmp_path / "in.pdf"
    in_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    out_pdf = tmp_path / "out.pdf"
    fake_proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch(
        "app.services.extraction.ocr_runner.shutil.which",
        return_value="/usr/bin/ocrmypdf",
    ), patch(
        "app.services.extraction.ocr_runner.subprocess.run",
        return_value=fake_proc,
    ):
        result = runner.run(str(in_pdf), str(out_pdf))
    assert result.ok is True
    assert result.output_path == str(out_pdf)


def test_run_fails_on_non_zero_exit(tmp_path):
    runner = OCRRunner()
    in_pdf = tmp_path / "in.pdf"
    in_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    out_pdf = tmp_path / "out.pdf"
    fake_proc = MagicMock(returncode=2, stdout="", stderr="some tesseract error")
    with patch(
        "app.services.extraction.ocr_runner.shutil.which",
        return_value="/usr/bin/ocrmypdf",
    ), patch(
        "app.services.extraction.ocr_runner.subprocess.run",
        return_value=fake_proc,
    ):
        result = runner.run(str(in_pdf), str(out_pdf))
    assert result.ok is False
    assert "tesseract" in (result.error or "")


def test_run_handles_timeout(tmp_path):
    runner = OCRRunner(timeout_sec=1)
    in_pdf = tmp_path / "in.pdf"
    in_pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    out_pdf = tmp_path / "out.pdf"
    with patch(
        "app.services.extraction.ocr_runner.shutil.which",
        return_value="/usr/bin/ocrmypdf",
    ), patch(
        "app.services.extraction.ocr_runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=1),
    ):
        result = runner.run(str(in_pdf), str(out_pdf))
    assert result.ok is False
    assert "timeout" in (result.error or "").lower()
