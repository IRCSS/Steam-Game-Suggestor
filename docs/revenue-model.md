# Revenue model

## `legacy_reviews_x45_price` (current, the only model)

```text
estimated_gross_revenue_usd = round(total_reviews * 45 * listed_price_usd)
```

- This is an **estimate of gross revenue**. It is not actual sales, net revenue, take-home income
  or profit. The UI labels it "Est. gross revenue" and adds a provenance line to every report.
- The multiplier of 45 sales per review is a coarse industry heuristic. The listed price is a
  snapshot with unknown date, region and discount state.
- Imported values are stored **exactly as found**. All 15,521 legacy values match the formula
  (0 mismatches); any future mismatch is flagged, never silently corrected.
- Games with a legacy price of 0 have an estimate of 0. That is **not** a claim that they earned
  nothing: free-to-play income is unknown (`price_zero_f2p_unverified`).

## Qualification floor

The catalog gate (default **$100,000** estimated gross, set with
`STEAM_STUDY_QUALIFICATION_MIN_REVENUE_USD`) decides which games enter the suggestion pool. It is
independent of the user-visible revenue filter, which defaults to the legacy $150K-$800K. Games
below the floor stay in the database and can always be reached by exact lookup.

## Ranks and percentiles

`revenue_rank_in_year`, `qualifying_games_in_year` and `revenue_percentile_in_year` describe the
**legacy source population** for that release year. They are shown as imported and labelled as
legacy-scoped. They are never recomputed against a different population.
