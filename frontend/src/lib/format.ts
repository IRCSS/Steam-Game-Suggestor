// Display formatting ported from the legacy HTML (formatCurrency / formatCompactCurrency).

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Number(value) >= 1000 ? 0 : 2,
  }).format(Number(value || 0));
}

export function formatCompactCurrency(value: number): string {
  const number = Number(value || 0);
  if (number >= 1_000_000_000) return `$${(number / 1_000_000_000).toFixed(1)}B`;
  if (number >= 1_000_000) return `$${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `$${Math.round(number / 1_000)}K`;
  return formatCurrency(number);
}

export function formatInt(value: number): string {
  return Number(value || 0).toLocaleString("en-US");
}

export function minorToMajor(amountMinor: number): number {
  return amountMinor / 100;
}
