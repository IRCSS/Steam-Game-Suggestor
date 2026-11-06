import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { META, VAMPIRE } from "../tests/fixtures";
import { App } from "../App";
import { Toast, useToast } from "../components/Toast";
import { SuggestPage } from "./SuggestPage";

type Handler = (url: string, init?: RequestInit) => unknown;

export const LANGUAGE_STATUS = {
  total_games: 15521,
  qualified_games: 3704,
  known: 100,
  known_qualified: 100,
  english: 90,
  no_english: 10,
  unavailable: 0,
  offline: false,
  job: {
    state: "idle",
    scope: "",
    total: 0,
    done: 0,
    found: 0,
    unavailable: 0,
    errors: 0,
    skipped: 0,
    started_at: null,
    finished_at: null,
    message: "",
    recent: [],
    seconds_per_request: 1.7,
  },
};

/** Endpoints every page load calls; answered here so tests only mock what they exercise. */
function sideEndpoint(url: string): unknown {
  if (url === "/api/studies") return { items: [], folder: "data/studies" };
  if (url === "/api/languages/status") return LANGUAGE_STATUS;
  return undefined;
}

/** The shell normally provides the toast; tests provide a minimal one. */
function Harness({ sessionId }: { sessionId: string }) {
  const toast = useToast();
  return (
    <>
      <SuggestPage meta={META} notify={toast.show} sessionId={sessionId} />
      <Toast message={toast.message} visible={toast.visible} />
    </>
  );
}

function mockFetch(handler: Handler) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const side = sideEndpoint(url);
      const result = side ?? handler(url, init);
      if (result instanceof Response) return result;
      return new Response(JSON.stringify(result), { status: 200 });
    }),
  );
  return calls;
}

const summary = {
  appid: VAMPIRE.appid,
  name: VAMPIRE.name,
  release_year: 2022,
  estimated_revenue_usd: 42131212,
  legacy_rank_in_year: 16,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SuggestPage", () => {
  it("shows match count, suggests a game and records history", async () => {
    let seen = false;
    const calls = mockFetch((url) => {
      if (url.endsWith("/api/suggestions/count"))
        return { count: seen ? 41 : 42, count_ignoring_history: 42, all_seen: false };
      if (url.endsWith("/api/suggestions")) {
        seen = true;
        return { status: "ok", game: VAMPIRE, repeat_history_reset: false, candidate_count: 42 };
      }
      if (url.includes("/history")) return { items: [summary] };
      throw new Error(`unexpected ${url}`);
    });
    render(<Harness sessionId="test-session-1" />);
    expect(await screen.findByText("42 matches")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Suggest a case study" }));
    expect(await screen.findByRole("heading", { name: "Vampire Survivors" })).toBeInTheDocument();
    expect(screen.getByText("Session history")).toBeInTheDocument();
    expect(await screen.findByText("41 matches")).toBeInTheDocument();

    const suggestCall = calls.find((c) => c.url.endsWith("/api/suggestions"));
    expect(suggestCall?.body).toMatchObject({
      session_id: "test-session-1",
      avoid_repeats: true,
      include_below_threshold: false,
      filters: { min_revenue: 150000, max_revenue: 800000, max_reviews: null },
    });
  });

  it("shows 'All seen' and the reset notice", async () => {
    mockFetch((url) => {
      if (url.endsWith("/count")) return { count: 0, count_ignoring_history: 3, all_seen: true };
      if (url.endsWith("/api/suggestions"))
        return { status: "ok", game: VAMPIRE, repeat_history_reset: true, candidate_count: 3 };
      return { items: [summary] };
    });
    render(<Harness sessionId="test-session-2" />);
    expect(await screen.findByText("All seen")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Suggest a case study" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(
      await screen.findByText("All matching games had been shown. Repeat history reset."),
    ).toBeInTheDocument();
  });

  it("disables suggesting with zero matches", async () => {
    mockFetch(() => ({ count: 0, count_ignoring_history: 0, all_seen: false }));
    render(<Harness sessionId="test-session-3" />);
    expect(await screen.findByText("0 matches")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suggest a case study" })).toBeDisabled();
  });

  it("loads a specific game by lookup and reports not-found", async () => {
    const calls = mockFetch((url) => {
      if (url.endsWith("/count")) return { count: 5, count_ignoring_history: 5, all_seen: false };
      if (url.includes("/api/games/resolve?q=nope"))
        return new Response(JSON.stringify({ detail: "No matching game found." }), {
          status: 404,
        });
      if (url.includes("/api/games/resolve")) return VAMPIRE;
      if (url.includes("/api/games?q=")) return { items: [summary] };
      if (url.includes("/views")) return { items: [summary] };
      throw new Error(`unexpected ${url}`);
    });
    render(<Harness sessionId="test-session-4" />);
    const input = screen.getByLabelText("Game name or AppID");
    await userEvent.type(input, "nope{Enter}");
    expect(await screen.findByText("No matching game found.")).toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "1794680");
    await userEvent.click(screen.getByRole("button", { name: "Load game report" }));
    expect(await screen.findByText("Loaded Vampire Survivors.")).toBeInTheDocument();
    expect(input).toHaveValue("Vampire Survivors");
    await waitFor(() => expect(calls.some((c) => c.url.includes("/views"))).toBe(true));
  });

  it("resets filters to defaults", async () => {
    const calls = mockFetch(() => ({ count: 1, count_ignoring_history: 1, all_seen: false }));
    render(<Harness sessionId="test-session-5" />);
    const minRevenue = document.querySelector<HTMLInputElement>("#minRevenue")!;
    await userEvent.clear(minRevenue);
    await userEvent.type(minRevenue, "5");
    await waitFor(() =>
      expect(calls.at(-1)?.body).toMatchObject({ filters: { min_revenue: 5 } }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(minRevenue).toHaveValue(150000);
    expect(screen.getByText("Filters reset.")).toBeInTheDocument();
  });

  it("adds the current game to Studies and refreshes the count", async () => {
    let inStudies = false;
    const calls = mockFetch((url, init) => {
      if (url.endsWith("/count"))
        return { count: inStudies ? 4 : 5, count_ignoring_history: 5, all_seen: false };
      if (url.includes("/api/games/resolve")) return VAMPIRE;
      if (url.includes("/views")) return { items: [summary] };
      if (url.includes("/api/games?q=")) return { items: [summary] };
      if (url === `/api/studies/${VAMPIRE.appid}` && init?.method === "PUT") {
        inStudies = true;
        return { ...VAMPIRE, study: { in_studies: true, added_at: "2026-11-06T10:00:00", added_by: "pc-1" } };
      }
      throw new Error(`unexpected ${url}`);
    });
    render(<Harness sessionId="test-session-6" />);
    await userEvent.type(screen.getByLabelText("Game name or AppID"), "1794680{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: /Add to Studies/ }));
    expect(
      await screen.findByText("Added Vampire Survivors to Studies - it won't be suggested again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "✓ In Studies" })).toBeInTheDocument();
    expect(await screen.findByText("4 matches")).toBeInTheDocument();
    const countBody = calls.filter((c) => c.url.endsWith("/count")).at(-1)?.body;
    expect(countBody).toMatchObject({ exclude_studies: true, filters: { require_english: false } });
  });

  it("renders the shell: badge, tabs, and Settings from the gear icon", async () => {
    const settings = {
      app_dir: "G:\\Tools\\SteamStudyTool",
      settings_file: "G:\\Tools\\SteamStudyTool\\settings.json",
      data_dir: "data",
      data_dir_resolved: "G:\\Tools\\SteamStudyTool\\data",
      export_dir: "studiesJPG",
      export_dir_resolved: "G:\\Tools\\SteamStudyTool\\studiesJPG",
      qualification_min_revenue_usd: 100000,
      offline_mode: false,
      offline_forced: false,
      steam_api_key_set: false,
      steam_store_requests_per_minute: 35,
      llm_provider: "none",
      llm_model: "",
      llm_api_key_set: false,
      warning: null,
    };
    let metaCalls = 0;
    const calls = mockFetch((url, init) => {
      if (url === "/api/meta") {
        metaCalls += 1;
        return META;
      }
      if (url.endsWith("/count")) return { count: 5, count_ignoring_history: 5, all_seen: false };
      if (url === "/api/settings" && init?.method === "PUT")
        return { ...settings, qualification_min_revenue_usd: 120000 };
      if (url === "/api/settings") return settings;
      throw new Error(`unexpected ${url}`);
    });
    render(<App />);
    expect(await screen.findByText("3,704 qualified games")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Suggest" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Suggest", "Charts", "Data"]);

    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(await screen.findByText("G:\\Tools\\SteamStudyTool\\data")).toBeInTheDocument();
    const floor = document.querySelector<HTMLInputElement>("#settingsFloor")!;
    await userEvent.clear(floor);
    await userEvent.type(floor, "120000");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Settings saved.")).toBeInTheDocument();
    const put = calls.find((c) => c.url === "/api/settings" && c.body);
    expect(put?.body).toMatchObject({
      qualification_min_revenue_usd: 120000,
      steam_api_key: null,
      llm_api_key: null,
    });
    await waitFor(() => expect(metaCalls).toBe(2)); // data changed -> meta reloaded
  });
});
