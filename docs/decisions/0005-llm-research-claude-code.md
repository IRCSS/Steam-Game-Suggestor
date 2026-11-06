# ADR 0005: LLM research with the local Claude Code CLI (Phase 5)

Status: accepted. Date: 2026-11-06.

## Context
The user researches the same facts for every candidate game and wants a standardized, cited
result instead of a chat. Every PC that runs the app has the Claude Code CLI installed. This
replaces the plan's "OpenAI Responses API" suggestion; the provider interface stays replaceable
(`llm.provider` in settings.json).

## What is researched (fixed, standardized)
| Item | Source | Computed by |
|---|---|---|
| Team size (people during development) | web (Claude) | range, best estimate, confidence, basis, sources |
| Development time (months to 1.0) | web (Claude) | same |
| Cost at Berlin salaries | app | people × years × €50,000 (configurable); also "a team of 3 would need N years" |
| Break-even | app | gross revenue = cost ÷ (1 − 30% platform cut); in copies at the current price; × the revenue estimate |
| Why it did as well as it did / why not better | 40 positive + 40 negative most helpful English Steam reviews (Claude) | 3-5 points each, with evidence and confidence |

Cost and break-even are deterministic, so they are reproducible and follow settings changes
without a new run. Their confidence is the weaker of the team-size and time confidences.

## How the CLI is run (verified live with CLI 2.1.319)
`claude --print --output-format json --json-schema <schema> --tools WebSearch,WebFetch
--allowedTools WebSearch,WebFetch --permission-mode dontAsk --permission-prompts none
--max-budget-usd <cap> --no-session-persistence --strict-mcp-config [--model <m>]`
- The prompt goes in on stdin, and the CLI runs in an empty temporary folder.
- `structured_output` is validated with Pydantic and then sanitized: a number without a source is
  capped at "low", "unknown" carries no numbers, non-http links are dropped.
- **Lesson from the first live run:** `--tools` alone is not enough. In dontAsk mode every
  WebSearch was silently refused, and the model answered from memory (honestly, with "low"
  confidence). Now the tools are also pre-approved, and refused tool calls or 0 searches are
  stored as visible warnings.
- Prompt v2 requires at least 4 searches. Live result for Vampire Survivors: 5 searches, Wikipedia
  and Vice cited, 65 s, $0.31.

## Storage and safety
- `data/research/<appid>.json` holds the last 10 runs, newest last, shared like the other files.
  Review text is never stored.
- Research has its own one-job worker (it doesn't block data updates), can be stopped, and has
  a time limit (default 15 min) and a budget cap (default $2/run).
- Web pages and reviews are untrusted: the tools are read-only and there is no shell or file
  access. The prompt says so, and the output is schema-validated.
- `settings.json` v2 migration: v1 stored `llm.provider: "none"` as a placeholder. It becomes
  `claude_code`; a later deliberate "Off" is kept.

## UI
"Get more info from LLM" opens the panel and runs research the first time; saved research opens
automatically with the game. The panel shows:
- the 4-row table with confidence labels and source links;
- the two review lists;
- run details (date, PC, model, searches, cost, duration) and "Refresh research".

When research exists, "Export as JPG" extends the image downward with the table and the lists.
