import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  api,
  type DataStatus,
  type JobPreview,
  type JobRequest,
  type JobView,
  type MetaResponse,
} from "../api/client";
import { formatCompactCurrency, formatInt } from "../lib/format";

interface Props {
  active: boolean;
  meta: MetaResponse;
  notify: (message: string) => void;
  onDataChanged: () => void;
  onOpenSettings: () => void;
}

type Part = "reviews" | "store" | "tags";
type Scope = "qualified" | "all" | "studies";

export function duration(seconds: number): string {
  if (seconds < 90) return `${Math.max(1, Math.round(seconds))} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

function when(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

const COUNTER_LABELS: Record<string, string> = {
  reviews_updated: "reviews updated",
  store_updated: "store info updated",
  tags_updated: "tags updated",
  unavailable: "not on the store",
  listed: "new AppIDs listed",
  screened: "screened",
  below_floor: "below floor",
  added_qualified: "new qualified games",
  not_released_or_not_game: "unreleased / not a game",
  retries: "retries",
  errors: "errors",
};

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="metric stat-tile">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

function YearPicker({
  years,
  value,
  onChange,
  idPrefix,
}: {
  years: number[];
  value: number[];
  onChange: (years: number[]) => void;
  idPrefix: string;
}) {
  return (
    <div className="chip-row" role="group" aria-label="Release years (none selected = all)">
      {years.map((year) => {
        const on = value.includes(year);
        return (
          <button
            key={year}
            id={`${idPrefix}-year-${year}`}
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

/** Live estimate for a job request (debounced). */
function usePreview(request: JobRequest | null, version: number) {
  const [preview, setPreview] = useState<JobPreview | null>(null);
  const key = JSON.stringify(request);
  useEffect(() => {
    if (!request) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .previewJob(request, controller.signal)
        .then(setPreview)
        .catch(() => undefined);
    }, 200);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures `request`
  }, [key, version]);
  return preview;
}

function ActionCard(props: {
  id: string;
  title: string;
  description: ReactNode;
  children?: ReactNode;
  preview: JobPreview | null;
  startLabel: string;
  disabled: boolean;
  disabledReason?: string;
  onStart: () => void;
}) {
  const { preview } = props;
  const nothing = preview !== null && preview.items === 0;
  return (
    <section className="panel data-card" aria-labelledby={`${props.id}-title`}>
      <h2 id={`${props.id}-title`} className="data-card-title">
        {props.title}
      </h2>
      <p className="settings-help">{props.description}</p>
      {props.children}
      <div className="data-card-footer">
        <span className="data-estimate" data-testid={`${props.id}-estimate`}>
          {preview === null
            ? "Estimating…"
            : nothing
              ? "Nothing to do - everything in scope is up to date."
              : `${formatInt(preview.items)} games · ≈ ${formatInt(preview.requests)} requests · ≈ ${duration(preview.seconds)}`}
        </span>
        <button
          id={`${props.id}-start`}
          className="primary-button"
          type="button"
          disabled={props.disabled || nothing}
          title={props.disabledReason}
          onClick={props.onStart}
        >
          {props.startLabel}
        </button>
      </div>
      {preview?.notes.map((note) => (
        <p className="settings-help" key={note}>
          {note}
        </p>
      ))}
    </section>
  );
}

function JobPanel({ job, onCancel }: { job: JobView; onCancel: () => void }) {
  if (job.state === "idle") return null;
  const running = job.state === "running";
  const percent = job.total ? Math.round((100 * job.done) / job.total) : 0;
  const counters = Object.entries(job.counters).filter(([, n]) => n > 0);
  return (
    <section className="panel job-panel" aria-live="polite" data-testid="job-panel">
      <div className="sidebar-heading">
        <h2>
          {job.label}
          <span className={`job-state ${job.state}`}>{job.state}</span>
        </h2>
        {running && (
          <button id="cancelJobButton" className="secondary-button" type="button" onClick={onCancel}>
            Stop
          </button>
        )}
      </div>
      {running && (
        <>
          <div className="progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <div className="progress-bar" style={{ width: `${percent}%` }} />
          </div>
          <p className="settings-help">
            {formatInt(job.done)} / {formatInt(job.total)} games · {formatInt(job.requests)} requests
            {job.eta_seconds !== null && job.eta_seconds !== undefined
              ? ` · about ${duration(job.eta_seconds)} left`
              : ""}
            . Keep the app open; if it closes, start again to continue where it stopped.
          </p>
        </>
      )}
      {!running && <p className="settings-help">{job.message}</p>}
      {counters.length > 0 && (
        <div className="chip-row">
          {counters.map(([key, n]) => (
            <span className="chip static" key={key}>
              {formatInt(n)} {COUNTER_LABELS[key] ?? key}
            </span>
          ))}
        </div>
      )}
      {job.recent.length > 0 && (
        <details className="job-log" open={running}>
          <summary>Log</summary>
          <ol>
            {[...job.recent].reverse().map((line, i) => (
              <li key={`${i}-${line}`}>{line}</li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}

export function DataPage({ active, meta, notify, onDataChanged, onOpenSettings }: Props) {
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [job, setJob] = useState<JobView | null>(null);
  const [version, setVersion] = useState(0);
  const lastState = useRef<string | null>(null);

  // Refresh options (defaults: qualified >= floor, all years, reviews + store, skip if < 7 days old)
  const [scope, setScope] = useState<Scope>("qualified");
  const [years, setYears] = useState<number[]>([]);
  const [parts, setParts] = useState<Part[]>(["reviews", "store"]);
  const [staleDays, setStaleDays] = useState("7");
  // Discover options
  const [maxNew, setMaxNew] = useState("500");
  const [fetchTags, setFetchTags] = useState(true);
  // Languages options
  const [langScope, setLangScope] = useState<"qualified" | "all">("qualified");
  const [langYears, setLangYears] = useState<number[]>([]);
  // Single AppID
  const [appid, setAppid] = useState("");

  const loadStatus = useCallback(() => {
    api
      .dataStatus()
      .then((s) => {
        setStatus(s);
        setJob(s.job);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (active) loadStatus();
  }, [active, loadStatus]);

  // Poll the running job; when it ends, refresh everything that depends on the data.
  const running = job?.state === "running";
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      api
        .currentJob()
        .then(setJob)
        .catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!job) return;
    if (lastState.current === "running" && job.state !== "running") {
      notify(`${job.label}: ${job.state === "completed" ? job.message : job.state}`);
      onDataChanged();
      loadStatus();
      setVersion((v) => v + 1);
    }
    lastState.current = job.state;
  }, [job, notify, onDataChanged, loadStatus]);

  const refreshRequest: JobRequest = {
    kind: "refresh",
    refresh: {
      scope,
      years,
      parts,
      stale_days: Number(staleDays) || 0,
      only_missing_languages: false,
    },
  };
  const discoverRequest: JobRequest = {
    kind: "discover",
    discover: { max_new: Math.max(1, Number(maxNew) || 500), fetch_tags: fetchTags },
  };
  const languageRequest: JobRequest = {
    kind: "languages",
    refresh: {
      scope: langScope,
      years: langYears,
      parts: ["store"],
      stale_days: 0,
      only_missing_languages: true,
    },
  };
  const refreshPreview = usePreview(refreshRequest, version);
  const discoverPreview = usePreview(discoverRequest, version);
  const languagePreview = usePreview(languageRequest, version);

  const start = async (request: JobRequest) => {
    try {
      const started = await api.startJob(request);
      lastState.current = "running";
      setJob(started);
    } catch (error) {
      notify(error instanceof ApiError ? error.message : "Could not start the job.");
    }
  };

  const testKey = async () => {
    try {
      const result = await api.testSteamKey();
      notify(result.message);
    } catch {
      notify("Could not test the key.");
    }
  };

  const togglePart = (part: Part) =>
    setParts((current) =>
      current.includes(part) ? current.filter((p) => p !== part) : [...current, part],
    );

  const offline = status?.offline ?? false;
  const busy = running || offline;
  const busyReason = offline
    ? "Offline mode is on (Settings)"
    : running
      ? "Another data job is running"
      : undefined;
  const floor = formatCompactCurrency(meta.dataset.qualification_threshold_usd);

  return (
    <div className="data-page">
      {status && (
        <div className="metric-grid data-stats" data-testid="data-stats">
          <StatTile label="Games in catalog" value={formatInt(status.total_games)} />
          <StatTile label={`Qualified (≥ ${floor})`} value={formatInt(status.qualified_games)} />
          <StatTile
            label="Updated from Steam"
            value={formatInt(status.refreshed + status.discovered)}
            note={`${formatInt(status.discovered)} newly added`}
          />
          <StatTile label="Languages known" value={formatInt(status.languages_known)} />
          <StatTile label="Last update" value={when(status.last_update)} />
          <StatTile
            label="Newest AppID known"
            value={String(status.discovery_cursor_appid)}
            note={
              status.listed_not_screened
                ? `${formatInt(status.listed_not_screened)} listed, not yet screened`
                : undefined
            }
          />
        </div>
      )}
      {offline && (
        <p className="settings-warning" role="alert">
          Offline mode is on - Steam requests are disabled. Turn it off in Settings to update data.
        </p>
      )}

      {job && <JobPanel job={job} onCancel={() => api.cancelJob().then(setJob)} />}

      <div className="data-grid">
        <ActionCard
          id="refresh"
          title="Update existing games"
          description={
            <>
              Re-reads review counts (all languages) and store info (price, release date,
              languages) for games already in the catalog. Estimated revenue and yearly ranks are
              recalculated. Earlier values are kept for the trend chart.
            </>
          }
          preview={refreshPreview}
          startLabel="Update games"
          disabled={busy || parts.length === 0}
          disabledReason={busyReason}
          onStart={() => start(refreshRequest)}
        >
          <fieldset className="data-options">
            <legend className="input-caption">Which games</legend>
            {(
              [
                ["qualified", `Qualified games (est. revenue ≥ ${floor})`],
                ["all", "All games in the catalog"],
                ["studies", "Only my Studies"],
              ] as [Scope, string][]
            ).map(([value, label]) => (
              <label className="settings-check" key={value}>
                <input
                  type="radio"
                  name="refresh-scope"
                  value={value}
                  checked={scope === value}
                  onChange={() => setScope(value)}
                />
                {label}
              </label>
            ))}
            <span className="input-caption">Release years</span>
            <YearPicker years={meta.years} value={years} onChange={setYears} idPrefix="refresh" />
            <span className="input-caption">What to update</span>
            {(
              [
                ["reviews", "Review counts"],
                ["store", "Store info: price, release date, languages"],
                ["tags", "Tags (SteamSpy, ~1 request/second)"],
              ] as [Part, string][]
            ).map(([part, label]) => (
              <label className="settings-check" key={part}>
                <input
                  type="checkbox"
                  id={`refresh-part-${part}`}
                  checked={parts.includes(part)}
                  onChange={() => togglePart(part)}
                />
                {label}
              </label>
            ))}
            <label className="settings-field narrow">
              <span className="input-caption">Skip games updated within (days)</span>
              <input
                id="refresh-stale"
                type="number"
                min={0}
                value={staleDays}
                onChange={(e) => setStaleDays(e.target.value)}
              />
            </label>
          </fieldset>
        </ActionCard>

        <ActionCard
          id="discover"
          title="Add new games"
          description={
            <>
              Reads Steam's official list of games with an AppID above{" "}
              {status ? <strong>{status.discovery_cursor_appid}</strong> : "the newest known"} and
              checks each one: games whose review count can never reach the {floor} floor are
              skipped after one request; promising ones get store info and tags. New AppIDs are
              usually, but not always, newer releases.
            </>
          }
          preview={discoverPreview}
          startLabel="Find new games"
          disabled={busy || !status?.steam_api_key_set}
          disabledReason={!status?.steam_api_key_set ? "Needs a Steam Web API key" : busyReason}
          onStart={() => start(discoverRequest)}
        >
          <div className="data-options">
            <p className="settings-help">
              Steam Web API key:{" "}
              {status?.steam_api_key_set ? (
                <>
                  set{" "}
                  <button className="link-button" type="button" onClick={testKey}>
                    Test key
                  </button>
                </>
              ) : (
                <>
                  <strong>not set</strong> - required for this step (free at
                  steamcommunity.com/dev/apikey).{" "}
                  <button className="link-button" type="button" onClick={onOpenSettings}>
                    Open Settings
                  </button>
                </>
              )}
            </p>
            <label className="settings-field narrow">
              <span className="input-caption">Check at most this many new AppIDs per run</span>
              <input
                id="discover-max"
                type="number"
                min={1}
                value={maxNew}
                onChange={(e) => setMaxNew(e.target.value)}
              />
            </label>
            <label className="settings-check">
              <input
                type="checkbox"
                checked={fetchTags}
                onChange={(e) => setFetchTags(e.target.checked)}
              />
              Fetch tags for new qualified games (SteamSpy)
            </label>
          </div>
        </ActionCard>

        <ActionCard
          id="languages"
          title="Look up languages"
          description={
            <>
              Fetches supported languages for games that don't have them yet, for the{" "}
              <em>Must support English</em> filter. Shared with every PC using this data folder.
            </>
          }
          preview={languagePreview}
          startLabel="Look up languages"
          disabled={busy}
          disabledReason={busyReason}
          onStart={() => start(languageRequest)}
        >
          <fieldset className="data-options">
            <legend className="input-caption">Which games</legend>
            {(
              [
                ["qualified", `Qualified games (≥ ${floor})`],
                ["all", "All games in the catalog"],
              ] as ["qualified" | "all", string][]
            ).map(([value, label]) => (
              <label className="settings-check" key={value}>
                <input
                  type="radio"
                  name="language-scope"
                  checked={langScope === value}
                  onChange={() => setLangScope(value)}
                />
                {label}
              </label>
            ))}
            <span className="input-caption">Release years</span>
            <YearPicker years={meta.years} value={langYears} onChange={setLangYears} idPrefix="lang" />
          </fieldset>
        </ActionCard>

        <section className="panel data-card" aria-labelledby="single-title">
          <h2 id="single-title" className="data-card-title">
            Update one AppID
          </h2>
          <p className="settings-help">
            Fetches reviews, store info and tags for one game now - also for AppIDs not yet in
            the catalog (added if Steam lists it as a released game with a price).
          </p>
          <div className="data-card-footer">
            <input
              id="single-appid"
              type="text"
              inputMode="numeric"
              placeholder="AppID, e.g. 1794680"
              aria-label="AppID to update"
              value={appid}
              onChange={(e) => setAppid(e.target.value.replace(/\D/g, ""))}
            />
            <button
              id="single-start"
              className="primary-button"
              type="button"
              disabled={busy || !appid}
              title={busyReason}
              onClick={() => start({ kind: "app", appid: Number(appid) })}
            >
              Update
            </button>
          </div>
        </section>
      </div>

      {status && (
        <p className="settings-help data-footnote">
          Data folder: <code>{status.data_dir}</code> · updates from this PC go to{" "}
          {status.observation_files.length
            ? status.observation_files.map((f) => `${f.file} (${Math.round(f.bytes / 1024)} KB)`).join(", ")
            : "observations/steam-<pc>.jsonl"}
          . Revenue stays an estimate (reviews × 45 × price).
        </p>
      )}
    </div>
  );
}
