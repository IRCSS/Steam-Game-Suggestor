import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { type FilterForm, formFromDefaults } from "../lib/filters";
import { META, VAMPIRE } from "../tests/fixtures";
import { FilterSidebar } from "./FilterSidebar";
import { GameCard } from "./GameCard";
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
    render(<GameCard game={VAMPIRE} onAnother={() => undefined} onCopyAppId={() => undefined} />);
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
    render(<GameCard game={game} onAnother={() => undefined} onCopyAppId={() => undefined} />);
    expect(screen.getByTestId("below-floor")).toHaveTextContent("Below $100K catalog floor");
    expect(screen.getByText("No short store description is available.")).toBeInTheDocument();
    expect(screen.getByText("No tags available")).toBeInTheDocument();
  });

  it("escapes store text instead of rendering HTML", () => {
    const game = { ...VAMPIRE, short_description: "<img src=x onerror=alert(1)>" };
    render(<GameCard game={game} onAnother={() => undefined} onCopyAppId={() => undefined} />);
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
