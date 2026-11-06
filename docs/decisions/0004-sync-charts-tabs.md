# ADR 0004: Steam data sync, charts and the three-tab layout

Status: accepted. Date: 2026-11-06. Covers plan Phases 3 and 4.

## UI: three tabs (user request, replaces the plan's five pages)
**Suggest** (study workflow: suggestions, report, Studies, LLM button, JPG export) · **Charts** ·
**Data** (all dataset updates, including language lookups, which moved out of Settings). Settings
(gear) keeps folders, floor, offline mode, request rate and keys. Tabs stay mounted once
opened, so switching keeps the current game and filters. The URL hash selects the tab.
Charts are lazy-loaded (Recharts).

## Steam endpoints (verified live 2026-11-06)
| Data | Endpoint | Key | Notes |
|---|---|---|---|
| Reviews | `IUserReviewsService/GetAppReviews` | no | must send `languages:["all"]`; without it Steam returns English-only totals (128,498 vs 252,733 for Vampire Survivors). With it, counts match the legacy dataset's definition (positive + negative, all languages). |
| Price, release date, languages, type | store `appdetails?filters=basic,price_overview,release_date&cc=us` | no | undiscounted `initial` USD price is used |
| Tags | SteamSpy `appdetails` | no | voted user tags, top 20, ~1 req/s |
| New AppIDs | `IStoreService/GetAppList` | **yes** | keyless returns 403; the old `ISteamApps/GetAppList` is gone (404) |

## Storage: observations, never catalog writes
Every fetch appends an observation (`store` / `reviews` / `tags` / `listed`) to
`<data>/observations/steam-<pc>.jsonl`. Reads merge all PCs' files incrementally (half-synced
last lines are skipped until complete). The in-memory catalog is the legacy import overlaid with
the newest observation per kind, plus newly discovered games. The SQLite catalog stays
read-only, so this remains safe for several PCs on one shared drive (ADR 0003). The full review
history is kept for the per-game trend chart.

## Ranks
The legacy rank and percentile were reverse-engineered and verified on all 15,521 records:
- **population** = games of that release year with at least 20 reviews;
- **rank** = position by estimated revenue (ties in source order);
- **percentile** = `round(100 × (N − rank + 1) / N, 2)`.

Ranks are now always recomputed over the local catalog. For untouched data they are identical
to the legacy values (tested), so legacy parity holds. Once data changes, ranks move and the UI
labels them "local catalog". The imported legacy rank is kept alongside.

## Jobs
One bounded background worker with per-provider rate limits: `store_requests_per_minute`
(default 35) for store and reviews, 1.2 s for SteamSpy, and 1 s for the app list. It backs off
exponentially on 429 and 5xx, honouring `Retry-After`, with at most 4 attempts. It can be
cancelled and resumes on the next run. Every job has a preview (games, requests, time) before
it starts.
- **Refresh**: scope qualified / all / Studies, release years, parts (reviews, store, tags),
  skip games updated within N days (default 7), optional limit.
- **Discover**: lists AppIDs above the highest known one ("since the last AppID", as requested;
  the UI notes that AppID order is not release order). It screens each with one reviews call:
  a game whose `reviews × 45 × $70` is below the floor is skipped. Promising ones get store info,
  then tags if they qualify.
- **Languages**: store info for games without language data. **Single AppID**: everything for
  one game, including AppIDs not yet in the catalog.

## Charts (dataviz method)
Single-hue blue (`#3987e5`). The only second series is Studies, in orange (`#d95926`) on the
price scatter. Both were validated on the app's dark panel (#111823): CVD ΔE 26.8, contrast ≥ 3:1.
- 24 px bars with rounded data ends; hairline grid; log axes ticked at powers of ten.
- A tooltip on every mark, a table view on every chart, and no dual axes.
- A scope line with counts, the "as of" time and the estimate model.
- The scatter is a deterministic sample of at most 1,500 points (Studies always shown); clicking
  a dot opens the game.

## Deferred
- LLM research (Phase 5): waiting for the user's list of fields and their provider/key choice.
- Desktop hardening (Phase 6 remainder): backup/restore UI, single-instance guard, code signing.
