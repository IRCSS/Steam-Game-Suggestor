// Chart tokens for the app's dark surface (legacy --panel #111823).
// Series colors validated with the dataviz validator against #111823 (dark mode):
// lightness band, chroma floor, CVD separation (dE 26.8), normal-vision (dE 31.8), contrast >= 3:1.
export const CHART = {
  series1: "#3987e5", // all games (blue)
  series2: "#d95926", // emphasis: games in Studies (orange)
  surface: "#111823",
  grid: "#1e2a3c", // hairline, one step off the surface (legacy --border-soft)
  axis: "#27344a", // baseline (legacy --border)
  text: "#f4f7fc", // primary ink (legacy --text)
  muted: "#9aabc1", // secondary ink (legacy --muted)
  subtle: "#718198", // axis labels (legacy --subtle)
} as const;

/** Powers of ten covering [min, max] - readable ticks for log axes. */
export function logTicks(min: number, max: number): number[] {
  if (!(min > 0) || !(max > 0)) return [];
  const ticks: number[] = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e += 1) {
    ticks.push(10 ** e);
  }
  return ticks;
}

/** Axis domain spanning the given log ticks (Recharts picks its own when there are none). */
export function logDomain(ticks: number[]): [number, number] | ["auto", "auto"] {
  const first = ticks[0];
  const last = ticks[ticks.length - 1];
  return first !== undefined && last !== undefined ? [first, last] : ["auto", "auto"];
}

export function compactUsd(value: number): string {
  if (value >= 1e9) return `$${(value / 1e9).toFixed(value >= 1e10 ? 0 : 1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(value >= 1e7 ? 0 : 1)}M`;
  if (value >= 1e3) return `$${Math.round(value / 1e3)}K`;
  return `$${Math.round(value)}`;
}

export function compactNumber(value: number): string {
  if (value >= 1e6) return `${(value / 1e6).toFixed(value >= 1e7 ? 0 : 1)}M`;
  if (value >= 1e4) return `${Math.round(value / 1e3)}K`;
  return Math.round(value).toLocaleString("en-US");
}

export function binLabel(start: number, end: number | null | undefined): string {
  return end === null || end === undefined ? `${compactUsd(start)}+` : `${compactUsd(start)}–${compactUsd(end)}`;
}
