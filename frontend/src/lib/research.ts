import type { components } from "../api/schema";

type Schemas = components["schemas"];
export type ResearchView = Schemas["ResearchView"];
export type ResearchStatus = Schemas["ResearchStatus"];
export type RangeView = Schemas["RangeView"];
export type EstimateView = Schemas["Estimate"];
export type Confidence = "high" | "medium" | "low" | "unknown";

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  unknown: "Unknown",
};

const trim = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, ""));

/** "3–5 people (best 4)" / "≈ 4 people" / "Unknown" */
export function estimateText(e: EstimateView, unit: string): string {
  const { low, high, best } = e;
  if (low == null && high == null && best == null) return "Unknown";
  const range = low != null && high != null && low !== high ? `${trim(low)}–${trim(high)} ${unit}` : null;
  if (range && best != null) return `${range} (best ${trim(best)})`;
  if (range) return range;
  return `≈ ${trim((best ?? low ?? high) as number)} ${unit}`;
}

export function money(value: number | null | undefined, currency: string): string {
  if (value == null) return "Unknown";
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "€" : `${currency} `;
  if (value >= 1e9) return `${symbol}${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `${symbol}${(value / 1e6).toFixed(value >= 1e7 ? 0 : 1)}M`;
  if (value >= 1e3) return `${symbol}${Math.round(value / 1e3)}K`;
  return `${symbol}${Math.round(value)}`;
}

/** "≈ €500K (€300K–€750K)" */
export function moneyRange(r: RangeView, currency: string): string {
  if (r.best == null) return "Unknown";
  const span =
    r.low != null && r.high != null && r.low !== r.high
      ? ` (${money(r.low, currency)}–${money(r.high, currency)})`
      : "";
  return `≈ ${money(r.best, currency)}${span}`;
}

export function compactCount(value: number | null | undefined): string {
  if (value == null) return "Unknown";
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${Math.round(value / 1e3)}K`;
  return String(Math.round(value));
}

export function years(value: number | null | undefined): string {
  if (value == null) return "Unknown";
  return `${value.toFixed(value < 10 ? 1 : 0)} years`;
}
