import { META } from "../tests/fixtures";
import { addTag, displayTags, formFromDefaults, formToApi, parseNumber, removeTag } from "./filters";
import { formatCompactCurrency, formatCurrency, formatInt } from "./format";

describe("format (legacy parity)", () => {
  it("formats currency like the legacy app", () => {
    expect(formatCurrency(3.74)).toBe("$3.74");
    expect(formatCurrency(0)).toBe("$0.00");
    expect(formatCurrency(1234.5)).toBe("$1,235");
  });

  it("formats compact currency", () => {
    expect(formatCompactCurrency(42_131_212)).toBe("$42.1M");
    expect(formatCompactCurrency(2_500_000_000)).toBe("$2.5B");
    expect(formatCompactCurrency(150_000)).toBe("$150K");
    expect(formatCompactCurrency(999)).toBe("$999.00");
  });

  it("formats integers with grouping", () => {
    expect(formatInt(15521)).toBe("15,521");
  });
});

describe("filters", () => {
  it("parses numbers like legacy numericValue", () => {
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("  ")).toBeNull();
    expect(parseNumber("1e5")).toBe(100000);
    expect(parseNumber("abc")).toBeNull();
    expect(parseNumber("0")).toBe(0);
  });

  it("round-trips the default filters", () => {
    const form = formFromDefaults(META.default_filters);
    expect(form.minRevenue).toBe("150000");
    expect(form.maxReviews).toBe("");
    expect(form.avoidRepeats).toBe(true);
    expect(form.includeBelowThreshold).toBe(false);
    expect(formToApi(form)).toEqual(META.default_filters);
  });

  it("adds and removes tags case-insensitively without duplicates", () => {
    expect(displayTags(" Indie , ,Action,")).toEqual(["Indie", "Action"]);
    expect(addTag("Indie", "indie")).toBe("Indie");
    expect(addTag("Indie", "Action")).toBe("Indie, Action");
    expect(removeTag("Indie, Action", "INDIE")).toBe("Action");
  });
});
