"""Single bounded background worker for data jobs (one job at a time per app process).

* Per-provider rate limits (fixed minimum interval between calls to the same provider).
* Exponential backoff honouring Retry-After on HTTP 429 / 5xx / network errors, max 4 attempts;
  a game that keeps failing is skipped (and retried by the next run), never fatal.
* Cancel stops before the next request; everything fetched so far is already saved.
* Progress, counters, ETA (measured seconds per item) and a short rolling log for the UI.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeVar

import httpx

from app.db.connection import utc_now
from app.logging_config import get_logger
from app.providers.steam_store import StoreError

log = get_logger("jobs")
MAX_ATTEMPTS = 4
MAX_BACKOFF_SECONDS = 300.0
T = TypeVar("T")

JobState = Literal["idle", "running", "completed", "cancelled", "failed"]


@dataclass
class JobStatus:
    job_id: str = ""
    kind: str = ""
    label: str = ""
    state: JobState = "idle"
    total: int = 0
    done: int = 0
    counters: dict[str, int] = field(default_factory=dict[str, int])
    requests: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""
    recent: deque[str] = field(default_factory=lambda: deque[str](maxlen=30))
    _started_monotonic: float = 0.0

    def eta_seconds(self) -> float | None:
        if self.state != "running" or self.done <= 0 or self.total <= self.done:
            return None
        elapsed = time.monotonic() - self._started_monotonic
        return elapsed / self.done * (self.total - self.done)


class JobFailed(RuntimeError):
    """Raised by a task to end the job as failed with a user-readable message."""


class JobContext:
    """Handed to a job's task function: rate-limited calls, progress and logging."""

    def __init__(
        self,
        status: JobStatus,
        client: httpx.Client,
        intervals: Mapping[str, float],
        cancel_event: threading.Event,
        sleep: Callable[[float], None],
    ) -> None:
        self.status = status
        self.client = client
        self._intervals = intervals
        self._last_call: dict[str, float] = {}
        self._cancel = cancel_event
        self._sleep = sleep

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel

    def log(self, line: str) -> None:
        self.status.recent.append(f"{utc_now()[11:19]} {line}")

    def count(self, key: str, n: int = 1) -> None:
        self.status.counters[key] = self.status.counters.get(key, 0) + n

    def set_total(self, total: int) -> None:
        self.status.total = total

    def advance(self, n: int = 1) -> None:
        self.status.done += n

    def _wait_turn(self, provider: str) -> None:
        interval = self._intervals.get(provider, 1.0)
        last = self._last_call.get(provider)
        if last is not None:
            remaining = interval - (time.monotonic() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_call[provider] = time.monotonic()

    def call(self, provider: str, what: str, fn: Callable[[httpx.Client], T]) -> T | None:
        """Run ``fn`` with rate limiting and retries. Returns None when the call gave up."""
        delay = max(self._intervals.get(provider, 1.0), 2.0)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if self.cancelled:
                return None
            self._wait_turn(provider)
            self.status.requests += 1
            try:
                return fn(self.client)
            except StoreError as exc:
                if not exc.retryable or attempt == MAX_ATTEMPTS:
                    self.count("errors")
                    self.log(f"{what}: {exc} - skipped (retried next run)")
                    return None
                wait = min(exc.retry_after or delay, MAX_BACKOFF_SECONDS)
                self.count("retries")
                self.log(f"{what}: {exc} - retrying in {wait:.0f}s")
                self._sleep(wait)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
        return None


Task = Callable[[JobContext], str]  # returns a short completion message


class JobRunner:
    def __init__(
        self,
        client_factory: Callable[[], httpx.Client],
        intervals: Mapping[str, float],
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.intervals = dict(intervals)
        self.status = JobStatus()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._sleep: Callable[[float], None] = sleep or self._interruptible_sleep

    def _interruptible_sleep(self, seconds: float) -> None:
        self._cancel.wait(seconds)  # returns early when cancelled

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, kind: str, label: str, task: Task) -> bool:
        with self._lock:
            if self.running:
                return False
            self._cancel.clear()
            self.status = JobStatus(
                job_id=uuid.uuid4().hex[:10],
                kind=kind,
                label=label,
                state="running",
                started_at=utc_now(),
                _started_monotonic=time.monotonic(),
            )
            self._thread = threading.Thread(
                target=self._run, args=(task, self.status), name=f"job-{kind}", daemon=True
            )
            self._thread.start()
            return True

    def cancel(self) -> None:
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self, task: Task, status: JobStatus) -> None:
        try:
            with self.client_factory() as client:
                ctx = JobContext(status, client, self.intervals, self._cancel, self._sleep)
                message = task(ctx)
            if self._cancel.is_set():
                status.state = "cancelled"
                status.message = "Stopped. Start again to continue where it left off."
            else:
                status.state = "completed"
                status.message = message
        except JobFailed as exc:
            status.state = "cancelled" if self._cancel.is_set() else "failed"
            status.message = "Stopped." if self._cancel.is_set() else str(exc)
        except Exception as exc:  # never let the worker die silently
            log.exception("job failed", extra={"kind": status.kind})
            status.state = "failed"
            status.message = f"Stopped by an unexpected error: {exc}"
        finally:
            status.finished_at = utc_now()
            log.info(
                "job ended",
                extra={"kind": status.kind, "state": status.state, "done": status.done,
                       "requests": status.requests, "counters": dict(status.counters)},
            )  # fmt: skip
