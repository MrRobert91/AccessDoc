import asyncio

import pytest

from app.services.job_store import job_store
from app.services.observability.activity_logger import ActivityLogger, activity


@pytest.fixture
def fresh_job():
    job = job_store.create(
        job_id="activity-test-job",
        original_filename="f.pdf",
        original_path="/tmp/f.pdf",
        options={},
    )
    yield job
    # cleanup
    job_store._jobs.pop("activity-test-job", None)


def test_emit_assigns_monotonic_seq(fresh_job):
    logger = ActivityLogger()
    e1 = logger.emit("activity-test-job", "extract", "code_a", "hello")
    e2 = logger.emit("activity-test-job", "analyze", "code_b", "world")
    assert e1 is not None and e2 is not None
    assert e1.seq == 0
    assert e2.seq == 1
    assert fresh_job.activity_cursor == 2
    assert len(fresh_job.activity) == 2


def test_emit_on_missing_job_returns_none():
    logger = ActivityLogger()
    result = logger.emit("ghost-job", "extract", "x", "none")
    assert result is None


def test_buffer_cap_drops_oldest(monkeypatch, fresh_job):
    from app.config import settings
    monkeypatch.setattr(settings, "activity_buffer_max", 5)
    logger = ActivityLogger()
    for i in range(10):
        logger.emit("activity-test-job", "extract", f"c{i}", "msg")
    assert len(fresh_job.activity) == 5
    # the last 5 codes kept
    assert [e.code for e in fresh_job.activity] == [f"c{i}" for i in range(5, 10)]


def test_events_since_returns_only_newer(fresh_job):
    logger = ActivityLogger()
    logger.emit("activity-test-job", "extract", "a", "1")
    logger.emit("activity-test-job", "extract", "b", "2")
    logger.emit("activity-test-job", "extract", "c", "3")
    later = logger.events_since("activity-test-job", since_seq=0)
    assert [e.code for e in later] == ["b", "c"]


def test_invalid_level_is_normalized(fresh_job):
    logger = ActivityLogger()
    e = logger.emit("activity-test-job", "extract", "x", "m", level="bogus")
    assert e is not None
    assert e.level == "info"


@pytest.mark.asyncio
async def test_subscriber_receives_emitted_event(fresh_job):
    logger = ActivityLogger()
    q = logger.subscribe("activity-test-job")
    try:
        logger.emit("activity-test-job", "extract", "hi", "there")
        ev = await asyncio.wait_for(q.get(), timeout=0.5)
        assert ev.code == "hi"
        assert ev.message == "there"
    finally:
        logger.unsubscribe("activity-test-job", q)
