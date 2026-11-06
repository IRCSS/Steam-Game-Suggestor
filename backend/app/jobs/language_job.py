"""Background job: look up supported languages for a set of AppIDs (user-started from Settings).

* Single bounded worker thread; one job at a time per app process.
* Polite fixed rate (settings: steam.store_requests_per_minute, default 35/min) plus exponential
  backoff with Retry-After on HTTP 429 / 5xx / network errors (max 4 attempts per game).
* Resumable: AppIDs already present in the shared cache (from any PC) are skipped, and the
  cache is re-read periodically so several PCs running the job do not repeat each other's work.
* Results are appended to this PC's cache shard immediately; cancel stops before the next call.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import httpx

from app.db.connection import utc_now
from app.logging_config import get_logger
from app.providers.steam_store import StoreError, fetch_languages
from app.storage.language_cache import LanguageCache

log = get_logger("language_job")
MAX_ATTEMPTS = 4
MAX_BACKOFF_SECONDS = 300.0
REFRESH_EVERY = 100

JobState = Literal["idle", "running", "completed", "cancelled", "failed"]


@dataclass
class JobStatus:
    state: JobState = "idle"
    scope: str = ""
    total: int = 0
    done: int = 0
    found: int = 0
    unavailable: int = 0
    errors: int = 0
    skipped: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""
    recent: deque[str] = field(default_factory=lambda: deque[str](maxlen=20))


class LanguageJob:
    def __init__(
        self,
        cache: LanguageCache,
        client_factory: Callable[[], httpx.Client],
        requests_per_minute: int,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.cache = cache
        self.client_factory = client_factory
        self.interval = 60.0 / max(1, requests_per_minute)
        self.status = JobStatus()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._sleep: Callable[[float], None] = sleep or self._interruptible_sleep

    def _interruptible_sleep(self, seconds: float) -> None:
        self._cancel.wait(seconds)  # returns early when the job is cancelled

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, appids: Sequence[int], scope: str) -> bool:
        with self._lock:
            if self.running:
                return False
            self._cancel.clear()
            self.status = JobStatus(state="running", scope=scope, started_at=utc_now())
            self._thread = threading.Thread(
                target=self._run, args=(list(appids),), name="language-job", daemon=True
            )
            self._thread.start()
            return True

    def cancel(self) -> None:
        self._cancel.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _log(self, line: str) -> None:
        self.status.recent.append(f"{utc_now()} {line}")

    def _pending(self, appids: list[int]) -> list[int]:
        known = self.cache.records()
        return [a for a in appids if a not in known]

    def _run(self, appids: list[int]) -> None:
        status = self.status
        try:
            pending = self._pending(appids)
            status.total = len(appids)
            status.skipped = len(appids) - len(pending)
            status.done = status.skipped
            known: set[int] = set()
            with self.client_factory() as client:
                for index, appid in enumerate(pending):
                    if self._cancel.is_set():
                        break
                    if index and index % REFRESH_EVERY == 0:
                        known = set(self.cache.records())  # pick up other PCs' progress
                    if appid in known:
                        status.skipped += 1
                        status.done += 1
                        continue
                    self._fetch_one(client, appid)
                    status.done += 1
                    if index < len(pending) - 1:
                        self._sleep(self.interval)
            if self._cancel.is_set():
                status.state = "cancelled"
                status.message = "Cancelled - start again to resume where it stopped."
            else:
                status.state = "completed"
                status.message = "Finished."
        except Exception as exc:  # never let the worker die silently
            log.exception("language job failed")
            status.state = "failed"
            status.message = f"Stopped by an unexpected error: {exc}"
        finally:
            status.finished_at = utc_now()
            log.info(
                "language job ended",
                extra={"state": status.state, "done": status.done, "errors": status.errors},
            )

    def _fetch_one(self, client: httpx.Client, appid: int) -> None:
        status = self.status
        delay = max(self.interval, 2.0)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                record = fetch_languages(client, appid)
            except StoreError as exc:
                if not exc.retryable or attempt == MAX_ATTEMPTS or self._cancel.is_set():
                    status.errors += 1
                    self._log(f"AppID {appid}: {exc} - skipped (will retry next run)")
                    return
                wait = min(exc.retry_after or delay, MAX_BACKOFF_SECONDS)
                self._log(f"AppID {appid}: {exc} - retrying in {wait:.0f}s")
                self._sleep(wait)
                delay = min(delay * 2, MAX_BACKOFF_SECONDS)
                continue
            self.cache.append(record)
            if record.status == "ok":
                status.found += 1
            else:
                status.unavailable += 1
            return
