import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type CountResponse,
  type GameReport,
  type GameSummary,
  type LanguageStatus,
  type MetaResponse,
  type StudyItem,
  type SuggestionQuery,
} from "../api/client";
import { ExportCard } from "../components/ExportCard";
import { SettingsDialog } from "../components/SettingsDialog";
import { StudiesList } from "../components/StudiesList";
import { renderJpeg, waitFor } from "../lib/exportJpeg";
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
  onMetaChanged?: () => void;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Unexpected error.";
}

export function SuggestPage({ meta, sessionId = SESSION_ID, onMetaChanged }: Props) {
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
  const [studies, setStudies] = useState<StudyItem[]>([]);
  const [languages, setLanguages] = useState<LanguageStatus | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [researchOpen, setResearchOpen] = useState(false);
  const [busy, setBusy] = useState<"study" | "export" | null>(null);
  const [exporting, setExporting] = useState<{ game: GameReport; at: Date } | null>(null);
  const exportRef = useRef<HTMLDivElement>(null);
  const artworkSettled = useRef<() => void>(() => undefined);
  const toast = useToast();

  const refreshSide = useCallback(() => {
    api.studies().then((r) => setStudies(r.items)).catch(() => undefined);
    api.languageStatus().then(setLanguages).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshSide();
  }, [refreshSide]);

  const query: SuggestionQuery = useMemo(
    () => ({
      session_id: sessionId,
      filters: formToApi(form),
      avoid_repeats: form.avoidRepeats,
      include_below_threshold: form.includeBelowThreshold,
      exclude_studies: form.excludeStudies,
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
      setResearchOpen(false);
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

  const toggleStudy = async () => {
    if (!game) return;
    if (game.study.in_studies && !window.confirm(`Remove "${game.name}" from Studies?`)) return;
    setBusy("study");
    try {
      const updated = game.study.in_studies
        ? await api.removeStudy(game.appid)
        : await api.addStudy(game.appid);
      setGame(updated);
      setViewVersion((v) => v + 1);
      refreshSide();
      toast.show(
        updated.study.in_studies
          ? `Added ${game.name} to Studies - it won't be suggested again.`
          : `Removed ${game.name} from Studies.`,
      );
    } catch (error) {
      toast.show(errorText(error));
    } finally {
      setBusy(null);
    }
  };

  const exportJpeg = async () => {
    if (!game || busy === "export") return;
    setBusy("export");
    try {
      const artwork = waitFor((done) => {
        artworkSettled.current = done;
      });
      setExporting({ game, at: new Date() });
      await artwork;
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      if (!exportRef.current) throw new Error("export view not ready");
      const dataUrl = await renderJpeg(exportRef.current);
      const saved = await api.exportJpeg(game.appid, dataUrl);
      const folder = saved.folder.split(/[\\/]/).pop() ?? saved.folder;
      toast.show(`Saved to ${folder}: ${saved.file_name}`);
    } catch (error) {
      toast.show(error instanceof ApiError ? error.message : "Could not export the JPG.");
    } finally {
      setExporting(null);
      setBusy(null);
    }
  };

  let languageNote = "Excludes games known to have no English support.";
  if (languages) {
    const unknown = languages.qualified_games - languages.known_qualified;
    languageNote =
      unknown > 0
        ? `Excludes games without English. Checked ${formatInt(languages.known_qualified)} of ${formatInt(languages.qualified_games)} qualified games; unchecked games stay in (look them up in Settings).`
        : `Excludes games without English (${formatInt(languages.no_english)} known).`;
  }

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
        <div className="topbar-side">
          <div className="dataset-badge" title={ds.scope_label}>
            {formatInt(ds.qualified_games)} qualified games
            <span className="dataset-badge-sub">
              of {formatInt(ds.total_games)} imported · {ds.scope_label}
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
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path
                fill="currentColor"
                d="M19.14 12.94a7.07 7.07 0 0 0 .06-.94 7.07 7.07 0 0 0-.06-.94l2.03-1.58a.48.48 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96a7.03 7.03 0 0 0-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84a.48.48 0 0 0-.48.41l-.36 2.54a7.03 7.03 0 0 0-1.62.94l-2.39-.96a.49.49 0 0 0-.59.22L2.74 8.87a.48.48 0 0 0 .12.61l2.03 1.58a7.07 7.07 0 0 0-.06.94c0 .32.02.63.06.94l-2.03 1.58a.48.48 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54c.05.24.25.41.48.41h3.84c.24 0 .44-.17.48-.41l.36-2.54a7.03 7.03 0 0 0 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.48.48 0 0 0-.12-.61l-2.03-1.58zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z"
              />
            </svg>
          </button>
        </div>
      </header>

      <div className="layout">
        <FilterSidebar
          years={meta.years}
          tags={meta.tags}
          form={form}
          thresholdUsd={ds.qualification_threshold_usd}
          languageNote={languageNote}
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
            <GameCard
              game={game}
              onAnother={suggest}
              onCopyAppId={copyAppId}
              onToggleStudy={toggleStudy}
              onResearch={() => setResearchOpen((open) => !open)}
              onExportJpeg={exportJpeg}
              researchOpen={researchOpen}
              busy={busy}
            />
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
          <StudiesList items={studies} onOpen={openGame} />
        </section>
      </div>
      {exporting && (
        <div className="export-stage" aria-hidden="true">
          <ExportCard
            ref={exportRef}
            game={exporting.game}
            exportedAt={exporting.at}
            onArtworkSettled={() => artworkSettled.current()}
          />
        </div>
      )}
      {settingsOpen && (
        <SettingsDialog
          onClose={() => {
            setSettingsOpen(false);
            refreshSide();
          }}
          onSaved={() => {
            onMetaChanged?.();
            refreshSide();
            setViewVersion((v) => v + 1);
          }}
          notify={toast.show}
        />
      )}
      <Toast message={toast.message} visible={toast.visible} />
    </main>
  );
}
