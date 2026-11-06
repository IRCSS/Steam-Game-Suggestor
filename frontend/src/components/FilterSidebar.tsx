import type { ReactNode } from "react";
import type { FilterForm, NumericField } from "../lib/filters";
import { formatCompactCurrency } from "../lib/format";
import { TagPicker } from "./TagPicker";

interface Props {
  years: number[];
  tags: string[];
  form: FilterForm;
  thresholdUsd: number;
  matchLabel: string;
  canSuggest: boolean;
  resetKey: number;
  lookup: ReactNode;
  onChange: (form: FilterForm) => void;
  onSuggest: () => void;
  onReset: () => void;
}

interface PairProps {
  label: string;
  help?: string;
  min: { id: NumericField; caption: string; attrs?: Record<string, string | number> };
  max: { id: NumericField; caption: string; attrs?: Record<string, string | number> };
  form: FilterForm;
  set: (field: NumericField, value: string) => void;
}

function NumberPair({ label, help, min, max, form, set }: PairProps) {
  return (
    <section className="filter-group">
      <span className="filter-label">{label}</span>
      <div className="input-pair">
        {[min, max].map((f) => (
          <label key={f.id}>
            <span className="input-caption">{f.caption}</span>
            <input
              id={f.id}
              type="number"
              value={form[f.id]}
              onChange={(e) => set(f.id, e.target.value)}
              {...f.attrs}
            />
          </label>
        ))}
      </div>
      {help && <span className="filter-help">{help}</span>}
    </section>
  );
}

/** Legacy sticky sidebar: lookup, study filters, toggles and the main buttons. */
export function FilterSidebar(props: Props) {
  const { form, onChange } = props;
  const set = (field: NumericField, value: string) => onChange({ ...form, [field]: value });
  const toggleYear = (year: number, checked: boolean) =>
    onChange({
      ...form,
      years: checked ? [...new Set([...form.years, year])] : form.years.filter((y) => y !== year),
    });

  return (
    <aside className="panel filters">
      {props.lookup}

      <div className="sidebar-heading">
        <h2>Study filters</h2>
        <span id="matchCount" className="match-count" aria-live="polite">
          {props.matchLabel}
        </span>
      </div>

      <section className="filter-group first">
        <span className="filter-label">Release years</span>
        <div className="year-grid">
          {props.years.map((year) => (
            <label className="year-option" key={year}>
              <input
                type="checkbox"
                className="year-checkbox"
                value={year}
                checked={form.years.includes(year)}
                onChange={(e) => toggleYear(year, e.target.checked)}
              />
              <span>{year}</span>
            </label>
          ))}
        </div>
      </section>

      <NumberPair
        label="Estimated revenue"
        help="Estimated gross: total reviews × 45 × listed price. Not actual sales."
        min={{ id: "minRevenue", caption: "Minimum", attrs: { min: 0, step: 10000 } }}
        max={{ id: "maxRevenue", caption: "Maximum", attrs: { min: 0, step: 10000 } }}
        form={form}
        set={set}
      />
      <NumberPair
        label="Listed price"
        min={{ id: "minPrice", caption: "Minimum", attrs: { min: 0 } }}
        max={{ id: "maxPrice", caption: "Maximum", attrs: { min: 0 } }}
        form={form}
        set={set}
      />
      <NumberPair
        label="Revenue rank in release year"
        min={{ id: "minRank", caption: "Best rank", attrs: { min: 1 } }}
        max={{ id: "maxRank", caption: "Worst rank", attrs: { min: 1 } }}
        form={form}
        set={set}
      />
      <NumberPair
        label="Revenue percentile"
        min={{ id: "minPercentile", caption: "Minimum", attrs: { min: 0, max: 100 } }}
        max={{ id: "maxPercentile", caption: "Maximum", attrs: { min: 0, max: 100 } }}
        form={form}
        set={set}
      />
      <NumberPair
        label="Review count"
        min={{ id: "minReviews", caption: "Minimum", attrs: { min: 20 } }}
        max={{ id: "maxReviews", caption: "Maximum", attrs: { min: 20, placeholder: "No limit" } }}
        form={form}
        set={set}
      />
      <NumberPair
        label="Positive review score"
        min={{ id: "minReviewScore", caption: "Minimum %", attrs: { min: 0, max: 100 } }}
        max={{ id: "maxReviewScore", caption: "Maximum %", attrs: { min: 0, max: 100 } }}
        form={form}
        set={set}
      />

      <TagPicker
        key={props.resetKey}
        tags={props.tags}
        value={form.includeTags}
        onChange={(includeTags) => onChange({ ...form, includeTags })}
      />

      <section className="filter-group">
        <label className="filter-label" htmlFor="excludeTags">
          Exclude tags
        </label>
        <input
          id="excludeTags"
          type="text"
          placeholder="e.g. VR, Multiplayer"
          value={form.excludeTags}
          onChange={(e) => onChange({ ...form, excludeTags: e.target.value })}
        />
      </section>

      <section className="filter-group">
        <div className="toggle-row">
          <div className="toggle-copy">
            <strong>Avoid repeats</strong>
            <span>Skip games already shown this session.</span>
          </div>
          <label className="switch">
            <input
              id="avoidRepeats"
              type="checkbox"
              aria-label="Avoid repeats"
              checked={form.avoidRepeats}
              onChange={(e) => onChange({ ...form, avoidRepeats: e.target.checked })}
            />
            <span className="switch-track"></span>
          </label>
        </div>
        <div className="toggle-row toggle-row-spaced">
          <div className="toggle-copy">
            <strong>Include below catalog floor</strong>
            <span>
              Also suggest games under the {formatCompactCurrency(props.thresholdUsd)} estimated
              revenue floor.
            </span>
          </div>
          <label className="switch">
            <input
              id="includeBelowThreshold"
              type="checkbox"
              aria-label="Include games below the catalog revenue floor"
              checked={form.includeBelowThreshold}
              onChange={(e) => onChange({ ...form, includeBelowThreshold: e.target.checked })}
            />
            <span className="switch-track"></span>
          </label>
        </div>
      </section>

      <div className="button-stack">
        <button
          id="suggestButton"
          className="primary-button"
          type="button"
          disabled={!props.canSuggest}
          onClick={props.onSuggest}
        >
          Suggest a case study
        </button>
        <button id="resetButton" className="secondary-button" type="button" onClick={props.onReset}>
          Reset filters
        </button>
      </div>
    </aside>
  );
}
