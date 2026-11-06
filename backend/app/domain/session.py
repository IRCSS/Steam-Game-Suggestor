"""In-memory session view history (legacy semantics; one session = one page load / app window).

Kept per process instead of in the shared catalog database, so several PCs using the app on a
shared drive never write to the same file for something this short-lived.

* ``seen``: AppIDs shown since the last repeat reset or history clear (for "avoid repeats").
* ``history``: the 12 most recent distinct AppIDs shown, newest first.
* An automatic repeat reset forgets ``seen`` but keeps the visible history (legacy behaviour);
  "Clear" empties both.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field

HISTORY_LIMIT = 12
MAX_SESSIONS = 500


@dataclass(slots=True)
class _Session:
    seen: set[int] = field(default_factory=set[int])
    history: list[int] = field(default_factory=list[int])  # newest first, distinct


class SessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS) -> None:
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._max = max_sessions
        self._lock = threading.Lock()

    def _get(self, session_id: str) -> _Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = _Session()
            self._sessions[session_id] = session
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return session

    def seen(self, session_id: str) -> frozenset[int]:
        with self._lock:
            return frozenset(self._get(session_id).seen)

    def record_view(self, session_id: str, appid: int) -> None:
        with self._lock:
            session = self._get(session_id)
            session.seen.add(appid)
            session.history = [appid, *(a for a in session.history if a != appid)][:HISTORY_LIMIT]

    def reset_repeats(self, session_id: str) -> None:
        with self._lock:
            self._get(session_id).seen.clear()

    def clear(self, session_id: str) -> None:
        with self._lock:
            session = self._get(session_id)
            session.seen.clear()
            session.history.clear()

    def history(self, session_id: str) -> list[int]:
        with self._lock:
            return list(self._get(session_id).history)
