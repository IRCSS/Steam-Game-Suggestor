"""Small helpers for sync-friendly file storage on local, network or cloud-synced drives."""

from __future__ import annotations

import json
import os
import re
import socket
import uuid
from pathlib import Path
from typing import Any

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def machine_id() -> str:
    """Stable, filename-safe identifier for this PC (used to shard per-PC files)."""
    name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "pc"
    return _UNSAFE.sub("-", name).strip("-").lower() or "pc"


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write via a temp file in the same folder + rename, so readers (and sync clients) never
    see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
