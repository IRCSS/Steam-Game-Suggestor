import type { JobView } from "../api/client";
import { formatCompactCurrency, formatCurrency } from "../lib/format";
import {
  CONFIDENCE_LABEL,
  type Confidence,
  type EstimateView,
  type ResearchKind,
  type ResearchRun,
  type ResearchStatus,
  type ResearchView,
  compactCount,
  estimateText,
  jobResearchKind,
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

const UNKNOWN: EstimateView = { confidence: "unknown", basis: "" };

/** Team size, development time and the calculated cost / break-even (also in the JPG export). */
export function BudgetTable({ view, forExport = false }: { view: ResearchView; forExport?: boolean }) {
  const run = view.budget;
  const econ = view.economics;
  if (!run) return null;
  const team = run.findings.team_size ?? UNKNOWN;
  const months = run.findings.development_months ?? UNKNOWN;
  const monthsBest = months.best ?? (months.low != null && months.high != null ? (months.low + months.high) / 2 : null);
  const cut = econ ? Math.round(econ.platform_cut * 100) : 30;

  return (
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
          <td className="research-value">{estimateText(team, "people")}</td>
          <td>
            <ConfidenceChip level={team.confidence as Confidence} />
          </td>
          <td>
            {team.basis}
            {!forExport && <Sources sources={team.sources ?? []} />}
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
  );
}

/** Why it did well / what held it back, from the Steam reviews (also in the JPG export). */
export function ReviewInsights({ run }: { run: ResearchRun | null }) {
  if (!run) return null;
  const f = run.findings;
  return (
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
  );
}

function meta(run: ResearchRun, kind: ResearchKind): string {
  const parts = [`Researched ${run.created_at.slice(0, 10)} by Claude Code${run.model ? ` (${run.model})` : ""} on ${run.created_by}`];
  if (kind === "budget") parts.push(`${run.web_searches} web searches`);
  else parts.push(`${run.reviews_used.positive ?? 0}+${run.reviews_used.negative ?? 0} reviews read`);
  if (run.cost_usd != null) parts.push(`$${run.cost_usd.toFixed(2)}`);
  parts.push(`${Math.round(run.duration_seconds / 60) || 1} min`);
  return parts.join(" · ");
}

const SECTION: Record<
  ResearchKind,
  { title: string; run: string; refresh: string; testid: string; explain: string; takes: string; caveat: string }
> = {
  budget: {
    title: "Budget estimate",
    run: "Estimate budget",
    refresh: "Refresh budget",
    testid: "research-budget",
    explain: "Claude Code looks up on the web how many people made it and how long it took; the app calculates the cost",
    takes: "usually about a minute",
    caveat: "Estimates from public sources - check the links before relying on them.",
  },
  reviews: {
    title: "Review analysis",
    run: "Analyze reviews",
    refresh: "Refresh review analysis",
    testid: "research-reviews",
    explain: "Claude Code reads the 40 most helpful positive and 40 negative Steam reviews: why it did well and what held it back",
    takes: "usually 1–2 minutes",
    caveat: "Summarized from player reviews.",
  },
};

interface PanelProps {
  view: ResearchView | null;
  status: ResearchStatus | null;
  job: JobView | null; // the research job, if it concerns this game
  otherJobLabel: string | null; // research running for another game
  onRun: (kind: ResearchKind) => void;
  onCancel: () => void;
}

/** LLM research for the current game, in two steps: budget estimate, then review analysis. */
export function ResearchPanel({ view, status, job, otherJobLabel, onRun, onCancel }: PanelProps) {
  const jobKind = jobResearchKind(job);
  const anyRunning = job?.state === "running";

  const section = (kind: ResearchKind) => {
    const s = SECTION[kind];
    const run = view ? view[kind] : null;
    const running = anyRunning && jobKind === kind;
    // One research job at a time: the other step waits until this one is done.
    const busyLabel = otherJobLabel ?? (anyRunning && !running ? (job?.label ?? null) : null);
    const blocked = !status?.available || Boolean(busyLabel);
    return (
      <section className="research-section" data-testid={s.testid}>
        <div className="research-head">
          <h3 className="section-title">{s.title}</h3>
          {run && !running && (
            <button className="ghost-button" type="button" disabled={blocked} title={busyLabel ?? status?.message} onClick={() => onRun(kind)}>
              {s.refresh}
            </button>
          )}
        </div>

        {running && (
          <div className="research-running" data-testid="research-running">
            <div className="progress">
              <div className="progress-bar indeterminate" />
            </div>
            <p className="settings-help">
              {job?.recent.at(-1)?.slice(9) ?? "Starting…"} - {s.takes}, and you can keep browsing.{" "}
              <button className="link-button" type="button" onClick={onCancel}>
                Stop
              </button>
            </p>
          </div>
        )}

        {!running && job?.state === "failed" && jobKind === kind && (
          <p className="settings-warning" role="alert">
            {s.title} failed: {job.message}
          </p>
        )}

        {!run && !running && (
          <div className="research-empty">
            {status?.available ? (
              <>
                <p className="settings-help">
                  Not done yet. {s.explain} ({s.takes}, at most ${status.max_budget_usd.toFixed(2)} of
                  your Claude usage).
                </p>
                <button className="primary-button" type="button" disabled={Boolean(busyLabel)} onClick={() => onRun(kind)}>
                  {s.run}
                </button>
                {busyLabel && <p className="settings-help">Busy: {busyLabel}.</p>}
              </>
            ) : (
              <p className="settings-help">{status?.message ?? "Checking research availability…"}</p>
            )}
          </div>
        )}

        {view && run && (kind === "budget" ? <BudgetTable view={view} /> : <ReviewInsights run={run} />)}

        {run && (
          <p className="research-meta">
            {meta(run, kind)}. {s.caveat}
            {run.warnings.length > 0 && ` Notes: ${run.warnings.join("; ")}.`}
          </p>
        )}
      </section>
    );
  };

  return (
    <section className="research-panel" data-testid="research-panel" aria-live="polite">
      {section("budget")}
      {section("reviews")}
    </section>
  );
}
