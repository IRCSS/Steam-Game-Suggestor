import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import {
  api,
  type ChartsResponse,
  type GameReport,
  type HistoryResponse2,
  type MetaResponse,
  type StudyFilters,
} from "../api/client";
import { CHART, binLabel, compactNumber, compactUsd, logDomain, logTicks } from "../lib/chartTheme";
import { formatCurrency, formatInt } from "../lib/format";

interface Props {
  meta: MetaResponse;
  active: boolean;
  refreshToken: number;
  currentGame: GameReport | null;
  suggestFilters: StudyFilters | null;
  onOpenGame?: (appid: number) => void;
}

type Point = ChartsResponse["points"][number];

const axisProps = {
  stroke: CHART.axis,
  tick: { fill: CHART.subtle, fontSize: 11 },
  tickLine: false,
} as const;

/** Tooltip shell: value first (strong), label secondary; text tokens only. */
function TipBox({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{title}</div>
      {rows.map(([label, value]) => (
        <div className="chart-tooltip-row" key={label}>
          <strong>{value}</strong> <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

function ChartCard(props: {
  id: string;
  title: string;
  subtitle: string;
  table: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className={`panel chart-card${props.wide ? " wide" : ""}`} aria-labelledby={`${props.id}-title`}>
      <div className="chart-card-head">
        <div>
          <h2 id={`${props.id}-title`} className="chart-title">
            {props.title}
          </h2>
          <p className="chart-subtitle">{props.subtitle}</p>
        </div>
        <button
          className="ghost-button chart-table-toggle"
          type="button"
          aria-pressed={showTable}
          onClick={() => setShowTable((s) => !s)}
        >
          {showTable ? "Chart" : "Table"}
        </button>
      </div>
      {showTable ? <div className="chart-table-wrap">{props.table}</div> : props.children}
    </section>
  );
}

function DataTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="research-table chart-table">
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Dot with a 2px surface ring and a 24px transparent hit area. */
function Dot(color: string, radius: number, opacity: number) {
  return function DotShape(props: unknown) {
    const { cx, cy } = props as { cx?: number; cy?: number };
    if (cx === undefined || cy === undefined) return <g />;
    return (
      <g>
        <circle cx={cx} cy={cy} r={12} fill="transparent" />
        <circle
          cx={cx}
          cy={cy}
          r={radius}
          fill={color}
          fillOpacity={opacity}
          stroke={CHART.surface}
          strokeWidth={radius > 3 ? 2 : 0}
        />
      </g>
    );
  };
}

function YearChips({
  years,
  value,
  onChange,
}: {
  years: number[];
  value: number[];
  onChange: (v: number[]) => void;
}) {
  return (
    <div className="chip-row" role="group" aria-label="Release years">
      {years.map((year) => {
        const on = value.includes(year);
        return (
          <button
            key={year}
            type="button"
            className={`chip${on ? " on" : ""}`}
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((y) => y !== year) : [...value, year].sort())}
          >
            {year}
          </button>
        );
      })}
      <span className="chip-hint">{value.length ? "" : "all years"}</span>
    </div>
  );
}

function GameHistory({
  appid,
  refreshToken,
  asTable = false,
}: {
  appid: number | null;
  refreshToken: number;
  asTable?: boolean;
}) {
  const [history, setHistory] = useState<HistoryResponse2 | null>(null);
  useEffect(() => {
    if (appid === null) return;
    let cancelled = false;
    api
      .gameHistory(appid)
      .then((h) => !cancelled && setHistory(h))
      .catch(() => !cancelled && setHistory(null));
    return () => {
      cancelled = true;
    };
  }, [appid, refreshToken]);

  if (appid === null) {
    return <p className="settings-help">Open a game in the Suggest tab to see its review history.</p>;
  }
  if (!history) return <p className="settings-help">Loading…</p>;
  const legacy = history.points.find((p) => !p.observed_at);
  const dated = history.points
    .filter((p) => p.observed_at)
    .map((p) => ({ ...p, t: new Date(p.observed_at as string).getTime() }));
  if (asTable) {
    return (
      <DataTable
        head={["Observed", "Source", "Reviews", "Est. revenue"]}
        rows={history.points.map((p) => [
          p.observed_at ? new Date(p.observed_at).toLocaleString() : "date unknown",
          p.source === "legacy_import" ? "legacy import" : "Steam",
          formatInt(p.total_reviews),
          compactUsd(p.estimated_revenue),
        ])}
      />
    );
  }
  return (
    <>
      {legacy && (
        <p className="settings-help">
          Legacy import (date unknown): {formatInt(legacy.total_reviews)} reviews,{" "}
          {compactUsd(legacy.estimated_revenue)} estimated.
        </p>
      )}
      {!history.enough_history ? (
        <p className="settings-help" data-testid="history-empty">
          Not enough history yet - {dated.length === 0 ? "no Steam updates" : "only one Steam update"}{" "}
          for {history.name}. Each data update adds a point (Data tab).
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={dated} margin={{ top: 12, right: 24, bottom: 4, left: 8 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(t: number) => new Date(t).toLocaleDateString()}
              {...axisProps}
            />
            <YAxis tickFormatter={compactNumber} width={56} {...axisProps} />
            <Tooltip
              cursor={{ stroke: CHART.axis }}
              content={({ active, payload }) => {
                const p = payload?.[0]?.payload as (typeof dated)[number] | undefined;
                if (!active || !p) return null;
                return (
                  <TipBox
                    title={new Date(p.t).toLocaleString()}
                    rows={[
                      ["reviews", formatInt(p.total_reviews)],
                      ["est. revenue", compactUsd(p.estimated_revenue)],
                    ]}
                  />
                );
              }}
            />
            <Line
              type="monotone"
              dataKey="total_reviews"
              stroke={CHART.series1}
              strokeWidth={2}
              dot={{ r: 4, fill: CHART.series1, stroke: CHART.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </>
  );
}

export default function ChartsPage({
  meta,
  active,
  refreshToken,
  currentGame,
  suggestFilters,
  onOpenGame,
}: Props) {
  const [useStudyFilters, setUseStudyFilters] = useState(false);
  const [years, setYears] = useState<number[]>([]);
  const [includeBelow, setIncludeBelow] = useState(false);
  const [minTagCount, setMinTagCount] = useState("20");
  const [data, setData] = useState<ChartsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const request = useMemo(
    () => ({
      use_study_filters: useStudyFilters,
      filters: useStudyFilters ? suggestFilters : null,
      include_below_threshold: includeBelow,
      years: useStudyFilters ? [] : years,
      min_tag_count: Math.max(1, Number(minTagCount) || 20),
      tag_limit: 20,
    }),
    [useStudyFilters, suggestFilters, includeBelow, years, minTagCount],
  );

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api
        .charts(request, controller.signal)
        .then((r) => {
          setData(r);
          setError("");
        })
        .catch((e: unknown) => {
          if (!(e instanceof DOMException)) setError("Could not load chart data.");
        })
        .finally(() => setLoading(false));
    }, 150);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [request, active, refreshToken]);

  const scatter = useMemo(() => {
    const points = data?.points ?? [];
    return {
      all: points.filter((p) => !p.in_studies && p.revenue > 0),
      studies: points.filter((p) => p.in_studies && p.revenue > 0),
      reviews: points.filter((p) => p.reviews > 0),
    };
  }, [data]);

  const revenueTicks = useMemo(() => {
    const values = [...scatter.all, ...scatter.studies].map((p) => p.revenue);
    return values.length ? logTicks(Math.min(...values), Math.max(...values)) : [];
  }, [scatter]);
  const reviewTicks = useMemo(() => {
    const values = scatter.reviews.map((p) => p.reviews);
    return values.length ? logTicks(Math.min(...values), Math.max(...values)) : [];
  }, [scatter]);

  const tags = useMemo(
    () => [...(data?.tags ?? [])].sort((a, b) => b.median_revenue - a.median_revenue),
    [data],
  );
  const bins = (data?.revenue_bins ?? []).map((b) => ({ ...b, label: binLabel(b.start, b.end) }));

  const pointTip = ({ active: on, payload }: { active?: boolean; payload?: readonly { payload?: unknown }[] }) => {
    const p = payload?.[0]?.payload as Point | undefined;
    if (!on || !p) return null;
    return (
      <TipBox
        title={`${p.name} (${p.year})${p.in_studies ? " · in Studies" : ""}`}
        rows={[
          ["est. revenue", compactUsd(p.revenue)],
          ["price", formatCurrency(p.price)],
          ["reviews", formatInt(p.reviews)],
          ["positive", `${p.score.toFixed(1)}%`],
        ]}
      />
    );
  };
  const openPoint = (p: unknown) => {
    const point = (p as { payload?: Point } | undefined)?.payload;
    if (point && onOpenGame) onOpenGame(point.appid);
  };

  const scope = data?.scope_label ?? "";
  const sampled = data && data.points.length < data.points_total;
  const k = data?.kpis;

  return (
    <div className="charts-page">
      <div className="panel chart-filters" role="group" aria-label="Chart scope">
        <label className="settings-check">
          <input
            type="radio"
            name="chart-scope"
            checked={!useStudyFilters}
            onChange={() => setUseStudyFilters(false)}
          />
          Qualified catalog
        </label>
        <label className="settings-check">
          <input
            type="radio"
            name="chart-scope"
            checked={useStudyFilters}
            disabled={!suggestFilters}
            onChange={() => setUseStudyFilters(true)}
          />
          Same filters as the Suggest tab
        </label>
        {!useStudyFilters && <YearChips years={meta.years} value={years} onChange={setYears} />}
        <label className="settings-check">
          <input
            type="checkbox"
            checked={includeBelow}
            onChange={(e) => setIncludeBelow(e.target.checked)}
          />
          Include games below the floor
        </label>
        <label className="settings-check">
          Min games per tag
          <input
            className="inline-number"
            type="number"
            min={1}
            value={minTagCount}
            onChange={(e) => setMinTagCount(e.target.value)}
          />
        </label>
      </div>

      {error && (
        <p className="settings-warning" role="alert">
          {error}
        </p>
      )}

      <div className={`charts-body${loading && data ? " refetching" : ""}`}>
        {k && (
          <div className="metric-grid data-stats" data-testid="chart-kpis">
            <div className="metric stat-tile">
              <span className="metric-label">Games in scope</span>
              <span className="metric-value">{formatInt(k.count)}</span>
            </div>
            <div className="metric stat-tile">
              <span className="metric-label">Median est. revenue</span>
              <span className="metric-value green">
                {k.median_revenue === null || k.median_revenue === undefined ? "–" : compactUsd(k.median_revenue)}
              </span>
            </div>
            <div className="metric stat-tile">
              <span className="metric-label">Median price</span>
              <span className="metric-value">
                {k.median_price === null || k.median_price === undefined ? "–" : formatCurrency(k.median_price)}
              </span>
            </div>
            <div className="metric stat-tile">
              <span className="metric-label">Median reviews</span>
              <span className="metric-value">
                {k.median_reviews === null || k.median_reviews === undefined ? "–" : formatInt(Math.round(k.median_reviews))}
              </span>
            </div>
            <div className="metric stat-tile">
              <span className="metric-label">Median positive</span>
              <span className="metric-value">
                {k.median_score === null || k.median_score === undefined ? "–" : `${k.median_score.toFixed(1)}%`}
              </span>
            </div>
          </div>
        )}
        {data && (
          <p className="settings-help chart-scope" data-testid="chart-scope">
            {scope} · {formatInt(data.kpis.count)} games of {formatInt(data.catalog_total)} in the
            catalog · {data.revenue_model} · as of {new Date(data.as_of).toLocaleString()}
          </p>
        )}

        {data && data.kpis.count === 0 && (
          <p className="settings-help">No games in this scope. Widen the filters above.</p>
        )}

        {data && data.kpis.count > 0 && (
          <div className="chart-grid">
            <ChartCard
              id="chart-revenue"
              title="Estimated revenue distribution"
              subtitle={`Games per revenue band (log-spaced bands) · ${formatInt(data.kpis.count)} games`}
              table={<DataTable head={["Est. revenue", "Games"]} rows={bins.map((b) => [b.label, formatInt(b.count)])} />}
            >
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={bins} margin={{ top: 16, right: 12, bottom: 4, left: 0 }} barCategoryGap={2}>
                  <CartesianGrid stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="label" interval={0} angle={-30} textAnchor="end" height={54} {...axisProps} />
                  <YAxis tickFormatter={compactNumber} width={48} allowDecimals={false} {...axisProps} />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    content={({ active: on, payload }) => {
                      const b = payload?.[0]?.payload as (typeof bins)[number] | undefined;
                      if (!on || !b) return null;
                      return <TipBox title={b.label} rows={[["games", formatInt(b.count)]]} />;
                    }}
                  />
                  <Bar dataKey="count" fill={CHART.series1} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              id="chart-years"
              title="Games per release year"
              subtitle="Count per year in scope; median revenue in the tooltip and table"
              table={
                <DataTable
                  head={["Year", "Games", "Median est. revenue"]}
                  rows={data.years.map((y) => [y.year, formatInt(y.count), compactUsd(y.median_revenue)])}
                />
              }
            >
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.years} margin={{ top: 16, right: 12, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke={CHART.grid} vertical={false} />
                  <XAxis dataKey="year" {...axisProps} />
                  <YAxis tickFormatter={compactNumber} width={48} allowDecimals={false} {...axisProps} />
                  <Tooltip
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                    content={({ active: on, payload }) => {
                      const y = payload?.[0]?.payload as ChartsResponse["years"][number] | undefined;
                      if (!on || !y) return null;
                      return (
                        <TipBox
                          title={String(y.year)}
                          rows={[
                            ["games", formatInt(y.count)],
                            ["median est. revenue", compactUsd(y.median_revenue)],
                          ]}
                        />
                      );
                    }}
                  />
                  <Bar dataKey="count" fill={CHART.series1} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              id="chart-price"
              wide
              title="Price vs estimated revenue"
              subtitle={`Each dot is a game${sampled ? ` (showing ${formatInt(data.points.length)} of ${formatInt(data.points_total)}, Studies always shown)` : ""} · log revenue scale · click a dot to open it`}
              table={
                <DataTable
                  head={["Game", "Year", "Price", "Est. revenue", "Reviews", "In Studies"]}
                  rows={data.points
                    .slice()
                    .sort((a, b) => b.revenue - a.revenue)
                    .slice(0, 200)
                    .map((p) => [p.name, p.year, formatCurrency(p.price), compactUsd(p.revenue), formatInt(p.reviews), p.in_studies ? "yes" : ""])}
                />
              }
            >
              <ResponsiveContainer width="100%" height={340}>
                <ScatterChart margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
                  <CartesianGrid stroke={CHART.grid} />
                  <XAxis
                    type="number"
                    dataKey="price"
                    name="Price"
                    tickFormatter={(v: number) => `$${v}`}
                    domain={[0, "dataMax"]}
                    {...axisProps}
                  />
                  <YAxis
                    type="number"
                    dataKey="revenue"
                    name="Est. revenue"
                    scale="log"
                    domain={logDomain(revenueTicks)}
                    ticks={revenueTicks}
                    tickFormatter={compactUsd}
                    allowDataOverflow
                    width={60}
                    {...axisProps}
                  />
                  <ZAxis range={[40, 40]} />
                  <Tooltip cursor={false} content={pointTip} />
                  <Legend wrapperStyle={{ color: CHART.muted, fontSize: 12 }} />
                  <Scatter name="Games" data={scatter.all} fill={CHART.series1} shape={Dot(CHART.series1, 3, 0.55)} onClick={openPoint} isAnimationActive={false} />
                  <Scatter name="In Studies" data={scatter.studies} fill={CHART.series2} shape={Dot(CHART.series2, 5, 1)} onClick={openPoint} isAnimationActive={false} />
                </ScatterChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              id="chart-tags"
              wide
              title="Tags by median estimated revenue"
              subtitle={`The 20 most common tags with at least ${request.min_tag_count} games, ranked by median · sample size in brackets`}
              table={
                <DataTable
                  head={["Tag", "Games", "Median est. revenue", "Median reviews", "Median positive"]}
                  rows={tags.map((t) => [t.tag, formatInt(t.count), compactUsd(t.median_revenue), formatInt(Math.round(t.median_reviews)), `${t.median_score.toFixed(1)}%`])}
                />
              }
            >
              {tags.length === 0 ? (
                <p className="settings-help">No tag has enough games in this scope.</p>
              ) : (
                <ResponsiveContainer width="100%" height={Math.max(200, tags.length * 26 + 40)}>
                  <BarChart
                    layout="vertical"
                    data={tags.map((t) => ({ ...t, label: `${t.tag} (${formatInt(t.count)})` }))}
                    margin={{ top: 8, right: 56, bottom: 4, left: 8 }}
                    barCategoryGap={4}
                  >
                    <CartesianGrid stroke={CHART.grid} horizontal={false} />
                    <XAxis type="number" tickFormatter={compactUsd} {...axisProps} />
                    <YAxis type="category" dataKey="label" width={190} interval={0} {...axisProps} />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      content={({ active: on, payload }) => {
                        const t = payload?.[0]?.payload as ChartsResponse["tags"][number] | undefined;
                        if (!on || !t) return null;
                        return (
                          <TipBox
                            title={t.tag}
                            rows={[
                              ["median est. revenue", compactUsd(t.median_revenue)],
                              ["games", formatInt(t.count)],
                              ["median reviews", formatInt(Math.round(t.median_reviews))],
                              ["median positive", `${t.median_score.toFixed(1)}%`],
                            ]}
                          />
                        );
                      }}
                    />
                    <Bar
                      dataKey="median_revenue"
                      fill={CHART.series1}
                      radius={[0, 4, 4, 0]}
                      maxBarSize={18}
                      isAnimationActive={false}
                      label={{ position: "right", fill: CHART.muted, fontSize: 11, formatter: (v: unknown) => compactUsd(Number(v)) }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard
              id="chart-score"
              title="Review count vs positive score"
              subtitle="Log review scale. Revenue is derived from review count, so the two are mechanically linked."
              table={
                <DataTable
                  head={["Game", "Reviews", "Positive"]}
                  rows={scatter.reviews
                    .slice()
                    .sort((a, b) => b.reviews - a.reviews)
                    .slice(0, 200)
                    .map((p) => [p.name, formatInt(p.reviews), `${p.score.toFixed(1)}%`])}
                />
              }
            >
              <ResponsiveContainer width="100%" height={280}>
                <ScatterChart margin={{ top: 16, right: 24, bottom: 8, left: 0 }}>
                  <CartesianGrid stroke={CHART.grid} />
                  <XAxis
                    type="number"
                    dataKey="reviews"
                    scale="log"
                    domain={logDomain(reviewTicks)}
                    ticks={reviewTicks}
                    tickFormatter={compactNumber}
                    allowDataOverflow
                    {...axisProps}
                  />
                  <YAxis type="number" dataKey="score" domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} width={44} {...axisProps} />
                  <ZAxis range={[30, 30]} />
                  <Tooltip cursor={false} content={pointTip} />
                  <Scatter data={scatter.reviews} shape={Dot(CHART.series1, 3, 0.5)} onClick={openPoint} isAnimationActive={false} />
                </ScatterChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard
              id="chart-history"
              title={`Review history${currentGame ? `: ${currentGame.name}` : ""}`}
              subtitle="Total reviews (all languages) at each Steam update of this game"
              table={<GameHistory appid={currentGame?.appid ?? null} refreshToken={refreshToken} asTable />}
            >
              <GameHistory appid={currentGame?.appid ?? null} refreshToken={refreshToken} />
            </ChartCard>
          </div>
        )}
      </div>
    </div>
  );
}
