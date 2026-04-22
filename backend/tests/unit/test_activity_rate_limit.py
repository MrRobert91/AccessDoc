from unittest.mock import patch

from app.services.job_store import job_store
from app.services.observability.activity_logger import ActivityLogger


def _make_job(job_id: str) -> None:
    job_store._jobs.pop(job_id, None)
    job_store.create(
        job_id=job_id,
        original_filename="rl.pdf",
        original_path="/tmp/rl.pdf",
        options={},
    )


def test_info_events_rate_limited_when_limit_is_one():
    _make_job("rl-1")
    logger = ActivityLogger()
    with patch("app.services.observability.activity_logger.settings") as s:
        s.activity_rate_limit_per_sec = 1
        s.activity_buffer_max = 2000
        first = logger.emit("rl-1", "analyze", "x", "first")
        second = logger.emit("rl-1", "analyze", "x", "second")
        third = logger.emit("rl-1", "analyze", "x", "third")
    assert first is not None
    assert second is None
    assert third is None
    job_store._jobs.pop("rl-1", None)


def test_warn_events_bypass_rate_limit():
    _make_job("rl-2")
    logger = ActivityLogger()
    with patch("app.services.observability.activity_logger.settings") as s:
        s.activity_rate_limit_per_sec = 1
        s.activity_buffer_max = 2000
        logger.emit("rl-2", "analyze", "x", "first")
        dropped_info = logger.emit("rl-2", "analyze", "x", "dropped")
        warn_event = logger.emit("rl-2", "analyze", "bad", "boom", level="warn")
    assert dropped_info is None
    assert warn_event is not None
    assert warn_event.level == "warn"
    job_store._jobs.pop("rl-2", None)


def test_zero_rate_limit_disables_throttling():
    _make_job("rl-3")
    logger = ActivityLogger()
    with patch("app.services.observability.activity_logger.settings") as s:
        s.activity_rate_limit_per_sec = 0
        s.activity_buffer_max = 2000
        a = logger.emit("rl-3", "analyze", "x", "a")
        b = logger.emit("rl-3", "analyze", "x", "b")
        c = logger.emit("rl-3", "analyze", "x", "c")
    assert a and b and c
    job_store._jobs.pop("rl-3", None)
