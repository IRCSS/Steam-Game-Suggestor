import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { type FilterForm, formFromDefaults } from "../lib/filters";
import { META, RESEARCH, VAMPIRE } from "../tests/fixtures";
import { FilterSidebar } from "./FilterSidebar";
import { GameCard } from "./GameCard";
import type { JobView, ResearchStatus } from "../api/client";
import { ExportCard } from "./ExportCard";
import { ResearchPanel } from "./ResearchPanel";
import { StudiesList } from "./StudiesList";
import { HeroImage, PLACEHOLDER_IMAGE, marketingImageUrls } from "./HeroImage";
import { HistoryList } from "./HistoryList";

function SidebarHarness({ onForm }: { onForm: (f: FilterForm) => void }) {
  const [form, setForm] = useState(formFromDefaults(META.default_filters));
  return (
    <FilterSidebar
      years={META.years}
      tags={META.tags}
      form={form}
      thresholdUsd={100000}
      languageNote="note"
      matchLabel="12 matches"
      canSuggest
      resetKey={0}
      lookup={null}
      onChange={(f) => {
        setForm(f);
        onForm(f);
      }}
      onSuggest={() => undefined}
      onReset={() => undefined}
    />
  );
}

describe("FilterSidebar", () => {
  it("renders legacy defaults", () => {
    render(<SidebarHarness onForm={() => undefined} />);
    expect(screen.getByLabelText("Minimum", { selector: "#minRevenue" })).toHaveValue(150000);
    expect(document.querySelector("#maxRevenue")).toHaveValue(800000);
    expect(document.querySelector("#minReviewScore")).toHaveValue(50);
    expect(document.querySelector("#maxReviews")).toHaveValue(null);
    expect(document.querySelectorAll(".year-checkbox:checked")).toHaveLength(4);
    expect(screen.getByText("12 matches")).toBeInTheDocument();
    expect(screen.getByLabelText("Avoid repeats")).toBeChecked();
  });

  it("updates numeric inputs, years and toggles", async () => {
    const forms: FilterForm[] = [];
    render(<SidebarHarness onForm={(f) => forms.push(f)} />);
    fireEvent.change(document.querySelector("#minRevenue")!, { target: { value: "200000" } });
    expect(forms.at(-1)?.minRevenue).toBe("200000");
    await userEvent.click(screen.getByRole("checkbox", { name: "2023" }));
    expect(forms.at(-1)?.years).toEqual([2022, 2024, 2025]);
    await userEvent.click(screen.getByLabelText("Include games below the catalog revenue floor"));
    expect(forms.at(-1)?.includeBelowThreshold).toBe(true);
  });

  it("adds tags from the browser, filters the catalog and removes chips", async () => {
    const forms: FilterForm[] = [];
    render(<SidebarHarness onForm={(f) => forms.push(f)} />);
    expect(screen.getByText(`Browse all ${META.tags.length} tags`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Colony Sim", hidden: true }));
    await userEvent.click(screen.getByRole("button", { name: "Indie", hidden: true }));
    expect(forms.at(-1)?.includeTags).toBe("Colony Sim, Indie");
    expect(document.querySelector('[data-tag="Indie"]')).toHaveClass("selected");
    fireEvent.change(document.querySelector("#tagSearch")!, { target: { value: "rogue" } });
    const visible = [...document.querySelectorAll<HTMLButtonElement>(".available-tag")]
      .filter((b) => !b.hidden)
      .map((b) => b.dataset.tag);
    expect(visible).toEqual(["Roguelike", "Roguelike Deckbuilder"]);
    await userEvent.click(screen.getByRole("button", { name: "Remove tag Colony Sim" }));
    expect(forms.at(-1)?.includeTags).toBe("Indie");
  });
});

describe("GameCard", () => {
  it("renders metrics, labels and links", () => {
    render(<GameCard game={VAMPIRE} onAnother={() => undefined} onCopyAppId={() => undefined} onToggleStudy={() => undefined} onResearch={() => undefined} onExportJpeg={() => undefined} researchOpen={false} busy={null} />);
    expect(screen.getByRole("heading", { name: "Vampire Survivors" })).toBeInTheDocument();
    expect(document.querySelector("#gameRevenue")).toHaveTextContent("$42.1M");
    expect(document.querySelector("#gamePrice")).toHaveTextContent("$3.74");
    expect(document.querySelector("#gameRank")).toHaveTextContent("#16");
    expect(document.querySelector("#gamePercentile")).toHaveTextContent("99.6%");
    expect(document.querySelector("#gameReviews")).toHaveTextContent("250,334");
    expect(document.querySelector("#rankCardValue")).toHaveTextContent("#16 of 3,946");
    expect(document.querySelector("#rankCardNote")).toHaveTextContent("top 0.4%");
    expect(screen.getByText("Est. gross revenue")).toBeInTheDocument();
    expect(screen.getByTestId("provenance")).toHaveTextContent("not actual sales");
    expect(screen.getByRole("link", { name: /Reveal Steam page/ })).toHaveAttribute(
      "href",
      "https://store.steampowered.com/app/1794680",
    );
    expect(screen.queryByTestId("below-floor")).toBeNull();
  });

  it("flags below-floor games and handles missing description/tags", () => {
    const game = {
      ...VAMPIRE,
      short_description: "",
      tags: [],
      qualification: { qualified: false, threshold_usd: 100000 },
    };
    render(<GameCard game={game} onAnother={() => undefined} onCopyAppId={() => undefined} onToggleStudy={() => undefined} onResearch={() => undefined} onExportJpeg={() => undefined} researchOpen={false} busy={null} />);
    expect(screen.getByTestId("below-floor")).toHaveTextContent("Below $100K catalog floor");
    expect(screen.getByText("No short store description is available.")).toBeInTheDocument();
    expect(screen.getByText("No tags available")).toBeInTheDocument();
  });

  it("escapes store text instead of rendering HTML", () => {
    const game = { ...VAMPIRE, short_description: "<img src=x onerror=alert(1)>" };
    render(<GameCard game={game} onAnother={() => undefined} onCopyAppId={() => undefined} onToggleStudy={() => undefined} onResearch={() => undefined} onExportJpeg={() => undefined} researchOpen={false} busy={null} />);
    expect(document.querySelector("#gameDescription")?.textContent).toBe(
      "<img src=x onerror=alert(1)>",
    );
    expect(document.querySelector("#gameDescription img")).toBeNull();
  });
});

describe("HeroImage", () => {
  it("falls back through CDN URLs to the placeholder", () => {
    render(<HeroImage appid={10} name="X" />);
    const img = screen.getByAltText("X Steam artwork") as HTMLImageElement;
    const urls = marketingImageUrls(10);
    expect(img.src).toBe(urls[0]);
    fireEvent.error(img);
    expect(img.src).toBe(urls[1]);
    fireEvent.error(img);
    fireEvent.error(img);
    expect(img.getAttribute("src")).toBe(PLACEHOLDER_IMAGE);
  });
});

describe("HistoryList", () => {
  it("is hidden when empty and numbers items", async () => {
    const { container, rerender } = render(
      <HistoryList items={[]} onClear={() => undefined} onOpen={() => undefined} />,
    );
    expect(container).toBeEmptyDOMElement();
    const opened: number[] = [];
    rerender(
      <HistoryList
        items={[
          {
            appid: 1,
            name: "A",
            release_year: 2022,
            estimated_revenue_usd: 150000,
            legacy_rank_in_year: 3,
          },
        ]}
        onClear={() => undefined}
        onOpen={(id) => opened.push(id)}
      />,
    );
    expect(screen.getByText("Session history")).toBeInTheDocument();
    expect(screen.getByText("$150K")).toBeInTheDocument();
    await userEvent.click(screen.getByText("A"));
    expect(opened).toEqual([1]);
  });
});

describe("study, research and export controls", () => {
  function renderCard(overrides: Partial<Parameters<typeof GameCard>[0]> = {}) {
    const calls: string[] = [];
    render(
      <GameCard
        game={VAMPIRE}
        onAnother={() => calls.push("another")}
        onCopyAppId={() => calls.push("copy")}
        onToggleStudy={() => calls.push("study")}
        onResearch={() => calls.push("research")}
        onExportJpeg={() => calls.push("export")}
        researchOpen={false}
        busy={null}
        {...overrides}
      />,
    );
    return calls;
  }

  it("shows the three new buttons and languages", async () => {
    const calls = renderCard();
    await userEvent.click(screen.getByRole("button", { name: /Add to Studies/ }));
    await userEvent.click(screen.getByRole("button", { name: "Get more info from LLM" }));
    await userEvent.click(screen.getByRole("button", { name: "Export as JPG" }));
    expect(calls).toEqual(["study", "research", "export"]);
    expect(document.querySelector("#gameLanguages")).toHaveTextContent("English, French, Japanese");
    expect(screen.getByText("English ✓")).toBeInTheDocument();
    expect(screen.queryByTestId("research-panel")).toBeNull();
  });

  it("reflects study state, research panel and busy export", () => {
    renderCard({
      game: {
        ...VAMPIRE,
        study: { in_studies: true, added_at: "2026-11-06T10:00:00+00:00", added_by: "pc-1" },
        languages: { status: "unknown", english: null, languages: [], fetched_at: null },
      },
      researchOpen: true,
      researchPanel: (
        <ResearchPanel view={null} status={STATUS_OK} job={null} otherJobLabel={null} onRun={() => undefined} onCancel={() => undefined} />
      ),
      busy: "export",
    });
    expect(screen.getByRole("button", { name: "✓ In Studies" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Added 2026-11-06 on pc-1")).toBeInTheDocument();
    expect(screen.getByTestId("research-panel")).toHaveTextContent("No research yet");
    expect(screen.getByRole("button", { name: "Exporting…" })).toBeDisabled();
    expect(document.querySelector("#gameLanguages")).toHaveTextContent("Not checked yet");
  });

  it("lists studies and opens them", async () => {
    const opened: number[] = [];
    render(
      <StudiesList
        items={[
          {
            appid: 7,
            name: "Saved Game",
            added_at: "2026-11-06T10:00:00+00:00",
            added_by: "pc-1",
            release_year: 2023,
            estimated_revenue_usd: 250000,
          },
        ]}
        onOpen={(id) => opened.push(id)}
      />,
    );
    expect(screen.getByText("1 saved")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Saved Game"));
    expect(opened).toEqual([7]);
  });
});

const IDLE: JobView = {
  job_id: "", kind: "", label: "", state: "idle", total: 0, done: 0, counters: {}, requests: 0,
  started_at: null, finished_at: null, eta_seconds: null, message: "", recent: [],
};
const STATUS_OK: ResearchStatus = { available: true, message: "Ready", provider: "claude_code", cli_path: "claude.exe", max_budget_usd: 2, job: IDLE };

describe("ResearchPanel", () => {
  const noop = () => undefined;

  it("renders the standardized table, confidences and both insight lists", () => {
    render(<ResearchPanel view={RESEARCH} status={STATUS_OK} job={null} otherJobLabel={null} onRun={noop} onCancel={noop} />);
    const table = screen.getByTestId("research-table");
    expect(table).toHaveTextContent("People who worked on it");
    expect(table).toHaveTextContent("1–3 people (best 1)");
    expect(table).toHaveTextContent("10–14 months (best 12)");
    expect(table).toHaveTextContent("≈ 1.0 years");
    expect(table).toHaveTextContent("Cost at €50K per person-year");
    expect(table).toHaveTextContent("≈ €50K (€42K–€175K)");
    expect(table).toHaveTextContent("A team of 3 would need 0.3 years");
    expect(table).toHaveTextContent("Break-even (after the 30% platform cut)");
    expect(table).toHaveTextContent("≈ $77K gross");
    expect(table).toHaveTextContent("≈ 15K copies at $4.99");
    expect(table).toHaveTextContent("546× break-even");
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Medium").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Developer interview" })).toHaveAttribute("href", "https://example.com/interview");
    expect(screen.getByTestId("insights-worked")).toHaveTextContent("Huge value for the price");
    expect(screen.getByTestId("insights-held-back")).toHaveTextContent("Repetitive late game");
    expect(screen.getByText(/Researched 2026-11-06 by Claude Code/)).toHaveTextContent("$0.73");
    expect(screen.getByRole("button", { name: "Refresh research" })).toBeEnabled();
  });

  it("shows run / running / failed / unavailable states", async () => {
    const calls: string[] = [];
    const empty = { ...RESEARCH, run: null, economics: null, runs_count: 0 };
    const { rerender } = render(
      <ResearchPanel view={empty} status={STATUS_OK} job={null} otherJobLabel={null} onRun={() => calls.push("run")} onCancel={() => calls.push("cancel")} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Run research" }));
    expect(calls).toEqual(["run"]);

    rerender(
      <ResearchPanel view={null} status={STATUS_OK} job={{ ...IDLE, state: "running", recent: ["12:00:00 Asking Claude Code"] }} otherJobLabel={null} onRun={noop} onCancel={() => calls.push("cancel")} />,
    );
    expect(screen.getByTestId("research-running")).toHaveTextContent("Asking Claude Code");
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(calls).toEqual(["run", "cancel"]);

    rerender(
      <ResearchPanel view={RESEARCH} status={STATUS_OK} job={{ ...IDLE, state: "failed", message: "stopped at the $2.00 budget cap" }} otherJobLabel={null} onRun={noop} onCancel={noop} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("budget cap");
    expect(screen.getByTestId("research-table")).toBeInTheDocument(); // previous result still shown

    rerender(
      <ResearchPanel view={null} status={{ ...STATUS_OK, available: false, message: "Claude Code CLI not found on this PC." }} job={null} otherJobLabel={null} onRun={noop} onCancel={noop} />,
    );
    expect(screen.getByText("Claude Code CLI not found on this PC.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run research" })).toBeNull();
  });

  it("is included at the bottom of the JPG export when present", () => {
    const { rerender } = render(<ExportCard game={VAMPIRE} exportedAt={new Date("2026-11-06")} research={RESEARCH} onArtworkSettled={noop} />);
    const section = screen.getByTestId("export-research");
    expect(section).toHaveTextContent("1–3 people (best 1)");
    expect(section).toHaveTextContent("Why it performed as well as it did");
    expect(section.querySelector("a")).toBeNull(); // no links in an image
    rerender(<ExportCard game={VAMPIRE} exportedAt={new Date("2026-11-06")} research={null} onArtworkSettled={noop} />);
    expect(screen.queryByTestId("export-research")).toBeNull();
  });
});
