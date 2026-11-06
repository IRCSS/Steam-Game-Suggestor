import type { GameSummary } from "../api/client";
import { formatCompactCurrency } from "../lib/format";

interface Props {
  items: GameSummary[];
  onClear: () => void;
  onOpen: (appid: number) => void;
}

/** Last 12 distinct games shown this session (legacy history panel). */
export function HistoryList({ items, onClear, onOpen }: Props) {
  if (items.length === 0) return null;
  return (
    <section id="historyPanel" className="panel history-panel">
      <div className="sidebar-heading">
        <h2>Session history</h2>
        <button id="clearHistoryButton" className="ghost-button" type="button" onClick={onClear}>
          Clear
        </button>
      </div>
      <div id="historyList" className="history-list">
        {items.map((game, index) => (
          <div
            className="history-item"
            key={game.appid}
            role="button"
            tabIndex={0}
            title="Open this game's report"
            onClick={() => onOpen(game.appid)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen(game.appid);
              }
            }}
          >
            <span className="history-number">{index + 1}</span>
            <span className="history-name">{game.name}</span>
            <span className="history-revenue">
              {formatCompactCurrency(game.estimated_revenue_usd)}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
