import { forwardRef } from "react";
import { api, type GameReport, type ResearchView } from "../api/client";
import { formatCompactCurrency, formatCurrency, formatInt, minorToMajor } from "../lib/format";
import { PLACEHOLDER_IMAGE } from "./HeroImage";
import { BudgetTable, ReviewInsights } from "./ResearchPanel";

interface Props {
  game: GameReport;
  exportedAt: Date;
  research?: ResearchView | null;
  onArtworkSettled: () => void;
}

/**
 * Compact, button-free study sheet rendered off-screen and captured as a JPEG ("Export JPG").
 * Artwork comes through the backend proxy (same origin) so it can be drawn into the image.
 */
export const ExportCard = forwardRef<HTMLDivElement, Props>(function ExportCard(
  { game, exportedAt, research, onArtworkSettled },
  ref,
) {
  const rank = game.rank.rank;
  const total = game.rank.population_count;
  const topShare = total > 0 ? Math.min(100, (100 * rank) / total) : 0;
  const languages = game.languages;
  const languageText =
    languages.status === "ok" && languages.languages.length
      ? languages.languages.join(", ")
      : languages.status === "unavailable"
        ? "Not available from the Steam store"
        : "Not checked yet";

  const metrics: [string, string, string?][] = [
    ["Est. gross revenue", formatCompactCurrency(minorToMajor(game.estimated_revenue.amount_minor)), "green"],
    ["Listed price", formatCurrency(minorToMajor(game.price.amount_minor))],
    ["Yearly revenue rank", `#${formatInt(rank)} of ${formatInt(total)}`, "accent"],
    ["Revenue percentile", `${game.rank.percentile.toFixed(1)}%`],
    ["Steam reviews", formatInt(game.reviews.total)],
    ["Positive reviews", `${game.reviews.positive_percent.toFixed(1)}%`],
  ];

  return (
    <div ref={ref} className="export-card" data-testid="export-card">
      <div className="export-top">
        <img
          className="export-art"
          alt=""
          src={api.artworkUrl(game.appid)}
          onLoad={onArtworkSettled}
          onError={(e) => {
            if (e.currentTarget.src !== PLACEHOLDER_IMAGE) e.currentTarget.src = PLACEHOLDER_IMAGE;
            onArtworkSettled();
          }}
        />
        <div className="export-heading">
          <div className="case-label">Indie case study</div>
          <h1 className="export-title">{game.name}</h1>
          <div className="export-chips">
            <span className="hero-chip">{game.release_year}</span>
            <span className="hero-chip">AppID {game.appid}</span>
            {game.languages.english === true && <span className="hero-chip">English ✓</span>}
            {game.languages.english === false && (
              <span className="hero-chip hero-chip-warning">No English</span>
            )}
          </div>
          <div className="export-url">{game.steam_url}</div>
        </div>
      </div>

      <div className="export-metrics">
        {metrics.map(([label, value, tone]) => (
          <div className="metric" key={label}>
            <span className="metric-label">{label}</span>
            <span className={`metric-value${tone ? ` ${tone}` : ""}`}>{value}</span>
          </div>
        ))}
      </div>

      <div className="export-body">
        <section>
          <h3 className="section-title">Store pitch</h3>
          <p className="description">
            {game.short_description || "No short store description is available."}
          </p>
        </section>
        <section>
          <h3 className="section-title">Steam tags</h3>
          <div className="tag-list">
            {game.tags.map((tag) => (
              <span className="tag" key={tag}>
                {tag}
              </span>
            ))}
          </div>
        </section>
        <section>
          <h3 className="section-title">Languages</h3>
          <p className="export-small">{languageText}</p>
        </section>
        <section>
          <h3 className="section-title">Market position</h3>
          <p className="export-small">
            Approximately the top {topShare.toFixed(1)}% of qualifying {game.release_year} releases
            in the legacy dataset (#{formatInt(rank)} of {formatInt(total)}).
          </p>
        </section>
      </div>

      {(research?.budget || research?.reviews) && (
        <section className="export-research" data-testid="export-research">
          <h3 className="section-title">LLM research</h3>
          <BudgetTable view={research} forExport />
          <ReviewInsights run={research.reviews} />
          <p className="export-small">
            {research.budget &&
              `Budget researched ${research.budget.created_at.slice(0, 10)} by Claude Code from public sources; cost and break-even are calculated from the estimates. `}
            {research.reviews &&
              `Reviews analyzed ${research.reviews.created_at.slice(0, 10)} from the most helpful Steam reviews.`}
          </p>
        </section>
      )}

      <footer className="export-footer">
        Exported {exportedAt.toISOString().slice(0, 10)} · Indie Case Study Suggester · Revenue is an
        estimate (total reviews × 45 × listed price), not actual sales · Legacy snapshot, capture
        date unknown
      </footer>
    </div>
  );
});
