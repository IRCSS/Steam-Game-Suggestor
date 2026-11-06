import { useEffect, useState } from "react";
import { ApiError, api, type MetaResponse } from "./api/client";
import { SuggestPage } from "./pages/SuggestPage";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; meta: MetaResponse };

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

  if (state.kind === "ready" && state.meta.dataset.total_games > 0) {
    const refreshMeta = () => {
      api
        .meta()
        .then((meta) => setState({ kind: "ready", meta }))
        .catch(() => undefined);
    };
    return <SuggestPage meta={state.meta} onMetaChanged={refreshMeta} />;
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
