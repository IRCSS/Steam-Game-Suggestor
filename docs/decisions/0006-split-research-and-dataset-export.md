# ADR 0006: Two-step LLM research and the dataset export

Status: accepted. Date: 2026-11-07.

## Context
The user researches a game in two steps. While browsing, they only need team size and
development time to decide whether the budget fits a study. They analyze the reviews only for
games they keep. One combined research run (ADR 0005) made the first step slow, and it paid for
reading 80 reviews on games that were then dropped.

The user also wants others to be able to analyze the data in their own tools.

## Decision: research split into "budget" and "reviews"
| Step | Button | Input | CLI tools | Typical |
|---|---|---|---|---|
| `budget` | Estimate budget | the game's name and AppID | `WebSearch,WebFetch` | about 1 min |
| `reviews` | Analyze reviews | 40 + 40 most helpful Steam reviews | none (`--tools ""`) | 1–2 min |

- Each step sends its own JSON schema (`findings_json_schema(kind)`). Fields the step does not
  produce keep empty defaults ("unknown" estimates, empty lists). Prompt version 3.
- The budget prompt asks for at least 3 searches (previously 4) and says to stop once there is a
  credible answer. Only the budget step warns when no web search was made.
- Every run stores `kind`. Runs saved before the split have no `kind` and load as `"full"`, which
  answers both steps. `GET /api/research/{appid}` returns the newest run for each step
  (`budget`, `reviews`); economics come from `budget`. `POST` takes `{"kind": ...}`.
- One research job at a time: while one step runs, the other step's button waits.
- Live check (CLI 2.1.308): the reviews command with `--tools ""` returned valid structured output
  and no refused tools, for $0.001.

## Decision: dataset export
Settings -> Export dataset writes `steam-study-dataset-<UTC timestamp>.zip` to the export folder.
- Every table is written twice, as `csv/<table>.csv` and as `json/<table>.json` (a list of objects
  with the same keys). The tables are `games`, `studies`, `research` and `review_history`.
  `json/research-details.json` adds the full research runs (sources, evidence, economics), and
  `dataset.json` holds the manifest (versions, row counts, cost model, qualification floor).
- The CSV files are UTF-8 without a BOM, comma-separated and RFC 4180 quoted. An empty cell is
  unknown, booleans are `true`/`false`, and list values are JSON arrays inside the cell. This way
  every language parses them the same way.
- `README.md` in the zip describes every column and marks estimates as estimates.
- Settings, API keys and review text are never exported.
- Table rows are built in `domain/dataset.py` (pure functions); the zip is written in
  `storage/dataset_export.py` (temp file, then rename).
