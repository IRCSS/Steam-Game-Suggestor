import type { JobView } from "../api/client";
import { formatCompactCurrency, formatCurrency } from "../lib/format";
import {
  CONFIDENCE_LABEL,
  type Confidence,
  type ResearchStatus,
  type ResearchView,
  compactCount,
  estimateText,
  money,
  moneyRange,
  years,
} from "../lib/research";

export function ConfidenceChip({ level }: { level: Confidence }) {
  return (
    <span className={`conf-chip conf-${level}`} title={`${CONFIDENCE_LABEL[level]} confidence`}>
      {CONFIDENCE_LABEL[level]}
    </span>
  );
}

function Sources({ sources }: { sources: { title: string; url: string }[] }) {
  if (!sources.length) return null;
  return (
    <span className="research-sources">
      {sources.map((s, i) => (
        <a key={`${s.url}-${i}`} href={s.url} target="_blank" rel="noopener noreferrer" title={s.url}>
          {s.title || new URL(s.url).hostname}
        </a>
      ))}
    </span>
  );
}

/** The standardized research table + review insights (also rendered in the JPG export). */
export function ResearchTable({ view, forExport = false }: { view: ResearchView; forExport?: boolean }) {
  const run = view.run;
  const econ = view.economics;
  if (!run) return null;
  const f = run.findings;
  const months = f.development_months;
  const monthsBest = months.best ?? (months.low != null && months.high != null ? (months.low + months.high) / 2 : null);
  const cut = econ ? Math.round(econ.platform_cut * 100) : 30;

  return (
    <>
      <table className="research-table" data-testid="research-table">
        <thead>
          <tr>
            <th>Question</th>
            <th>Estimate</th>
            <th>Confidence</th>
            <th>{forExport ? "Basis" : "Basis & sources"}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>People who worked on it</td>
            <td className="research-value">{estimateText(f.team_size, "people")}</td>
            <td>
              <ConfidenceChip level={f.team_size.confidence as Confidence} />
            </td>
            <td>
              {f.team_size.basis}
              {!forExport && <Sources sources={f.team_size.sources ?? []} />}
            </td>
          </tr>
          <tr>
            <td>Development time</td>
            <td className="research-value">
              {estimateText(months, "months")}
              {monthsBest != null && <span className="research-sub">≈ {(monthsBest / 12).toFixed(1)} years</span>}
            </td>
            <td>
              <ConfidenceChip level={months.confidence as Confidence} />
            </td>
            <td>
              {months.basis}
              {!forExport && <Sources sources={months.sources ?? []} />}
            </td>
          </tr>
          {econ && (
            <>
              <tr>
                <td>Cost at {money(econ.salary_per_person_year, econ.cost_currency)} per person-year</td>
                <td className="research-value">
                  {moneyRange(econ.cost, econ.cost_currency)}
                  <span className="research-sub">≈ {money(econ.cost_usd.best, "USD")}</span>
                </td>
                <td>
                  <ConfidenceChip level={econ.confidence} />
                </td>
                <td>
                  {econ.person_years.best != null
                    ? `${econ.person_years.best.toFixed(1)} person-years × ${money(econ.salary_per_person_year, econ.cost_currency)}. A team of ${econ.comparison_team_size} would need ${years(econ.comparison_team_years.best)}.`
                    : "Needs team size and development time."}
                </td>
              </tr>
              <tr>
                <td>Break-even (after the {cut}% platform cut)</td>
                <td className="research-value">
                  {econ.break_even_gross_usd.best != null ? `≈ ${money(econ.break_even_gross_usd.best, "USD")} gross` : "Unknown"}
                  {econ.break_even_copies?.best != null && (
                    <span className="research-sub">
                      ≈ {compactCount(econ.break_even_copies.best)} copies at {formatCurrency(econ.price_usd)}
                    </span>
                  )}
                </td>
                <td>
                  <ConfidenceChip level={econ.confidence} />
                </td>
                <td>
                  Gross revenue at which the {100 - cut}% kept covers the cost.
                  {econ.revenue_multiple != null &&
                    ` Est. revenue ${formatCompactCurrency(econ.estimated_revenue_usd)} = ${econ.revenue_multiple >= 10 ? Math.round(econ.revenue_multiple) : econ.revenue_multiple.toFixed(1)}× break-even.`}
                </td>
              </tr>
            </>
          )}
        </tbody>
      </table>

      <div className="research-insights">
        {(
          [
            ["Why it performed as well as it did", f.why_it_worked, "insights-worked"],
            ["Why it didn't do better (bottlenecks)", f.what_held_it_back, "insights-held-back"],
          ] as const
        ).map(([title, items, id]) => (
          <section key={id} data-testid={id}>
            <h4 className="research-insights-title">{title}</h4>
            <ul>
              {(items ?? []).map((item, i) => (
                <li key={i}>
                  <strong>{item.point}</strong> <ConfidenceChip level={item.confidence as Confidence} />
                  {item.evidence && <span className="research-evidence">{item.evidence}</span>}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}

function meta(view: ResearchView): string {
  const run = view.run;
  if (!run) return "";
  const parts = [
    `Researched ${run.created_at.slice(0, 10)} by Claude Code${run.model ? ` (${run.model})` : ""} on ${run.created_by}`,
    `${run.web_searches} web searches`,
    `${run.reviews_used.positive ?? 0}+${run.reviews_used.negative ?? 0} reviews read`,
  ];
  if (run.cost_usd != null) parts.push(`$${run.cost_usd.toFixed(2)}`);
  parts.push(`${Math.round(run.duration_seconds / 60) || 1} min`);
  return parts.join(" · ");
}

interface PanelProps {
  view: ResearchView | null;
  status: ResearchStatus | null;
  job: JobView | null; // the research job, if it concerns this game
  otherJobLabel: string | null; // research running for another game
  onRun: () => void;
  onCancel: () => void;
}

/** "Get more info from LLM": standardized research for the current game. */
export function ResearchPanel({ view, status, job, otherJobLabel, onRun, onCancel }: PanelProps) {
  const running = job?.state === "running";
  const hasRun = Boolean(view?.run);
  const blocked = !status?.available || Boolean(otherJobLabel);

  return (
    <section className="research-panel" data-testid="research-panel" aria-live="polite">
      <div className="research-head">
        <h3 className="section-title">LLM research</h3>
        {hasRun && !running && (
          <button
            id="refreshResearchButton"
            className="ghost-button"
            type="button"
            disabled={blocked}
            title={otherJobLabel ?? status?.message}
            onClick={onRun}
          >
            Refresh research
          </button>
        )}
      </div>

      {running && (
        <div className="research-running" data-testid="research-running">
          <div className="progress">
            <div className="progress-bar indeterminate" />
          </div>
          <p className="settings-help">
            {job?.recent.at(-1)?.slice(9) ?? "Starting…"} - this usually takes 2–5 minutes and can
            run while you keep browsing.{" "}
            <button className="link-button" type="button" onClick={onCancel}>
              Stop
            </button>
          </p>
        </div>
      )}

      {!running && job?.state === "failed" && (
        <p className="settings-warning" role="alert">
          Research failed: {job.message}
        </p>
      )}

      {!hasRun && !running && (
        <div className="research-empty">
          {status?.available ? (
            <>
              <p className="settings-help">
                No research yet. Claude Code will look up team size and development time on the web
                and read the most helpful Steam reviews (usually 2–5 minutes, at most $
                {status.max_budget_usd.toFixed(2)} of your Claude usage).
              </p>
              <button
                id="runResearchButton"
                className="primary-button"
                type="button"
                disabled={Boolean(otherJobLabel)}
                onClick={onRun}
              >
                Run research
              </button>
              {otherJobLabel && <p className="settings-help">Busy: {otherJobLabel}.</p>}
            </>
          ) : (
            <p className="settings-help">{status?.message ?? "Checking research availability…"}</p>
          )}
        </div>
      )}

      {view && hasRun && <ResearchTable view={view} />}

      {view?.run && (
        <p className="research-meta">
          {meta(view)}
          {view.runs_count > 1 && ` · ${view.runs_count} runs kept`}. Estimates from public sources -
          check the links before relying on them.
          {view.run.warnings.length > 0 && ` Notes: ${view.run.warnings.join("; ")}.`}
        </p>
      )}
    </section>
  );
}
