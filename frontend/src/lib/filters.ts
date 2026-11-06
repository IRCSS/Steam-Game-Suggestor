import type { StudyFilters } from "../api/client";

/** Raw form state. Numeric inputs keep their text exactly like the legacy <input> values. */
export interface FilterForm {
  years: number[];
  minRevenue: string;
  maxRevenue: string;
  minPrice: string;
  maxPrice: string;
  minRank: string;
  maxRank: string;
  minPercentile: string;
  maxPercentile: string;
  minReviews: string;
  maxReviews: string;
  minReviewScore: string;
  maxReviewScore: string;
  includeTags: string;
  excludeTags: string;
  avoidRepeats: boolean;
  includeBelowThreshold: boolean;
  requireEnglish: boolean;
  excludeStudies: boolean;
}

export type NumericField = Exclude<
  keyof FilterForm,
  | "years"
  | "includeTags"
  | "excludeTags"
  | "avoidRepeats"
  | "includeBelowThreshold"
  | "requireEnglish"
  | "excludeStudies"
>;

const text = (value: number | null | undefined): string =>
  value === null || value === undefined ? "" : String(value);

/** Legacy numericValue(): empty or non-finite -> null (the backend applies the legacy fallback). */
export function parseNumber(value: string): number | null {
  if (value.trim() === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formFromDefaults(d: StudyFilters, avoidRepeats = true): FilterForm {
  return {
    years: [...d.years],
    minRevenue: text(d.min_revenue),
    maxRevenue: text(d.max_revenue),
    minPrice: text(d.min_price),
    maxPrice: text(d.max_price),
    minRank: text(d.min_rank),
    maxRank: text(d.max_rank),
    minPercentile: text(d.min_percentile),
    maxPercentile: text(d.max_percentile),
    minReviews: text(d.min_reviews),
    maxReviews: text(d.max_reviews),
    minReviewScore: text(d.min_review_score),
    maxReviewScore: text(d.max_review_score),
    includeTags: d.include_tags ?? "",
    excludeTags: d.exclude_tags ?? "",
    avoidRepeats,
    includeBelowThreshold: false,
    requireEnglish: d.require_english ?? false,
    excludeStudies: true,
  };
}

export function formToApi(f: FilterForm): StudyFilters {
  return {
    years: [...f.years].sort((a, b) => a - b),
    min_revenue: parseNumber(f.minRevenue),
    max_revenue: parseNumber(f.maxRevenue),
    min_price: parseNumber(f.minPrice),
    max_price: parseNumber(f.maxPrice),
    min_rank: parseNumber(f.minRank),
    max_rank: parseNumber(f.maxRank),
    min_percentile: parseNumber(f.minPercentile),
    max_percentile: parseNumber(f.maxPercentile),
    min_reviews: parseNumber(f.minReviews),
    max_reviews: parseNumber(f.maxReviews),
    min_review_score: parseNumber(f.minReviewScore),
    max_review_score: parseNumber(f.maxReviewScore),
    include_tags: f.includeTags,
    exclude_tags: f.excludeTags,
    require_english: f.requireEnglish,
  };
}

/** Legacy displayTags(): split on commas, trim, keep case, drop empties. */
export function displayTags(value: string): string[] {
  return value
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export function addTag(value: string, tag: string): string {
  const selected = displayTags(value);
  if (!selected.some((t) => t.toLocaleLowerCase() === tag.toLocaleLowerCase())) {
    selected.push(tag);
  }
  return selected.join(", ");
}

export function removeTag(value: string, tag: string): string {
  return displayTags(value)
    .filter((t) => t.toLocaleLowerCase() !== tag.toLocaleLowerCase())
    .join(", ");
}

/**
 * When the dataset changes (new release year, larger yearly populations), carry the new defaults
 * into the form - but only for fields the user has not changed. Newly appearing years are ticked
 * (the default is "all years"); years the user unticked stay unticked.
 */
export function followDefaults(form: FilterForm, previous: FilterForm, next: FilterForm): FilterForm {
  const updated: FilterForm = { ...form };
  const newYears = next.years.filter((y) => !previous.years.includes(y));
  if (newYears.length) {
    updated.years = [...form.years, ...newYears.filter((y) => !form.years.includes(y))].sort();
  }
  for (const key of Object.keys(next) as (keyof FilterForm)[]) {
    if (key === "years") continue;
    if (form[key] === previous[key] && previous[key] !== next[key]) {
      (updated as unknown as Record<string, unknown>)[key] = next[key];
    }
  }
  return updated;
}
