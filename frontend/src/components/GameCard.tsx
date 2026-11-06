import type { ReactNode } from "react";
import type { GameReport } from "../api/client";
import { formatCompactCurrency, formatCurrency, formatInt, minorToMajor } from "../lib/format";
import { HeroImage } from "./HeroImage";

interface Props {
  game: GameReport;
  onAnother: () => void;
  onCopyAppId: () => void;
  onToggleStudy: () => void;
  onResearch: () => void;
  onExportJpeg: () => void;
  researchOpen: boolean;
  researchPanel?: ReactNode;
  busy: "study" | "export" | null;
}

function languageSummary(game: GameReport): string {
  const info = game.languages;
  if (info.status === "unavailable") return "Not available from the Steam store.";
  if (info.status !== "ok" || info.languages.length === 0)
    return "Not checked yet - run the language lookup in Settings (gear icon).";
  return info.languages.join(", ");
}

export function StudyMetrics({ game }: { game: GameReport }) {
  const price = minorToMajor(game.price.amount_minor);
  return (
    <div className="metric-grid">
      <div className="metric">
        <span className="metric-label">Est. gross revenue</span>
        <span id="gameRevenue" className="metric-value green">
          {formatCompactCurrency(minorToMajor(game.estimated_revenue.amount_minor))}
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Listed price</span>
        <span id="gamePrice" className="metric-value">
          {formatCurrency(price)}
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Yearly revenue rank</span>
        <span id="gameRank" className="metric-value accent">
          #{formatInt(game.rank.rank)}
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Revenue percentile</span>
        <span id="gamePercentile" className="metric-value">
          {game.rank.percentile.toFixed(1)}%
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Steam reviews</span>
        <span id="gameReviews" className="metric-value">
          {formatInt(game.reviews.total)}
        </span>
      </div>
      <div className="metric">
        <span className="metric-label">Positive reviews</span>
        <span id="gameReviewScore" className="metric-value">
          {game.reviews.positive_percent.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

/** Legacy case-study card (hero artwork, metrics, pitch, tags, rank card, actions). */
export function GameCard(props: Props) {
  const { game, onAnother, onCopyAppId, busy } = props;
  const inStudies = game.study.in_studies;
  const rank = game.rank.rank;
  const total = game.rank.population_count;
  const topShare = total > 0 ? Math.min(100, (100 * rank) / total) : 0;
  const leadTags = game.tags.slice(0, 3).join(" · ");

  return (
    <article id="caseStudy" className="panel case-study">
      <div className="hero">
        <HeroImage key={game.appid} appid={game.appid} name={game.name} />
        <div className="hero-gradient"></div>
        <div className="hero-content">
          <div className="case-label">Indie case study</div>
          <h2 id="gameTitle" className="game-title">
            {game.name}
          </h2>
          <div id="heroMeta" className="hero-meta">
            <span className="hero-chip">{game.release_year}</span>
            <span className="hero-chip">AppID {game.appid}</span>
            {leadTags && <span className="hero-chip">{leadTags}</span>}
            {!game.qualification.qualified && (
              <span className="hero-chip hero-chip-warning" data-testid="below-floor">
                Below {formatCompactCurrency(game.qualification.threshold_usd)} catalog floor
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="case-content">
        <StudyMetrics game={game} />
        <p className="provenance" data-testid="provenance">
          Legacy snapshot (capture date unknown). Revenue is an estimate: total reviews × 45 ×
          listed price; not actual sales. Ranks are within the legacy {game.release_year} dataset.
        </p>

        <div className="details-grid">
          <div>
            <section>
              <h3 className="section-title">Store pitch</h3>
              <p id="gameDescription" className="description">
                {game.short_description || "No short store description is available."}
              </p>
            </section>
            <section style={{ marginTop: 26 }}>
              <h3 className="section-title">Steam tags</h3>
              <div id="gameTags" className="tag-list">
                {game.tags.length ? (
                  game.tags.map((tag) => (
                    <span className="tag" key={tag}>
                      {tag}
                    </span>
                  ))
                ) : (
                  <span className="tag">No tags available</span>
                )}
              </div>
            </section>
            <section style={{ marginTop: 26 }}>
              <h3 className="section-title">
                Languages
                {game.languages.english === true && <span className="lang-badge ok">English ✓</span>}
                {game.languages.english === false && (
                  <span className="lang-badge no">No English</span>
                )}
              </h3>
              <p id="gameLanguages" className="description languages-text">
                {languageSummary(game)}
              </p>
            </section>
          </div>
          <aside>
            <div className="rank-card">
              <span className="rank-label">Position among qualifying releases</span>
              <strong id="rankCardValue" className="rank-value">
                #{formatInt(rank)} of {formatInt(total)}
              </strong>
              <span id="rankCardNote" className="rank-note">
                Approximately the top {topShare.toFixed(1)}% of qualifying {game.release_year}{" "}
                releases in the legacy dataset. Dataset percentile:{" "}
                {game.rank.percentile.toFixed(1)}th.
              </span>
            </div>
          </aside>
        </div>

        <div className="actions">
          <button id="anotherButton" className="primary-button" type="button" onClick={onAnother}>
            Another case study
          </button>
          <a
            id="steamLink"
            className="store-button"
            href={game.steam_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Reveal Steam page ↗
          </a>
          <button
            id="copyAppIdButton"
            className="secondary-button"
            type="button"
            onClick={onCopyAppId}
          >
            Copy AppID
          </button>
        </div>
        <div className="actions actions-study">
          <button
            id="studyButton"
            className={inStudies ? "secondary-button study-active" : "primary-button study-button"}
            type="button"
            aria-pressed={inStudies}
            disabled={busy === "study"}
            onClick={props.onToggleStudy}
            title={inStudies ? "Remove this game from Studies" : "Archive as a potential case study"}
          >
            {inStudies ? "✓ In Studies" : "＋ Add to Studies"}
          </button>
          <button
            id="researchButton"
            className="secondary-button"
            type="button"
            aria-expanded={props.researchOpen}
            onClick={props.onResearch}
          >
            Get more info from LLM
          </button>
          <button
            id="exportJpegButton"
            className="secondary-button"
            type="button"
            disabled={busy === "export"}
            onClick={props.onExportJpeg}
          >
            {busy === "export" ? "Exporting…" : "Export as JPG"}
          </button>
          {inStudies && game.study.added_at && (
            <span className="study-meta">
              Added {game.study.added_at.slice(0, 10)}
              {game.study.added_by ? ` on ${game.study.added_by}` : ""}
            </span>
          )}
        </div>
        {props.researchOpen && props.researchPanel}
      </div>
    </article>
  );
}
