# Phase 5: LLM research (Claude Code CLI)

Status: **PASS**. Design: [ADR 0005](../decisions/0005-llm-research-claude-code.md)

## Implemented
- **Standardized research per game:**
  - team size and development time, from the web, each with a confidence and sources;
  - cost at €50K per person-year and break-even after the 30% platform cut, both calculated;
  - why it worked / why not better, from the most helpful Steam reviews.
- **Claude Code CLI provider** (headless, locked down, budget- and time-capped), with its own
  background worker, Stop, and warnings for refused tools or missing searches.
- `data/research/<appid>.json` keeps the last 10 runs.
- **Settings:** provider, model, CLI path (auto-detected), spend cap, time limit, and the cost
  model (salary, currency, exchange rate, comparison team size, platform cut). Settings file v2
  migration.
- **UI:** research panel with confidence labels and source links; the JPG export includes the
  research.

## Verification
- `npm run check`: ruff, pyright strict (0 errors), tsc, eslint, API contract, 118 pytest, 33 vitest.
- `npm run test-e2e`: 31 Playwright tests (saved research shown and exported; offline state).
- **Live runs** (Vampire Survivors):
  - Run 1 found that web tools were refused in dontAsk mode. Fixed with `--allowedTools`; the
    failure is now reported as a warning.
  - Run 2: 1 search ($0.18).
  - Run 3 (prompt v2): 5 searches, Wikipedia and Vice cited, 65 s, $0.31.

  The review insights were specific and consistent in all three runs.

## Limitations
- Team size and development time for small studios are often not public. Expect "low" or
  "medium" confidence, a wide range, and an explanation; the numbers are estimates.
- Each run uses the PC's Claude Code account (about $0.2-0.5 at current settings).
