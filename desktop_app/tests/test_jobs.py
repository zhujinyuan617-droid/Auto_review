import time

from autoreview_app.jobs import JobRegistry


def _wait(reg, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = reg.get(job_id)["status"]
        if status in {"succeeded", "failed"}:
            return reg.get(job_id)
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def test_successful_job_reports_result():
    reg = JobRegistry()
    job_id = reg.submit(lambda report: report("hi") or 42)
    final = _wait(reg, job_id)
    assert final["status"] == "succeeded"
    assert final["result"] == 42
    assert "hi" in final["progress"]


def test_failed_job_reports_error():
    reg = JobRegistry()

    def boom(report):
        raise ValueError("nope")

    job_id = reg.submit(boom)
    final = _wait(reg, job_id)
    assert final["status"] == "failed"
    assert "nope" in final["error"]


def test_unknown_job_is_none():
    assert JobRegistry().get("missing") is None
