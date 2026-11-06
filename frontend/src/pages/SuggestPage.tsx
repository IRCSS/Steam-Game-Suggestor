import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  api,
  type CountResponse,
  type GameReport,
  type GameSummary,
  type MetaResponse,
  type SuggestionQuery,
} from "../api/client";
import { FilterSidebar } from "../components/FilterSidebar";
import { GameCard } from "../components/GameCard";
import { GameLookup } from "../components/GameLookup";
import { HistoryList } from "../components/HistoryList";
import { Toast, useToast } from "../components/Toast";
import { type FilterForm, formFromDefaults, formToApi } from "../lib/filters";
import { formatInt } from "../lib/format";
import { SESSION_ID } from "../lib/session";

interface Props {
  meta: MetaResponse;
  sessionId?: string;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Unexpected error.";
}

export function SuggestPage({ meta, sessionId = SESSION_ID }: Props) {
  const defaults = useMemo(
    () => formFromDefaults(meta.default_filters, meta.default_avoid_repeats),
    [meta],
  );
  const [form, setForm] = useState<FilterForm>(defaults);
  const [resetKey, setResetKey] = useState(0);
  const [count, setCount] = useState<CountResponse | null>(null);
  const [game, setGame] = useState<GameReport | null>(null);
  const [history, setHistory] = useState<GameSummary[]>([]);
  const [viewVersion, setViewVersion] = useState(0);
  const [lookup, setLookup] = useState("");
  const toast = useToast();

  const query: SuggestionQuery = useMemo(
    () => ({
      session_id: sessionId,
      filters: formToApi(form),
      avoid_repeats: form.avoidRepeats,
      include_below_threshold: form.includeBelowThreshold,
    }),
    [form, sessionId],
  );

  // Matching count refreshes whenever filters or the session's seen-set change.
  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .count(query, controller.signal)
        .then(setCount)
        .catch((error: unknown) => {
          if (!(error instanceof DOMException)) setCount(null);
        });
    }, 120);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, viewVersion]);

  const show = useCallback(
    (report: GameReport, newHistory: GameSummary[]) => {
      setGame(report);
      setHistory(newHistory);
      setViewVersion((v) => v + 1);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [],
  );

  const showManual = useCallback(
    async (report: GameReport) => {
      const h = await api.recordView(sessionId, report.appid);
      setLookup(report.name);
      show(report, h.items);
    },
    [sessionId, show],
  );

  const suggest = async () => {
    try {
      const result = await api.suggest(query);
      if (result.repeat_history_reset) {
        toast.show("All matching games had been shown. Repeat history reset.");
      }
      if (!result.game) {
        toast.show("No games match these filters.");
        return;
      }
      const h = await api.history(sessionId);
      show(result.game, h.items);
    } catch (error) {
      toast.show(errorText(error));
    }
  };

  const loadSpecific = async () => {
    if (!lookup.trim()) {
      toast.show("No matching game found.");
      return;
    }
    try {
      const report = await api.resolve(lookup);
      await showManual(report);
      toast.show(`Loaded ${report.name}.`);
    } catch (error) {
      toast.show(error instanceof ApiError && error.status === 404
        ? "No matching game found."
        : errorText(error));
    }
  };

  const openGame = async (appid: number) => {
    try {
      await showManual(await api.game(appid));
    } catch (error) {
      toast.show(errorText(error));
    }
  };

  const reset = () => {
    setForm(defaults);
    setResetKey((k) => k + 1);
    toast.show("Filters reset.");
  };

  const clearHistory = async () => {
    try {
      await api.clearHistory(sessionId);
      setHistory([]);
      setViewVersion((v) => v + 1);
      toast.show("Session history cleared.");
    } catch (error) {
      toast.show(errorText(error));
    }
  };

  const copyAppId = async () => {
    if (!game) return;
    const text = String(game.appid);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    toast.show(`Copied AppID ${text}.`);
  };

  let matchLabel = "Calculating…";
  let canSuggest = false;
  if (count) {
    if (count.all_seen) {
      matchLabel = "All seen";
      canSuggest = true;
    } else {
      matchLabel = `${formatInt(count.count)} matches`;
      canSuggest = count.count > 0;
    }
  }

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
        <div className="dataset-badge" title={ds.scope_label}>
          {formatInt(ds.qualified_games)} qualified games
          <span className="dataset-badge-sub">
            of {formatInt(ds.total_games)} imported · {ds.scope_label}
          </span>
        </div>
      </header>

      <div className="layout">
        <FilterSidebar
          years={meta.years}
          tags={meta.tags}
          form={form}
          thresholdUsd={ds.qualification_threshold_usd}
          matchLabel={matchLabel}
          canSuggest={canSuggest}
          resetKey={resetKey}
          onChange={setForm}
          onSuggest={suggest}
          onReset={reset}
          lookup={
            <GameLookup
              value={lookup}
              onValueChange={setLookup}
              onPick={openGame}
              onLoad={loadSpecific}
            />
          }
        />

        <section className="result-column">
          {game ? (
            <GameCard game={game} onAnother={suggest} onCopyAppId={copyAppId} />
          ) : (
            <div id="emptyState" className="panel empty-state">
              <div>
                <div className="empty-icon">◈</div>
                <h2>Your next case study is waiting</h2>
                <p>
                  The default segment contains games earning an estimated $150K–$800K. Narrow the
                  market by year, review score, price, rank, percentile, or Steam tags.
                </p>
              </div>
            </div>
          )}
          <HistoryList items={history} onClear={clearHistory} onOpen={openGame} />
        </section>
      </div>
      <Toast message={toast.message} visible={toast.visible} />
    </main>
  );
}
