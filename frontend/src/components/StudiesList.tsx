import type { StudyItem } from "../api/client";
import { formatCompactCurrency } from "../lib/format";

interface Props {
  items: StudyItem[];
  onOpen: (appid: number) => void;
}

/** Games archived as potential case studies (newest first). Click to reopen a report. */
export function StudiesList({ items, onOpen }: Props) {
  if (items.length === 0) return null;
  return (
    <section id="studiesPanel" className="panel history-panel">
      <div className="sidebar-heading">
        <h2>Studies</h2>
        <span className="match-count">{items.length} saved</span>
      </div>
      <div className="history-list">
        {items.map((study) => (
          <div
            className="history-item"
            key={study.appid}
            role="button"
            tabIndex={0}
            title={`Added ${study.added_at.slice(0, 10)} on ${study.added_by}`}
            onClick={() => onOpen(study.appid)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen(study.appid);
              }
            }}
          >
            <span className="history-number">{study.release_year ?? "–"}</span>
            <span className="history-name">{study.name}</span>
            <span className="history-revenue">
              {study.estimated_revenue_usd !== null && study.estimated_revenue_usd !== undefined
                ? formatCompactCurrency(study.estimated_revenue_usd)
                : ""}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
