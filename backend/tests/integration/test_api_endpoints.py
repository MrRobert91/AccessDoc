import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "dependencies" in data


@pytest.mark.asyncio
async def test_create_job_rejects_non_pdf():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/v1/jobs",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["error_code"] == "INVALID_FILE_TYPE"


@pytest.mark.asyncio
async def test_get_nonexistent_job_result():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/result")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_nonexistent_job():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/does-not-exist/download")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sse_progress_nonexistent_job():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/does-not-exist/progress")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_job_returns_job_id_and_sse_url(tmp_path, monkeypatch):
    # Patch pipeline so the background task is a no-op during this test
    from app.routers import jobs as jobs_router

    async def noop_run(job_id: str):
        return None
    monkeypatch.setattr(jobs_router.pipeline, "run", noop_run)

    minimal_pdf = b"%PDF-1.4\n" + b"0" * 500 + b"\n%%EOF"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/v1/jobs",
            files={"file": ("test.pdf", minimal_pdf, "application/pdf")},
        )
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["sse_url"].startswith("/api/v1/jobs/")
    assert data["sse_url"].endswith("/progress")


@pytest.mark.asyncio
async def test_job_result_returns_completed_payload(monkeypatch, tmp_path):
    """End-to-end: create job, manually mark completed, then fetch result."""
    from app.services.job_store import job_store
    from app.models.accessibility import AccessibilityScore, BlockChange

    job = job_store.create(
        "job-result-test",
        "sample.pdf",
        str(tmp_path / "sample.pdf"),
        {},
    )
    before = AccessibilityScore(overall=20, pdfua1_compliant=False, wcag21_aa_compliant=False)
    after = AccessibilityScore(overall=91, pdfua1_compliant=True, wcag21_aa_compliant=True)
    job_store.complete(
        job_id="job-result-test",
        accessible_pdf_path=str(tmp_path / "accessible.pdf"),
        before_score=before,
        after_score=after,
        changes=[BlockChange("b0", 1, "heading_tagged", "1.3.1")],
        remaining_issues=[],
        page_count=3,
        model_used="google/gemma-4-31b-it:free",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/job-result-test/result")
    assert r.status_code == 200
    data = r.json()
    assert data["after_score"]["overall"] == 91
    assert data["page_count"] == 3
    assert data["download_url"].endswith("/download")
