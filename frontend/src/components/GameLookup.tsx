import { useEffect, useRef, useState } from "react";
import { api, type GameSummary } from "../api/client";
import { formatCompactCurrency } from "../lib/format";

interface Props {
  value: string;
  onValueChange: (value: string) => void;
  onPick: (appid: number) => void;
  onLoad: () => void;
}

/** Legacy "Find a specific game": autocomplete (first 12) + load button. Bypasses filters. */
export function GameLookup({ value, onValueChange, onPick, onLoad }: Props) {
  const [results, setResults] = useState<GameSummary[]>([]);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!value.trim()) return; // results are hidden while the input is empty
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api
        .search(value, controller.signal)
        .then((r) => setResults(r.items))
        .catch(() => setResults([]));
    }, 120);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [value]);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  const showResults = open && results.length > 0 && value.trim() !== "";

  return (
    <section className="lookup-section">
      <h2 className="lookup-title">Find a specific game</h2>
      <div className="lookup-wrap" ref={wrapRef}>
        <input
          id="gameLookup"
          type="text"
          placeholder="Game name or AppID"
          autoComplete="off"
          aria-label="Game name or AppID"
          value={value}
          onChange={(e) => {
            onValueChange(e.target.value);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setOpen(false);
              onLoad();
            }
          }}
        />
        <div
          id="lookupResults"
          className={`lookup-results${showResults ? "" : " hidden"}`}
          role="listbox"
        >
          {showResults &&
            results.map((game) => (
              <button
                key={game.appid}
                className="lookup-result"
                type="button"
                role="option"
                aria-selected={false}
                data-appid={game.appid}
                onClick={() => {
                  setOpen(false);
                  onPick(game.appid);
                }}
              >
                <span className="lookup-result-name">{game.name}</span>
                <span className="lookup-result-meta">
                  {game.release_year} · AppID {game.appid} ·{" "}
                  {formatCompactCurrency(game.estimated_revenue_usd)}
                </span>
              </button>
            ))}
        </div>
      </div>
      <button
        id="loadGameButton"
        className="secondary-button lookup-button"
        type="button"
        onClick={() => {
          setOpen(false);
          onLoad();
        }}
      >
        Load game report
      </button>
      <span className="filter-help">
        This ignores the study filters and loads the exact game's report.
      </span>
    </section>
  );
}
