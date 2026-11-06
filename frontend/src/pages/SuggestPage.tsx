import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type CountResponse,
  type GameReport,
  type GameSummary,
  type JobView,
  type LanguageStatus,
  type MetaResponse,
  type ResearchStatus,
  type ResearchView,
  type StudyItem,
  type StudyFilters,
  type SuggestionQuery,
} from "../api/client";
import { ExportCard } from "../components/ExportCard";
import { ResearchPanel } from "../components/ResearchPanel";
import { StudiesList } from "../components/StudiesList";
import { renderJpeg, waitFor } from "../lib/exportJpeg";
import { FilterSidebar } from "../components/FilterSidebar";
import { GameCard } from "../components/GameCard";
import { GameLookup } from "../components/GameLookup";
import { HistoryList } from "../components/HistoryList";
import { type FilterForm, followDefaults, formFromDefaults, formToApi } from "../lib/filters";
import { formatInt } from "../lib/format";
import { SESSION_ID } from "../lib/session";

interface Props {
  meta: MetaResponse;
  notify: (message: string) => void;
  sessionId?: string;
  /** Bumped by the shell when data changed elsewhere (settings saved, data job finished). */
  refreshToken?: number;
  onGameChange?: (game: GameReport | null) => void;
  onFiltersChange?: (filters: StudyFilters) => void;
  /** Open this game's report (e.g. clicked in the Charts tab). */
  openRequest?: { appid: number; nonce: number } | null;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Unexpected error.";
}

export function SuggestPage({
  meta,
  notify,
  sessionId = SESSION_ID,
  refreshToken = 0,
  onGameChange,
  onFiltersChange,
  openRequest = null,
}: Props) {
  const defaults = useMemo(
    () => formFromDefaults(meta.default_filters, meta.default_avoid_repeats),
    [meta],
  );
  const [form, setForm] = useState<FilterForm>(defaults);
  // New data (e.g. a new release year) updates untouched filters; see followDefaults().
  const [seenDefaults, setSeenDefaults] = useState(defaults);
  if (seenDefaults !== defaults) {
    setSeenDefaults(defaults);
    setForm((current) => followDefaults(current, seenDefaults, defaults));
  }
  const [resetKey, setResetKey] = useState(0);
  const [count, setCount] = useState<CountResponse | null>(null);
  const [game, setGame] = useState<GameReport | null>(null);
  const [history, setHistory] = useState<GameSummary[]>([]);
  const [viewVersion, setViewVersion] = useState(0);
  const [lookup, setLookup] = useState("");
  const [studies, setStudies] = useState<StudyItem[]>([]);
  const [languages, setLanguages] = useState<LanguageStatus | null>(null);
  const [researchOpen, setResearchOpen] = useState(false);
  const [research, setResearch] = useState<ResearchView | null>(null);
  const [researchStatus, setResearchStatus] = useState<ResearchStatus | null>(null);
  const [researchJob, setResearchJob] = useState<JobView | null>(null);
  const [researchAppid, setResearchAppid] = useState<number | null>(null);
  const researchState = useRef<string | null>(null);
  const [busy, setBusy] = useState<"study" | "export" | null>(null);
  const [exporting, setExporting] = useState<{ game: GameReport; at: Date } | null>(null);
  const exportRef = useRef<HTMLDivElement>(null);
  const artworkSettled = useRef<() => void>(() => undefined);
  const toast = { show: notify };

  const refreshSide = useCallback(() => {
    api.studies().then((r) => setStudies(r.items)).catch(() => undefined);
    api.languageStatus().then(setLanguages).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshSide();
  }, [refreshSide, refreshToken]);

  useEffect(() => {
    onGameChange?.(game);
  }, [game, onGameChange]);

  // Research availability (and any run already in progress, e.g. started before a reload).
  useEffect(() => {
    api
      .researchStatus()
      .then((s) => {
        setResearchStatus(s);
        setResearchJob(s.job);
        researchState.current = s.job.state;
      })
      .catch(() => undefined);
  }, [refreshToken]);

  // Saved research for the shown game; open the panel automatically when there is some.
  const gameId = game?.appid ?? null;
  useEffect(() => {
    if (gameId === null) return;
    let cancelled = false;
    api
      .research(gameId)
      .then((view) => {
        if (cancelled) return;
        setResearch(view);
        if (view.run) setResearchOpen(true);
      })
      .catch(() => !cancelled && setResearch(null));
    return () => {
      cancelled = true;
    };
  }, [gameId, refreshToken]);

  // Poll a running research job; when it ends, reload the result.
  const researchRunning = researchJob?.state === "running";
  useEffect(() => {
    if (!researchRunning) return;
    const timer = window.setInterval(() => {
      api
        .researchJob()
        .then((job) => {
          setResearchJob(job);
          if (researchState.current === "running" && job.state !== "running") {
            notify(job.state === "completed" ? job.message : `${job.label}: ${job.state}`);
            if (researchAppid !== null) {
              api
                .research(researchAppid)
                .then((view) => setResearch((current) => (view.appid === current?.appid ? view : current)))
                .catch(() => undefined);
            }
          }
          researchState.current = job.state;
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [researchRunning, researchAppid, notify]);

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
  }, [query, viewVersion, refreshToken]);

  useEffect(() => {
    onFiltersChange?.(query.filters);
  }, [query.filters, onFiltersChange]);

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

  useEffect(() => {
    if (openRequest) queueMicrotask(() => void openGame(openRequest.appid));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- react to new requests only
  }, [openRequest]);

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

  const runResearch = async () => {
    if (!game) return;
    try {
      const job = await api.startResearch(game.appid);
      setResearchAppid(game.appid);
      setResearchJob(job);
      researchState.current = "running";
      setResearchOpen(true);
    } catch (error) {
      toast.show(errorText(error));
    }
  };

  const toggleResearch = () => {
    const opening = !researchOpen;
    setResearchOpen(opening);
    // First time for this game: just run it (no chat, no extra click).
    if (
      opening &&
      game &&
      research?.appid === game.appid &&
      !research.run &&
      researchStatus?.available &&
      !researchRunning
    ) {
      void runResearch();
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
    <>

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
              onResearch={toggleResearch}
              researchPanel={
                <ResearchPanel
                  view={research?.appid === game.appid ? research : null}
                  status={researchStatus}
                  job={researchAppid === game.appid ? researchJob : null}
                  otherJobLabel={
                    researchRunning && researchAppid !== game.appid ? (researchJob?.label ?? null) : null
                  }
                  onRun={runResearch}
                  onCancel={() => api.cancelResearch().then(setResearchJob)}
                />
              }
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
            research={research?.appid === exporting.game.appid ? research : null}
            onArtworkSettled={() => artworkSettled.current()}
          />
        </div>
      )}
    </>
  );
}
