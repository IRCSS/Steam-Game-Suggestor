import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { ApiError, api, type GameReport, type MetaResponse, type StudyFilters } from "./api/client";
import { SettingsDialog } from "./components/SettingsDialog";
import { Toast, useToast } from "./components/Toast";
import { formatInt } from "./lib/format";
import { DataPage } from "./pages/DataPage";
import { SuggestPage } from "./pages/SuggestPage";

// Recharts is only loaded when the Charts tab is opened (keeps the Suggest tab fast).
const ChartsPage = lazy(() => import("./pages/ChartsPage"));

export type Tab = "suggest" | "charts" | "data";
const TABS: { id: Tab; label: string }[] = [
  { id: "suggest", label: "Suggest" },
  { id: "charts", label: "Charts" },
  { id: "data", label: "Data" },
];

function tabFromHash(): Tab {
  const id = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === id) ? (id as Tab) : "suggest";
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; meta: MetaResponse };

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        fill="currentColor"
        d="M19.14 12.94a7.07 7.07 0 0 0 .06-.94 7.07 7.07 0 0 0-.06-.94l2.03-1.58a.48.48 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.03 7.03 0 0 0-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84a.48.48 0 0 0-.48.41l-.36 2.54a7.03 7.03 0 0 0-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87a.48.48 0 0 0 .12.61l2.03 1.58a7.07 7.07 0 0 0-.06.94c0 .32.02.63.06.94l-2.03 1.58a.48.48 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54c.05.24.25.41.48.41h3.84c.24 0 .44-.17.48-.41l.36-2.54a7.03 7.03 0 0 0 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.48.48 0 0 0-.12-.61l-2.03-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z"
      />
    </svg>
  );
}

function Shell({ meta, onMetaChanged }: { meta: MetaResponse; onMetaChanged: () => void }) {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set([tabFromHash()]));
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [currentGame, setCurrentGame] = useState<GameReport | null>(null);
  const [suggestFilters, setSuggestFilters] = useState<StudyFilters | null>(null);
  const [openRequest, setOpenRequest] = useState<{ appid: number; nonce: number } | null>(null);
  const toast = useToast();

  useEffect(() => {
    const onHash = () => {
      const next = tabFromHash();
      setTab(next);
      setVisited((v) => (v.has(next) ? v : new Set(v).add(next))); // render tabs opened by URL
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const open = (next: Tab) => {
    setTab(next);
    setVisited((v) => new Set(v).add(next));
    if (window.location.hash !== `#${next}`) window.history.replaceState(null, "", `#${next}`);
  };

  /** Something changed the data (settings saved, job finished): refresh every tab. */
  const dataChanged = useCallback(() => {
    onMetaChanged();
    setRefreshToken((t) => t + 1);
  }, [onMetaChanged]);

  const ds = meta.dataset;
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Steam market study tool</p>
          <h1>Indie Case Study Suggester</h1>
          <p className="intro">
            Filter the recent Steam market and draw a random game to study its positioning,
            pricing, commercial outcome, tags, artwork, review score, and store pitch.
          </p>
        </div>
        <div className="topbar-side">
          <div className="dataset-badge" title={ds.scope_label}>
            {formatInt(ds.qualified_games)} qualified games
            <span className="dataset-badge-sub">
              of {formatInt(ds.total_games)} in catalog · {ds.scope_label}
            </span>
          </div>
          <button
            id="settingsButton"
            className="gear-button"
            type="button"
            aria-label="Settings"
            title="Settings"
            onClick={() => setSettingsOpen(true)}
          >
            <GearIcon />
          </button>
        </div>
      </header>

      <nav className="tab-bar" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            role="tab"
            type="button"
            className={`tab${tab === t.id ? " active" : ""}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => open(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div id="panel-suggest" role="tabpanel" aria-labelledby="tab-suggest" hidden={tab !== "suggest"}>
        <SuggestPage
          meta={meta}
          notify={toast.show}
          refreshToken={refreshToken}
          onGameChange={setCurrentGame}
          onFiltersChange={setSuggestFilters}
          openRequest={openRequest}
        />
      </div>
      {visited.has("charts") && (
        <div id="panel-charts" role="tabpanel" aria-labelledby="tab-charts" hidden={tab !== "charts"}>
          <Suspense fallback={<p className="settings-help">Loading charts…</p>}>
            <ChartsPage
              meta={meta}
              active={tab === "charts"}
              refreshToken={refreshToken}
              currentGame={currentGame}
              suggestFilters={suggestFilters}
              onOpenGame={(appid) => {
                setOpenRequest({ appid, nonce: Date.now() });
                open("suggest");
              }}
            />
          </Suspense>
        </div>
      )}
      {visited.has("data") && (
        <div id="panel-data" role="tabpanel" aria-labelledby="tab-data" hidden={tab !== "data"}>
          <DataPage
            active={tab === "data"}
            meta={meta}
            notify={toast.show}
            onDataChanged={dataChanged}
            onOpenSettings={() => setSettingsOpen(true)}
          />
        </div>
      )}

      {settingsOpen && (
        <SettingsDialog
          onClose={() => setSettingsOpen(false)}
          onSaved={dataChanged}
          notify={toast.show}
        />
      )}
      <Toast message={toast.message} visible={toast.visible} />
    </main>
  );
}

export function App() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .meta()
      .then((meta) => !cancelled && setState({ kind: "ready", meta }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiError ? error.message : "The local backend is not reachable.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const refreshMeta = useCallback(() => {
    api
      .meta()
      .then((meta) => setState({ kind: "ready", meta }))
      .catch(() => undefined);
  }, []);

  if (state.kind === "ready" && state.meta.dataset.total_games > 0) {
    return <Shell meta={state.meta} onMetaChanged={refreshMeta} />;
  }

  const needsImport = state.kind === "ready";
  return (
    <main className="app-shell">
      <div className="panel empty-state" role={state.kind === "error" ? "alert" : "status"}>
        <div>
          <div className="empty-icon">◈</div>
          {state.kind === "loading" && <h2>Loading local catalog…</h2>}
          {state.kind === "error" && (
            <>
              <h2>Backend unavailable</h2>
              <p>
                {state.message} Start it with <code>npm run dev</code> (or{" "}
                <code>npm run dev-api</code>) and retry.
              </p>
            </>
          )}
          {needsImport && (
            <>
              <h2>No data imported yet</h2>
              <p>
                Run <code>npm run import-data</code> to load the legacy dataset, then retry.
              </p>
            </>
          )}
          {state.kind !== "loading" && (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setState({ kind: "loading" });
                setAttempt((a) => a + 1);
              }}
            >
              Retry
            </button>
          )}
        </div>
      </div>
    </main>
  );
}
