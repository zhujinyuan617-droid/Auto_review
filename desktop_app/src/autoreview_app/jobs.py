from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

# A job is a callable taking one arg: report(msg) to append a progress line.
Job = Callable[[Callable[[str], None]], Any]


class JobRegistry:
    """Runs jobs on background threads and tracks status/progress/result/error."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, job: Job) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {"status": "running", "progress": [], "result": None, "error": None}
        thread = threading.Thread(target=self._run, args=(job_id, job), daemon=True)
        thread.start()
        return job_id

    def _run(self, job_id: str, job: Job) -> None:
        def report(message: str) -> None:
            with self._lock:
                self._jobs[job_id]["progress"].append(message)

        try:
            result = job(report)
            with self._lock:
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["status"] = "succeeded"
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller via status
            with self._lock:
                self._jobs[job_id]["error"] = f"{type(exc).__name__}: {exc}"
                self._jobs[job_id]["status"] = "failed"

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None
