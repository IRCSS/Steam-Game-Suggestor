"""Writes a dataset export (see ``domain/dataset.py``) as one zip file: README.md, dataset.json,
csv/<table>.csv and json/<table>.json."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.domain.dataset import Table


def _csv(table: Table) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([c for c, _ in table.columns])
    for row in table.rows:
        writer.writerow([table.csv_cell(row.get(c)) for c, _ in table.columns])
    return out.getvalue()


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def write_dataset_zip(
    target: Path,
    tables: Sequence[Table],
    readme: str,
    manifest: Mapping[str, Any],
    extra_json: Mapping[str, Any],
) -> Path:
    """Write via a temp file + rename, so a half-written zip is never left under the real name."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        archive.writestr("dataset.json", _json(manifest))
        for table in tables:
            archive.writestr(f"csv/{table.name}.csv", _csv(table))
            archive.writestr(f"json/{table.name}.json", _json(table.rows))
        for name, payload in extra_json.items():
            archive.writestr(f"json/{name}.json", _json(payload))
    tmp.replace(target)
    return target
