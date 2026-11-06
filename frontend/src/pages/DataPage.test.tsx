import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { binLabel, compactNumber, compactUsd } from "../lib/chartTheme";
import { META } from "../tests/fixtures";
import { DataPage, duration } from "./DataPage";

const IDLE_JOB = {
  job_id: "",
  kind: "",
  label: "",
  state: "idle",
  total: 0,
  done: 0,
  counters: {},
  requests: 0,
  started_at: null,
  finished_at: null,
  eta_seconds: null,
  message: "",
  recent: [],
};

const STATUS = {
  data_dir: "G:\\Tools\\SteamStudyTool\\data",
  total_games: 15521,
  qualified_games: 3704,
  legacy_unchanged: 15521,
  refreshed: 0,
  discovered: 0,
  years: { "2022": 3946 },
  last_update: null,
  discovery_cursor_appid: 3650000,
  listed_not_screened: 0,
  languages_known: 0,
  steam_api_key_set: false,
  offline: false,
  qualification_threshold_usd: 100000,
  observation_files: [],
  seconds_per_request: { store: 1.7, reviews: 1.7, steamspy: 1.2, applist: 1 },
  job: IDLE_JOB,
};

function mock(handler: (url: string, body: unknown) => unknown) {
  const calls: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, body });
      return new Response(JSON.stringify(handler(url, body)), { status: 200 });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("DataPage", () => {
  it("shows status, estimates per action, and starts a refresh job", async () => {
    // Like the real backend: status and /jobs/current report the same (latest) job.
    let job: Record<string, unknown> = IDLE_JOB;
    const changed: number[] = [];
    const notes: string[] = [];
    const calls = mock((url, body) => {
      if (url === "/api/data/status") return { ...STATUS, job };
      if (url === "/api/data/jobs/preview") {
        const kind = (body as { kind: string }).kind;
        return { items: kind === "discover" ? 500 : 3704, requests: 7408, seconds: 7400, needs_key: kind === "discover", notes: [] };
      }
      if (url === "/api/data/jobs") {
        job = { ...IDLE_JOB, kind: "refresh", label: "Refresh existing games", state: "running", total: 3704, done: 10, requests: 20, eta_seconds: 3600 };
        return job;
      }
      if (url === "/api/data/jobs/current") {
        job = { ...IDLE_JOB, kind: "refresh", label: "Refresh existing games", state: "completed", total: 3704, done: 3704, message: "Refreshed 3704 games.", counters: { reviews_updated: 3704 } };
        return job;
      }
      throw new Error(`unexpected ${url}`);
    });
    render(
      <DataPage
        active
        meta={META}
        notify={(m) => notes.push(m)}
        onDataChanged={() => changed.push(1)}
        onOpenSettings={() => undefined}
      />,
    );
    expect(await screen.findByText("15,521")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("refresh-estimate")).toHaveTextContent("3,704 games · ≈ 7,408 requests · ≈ 2.1 h"),
    );

    // Defaults: qualified games, reviews + store, skip if updated within 7 days.
    const refreshPreview = calls.find((c) => c.url === "/api/data/jobs/preview" && (c.body as { kind: string }).kind === "refresh");
    expect(refreshPreview?.body).toMatchObject({
      refresh: { scope: "qualified", years: [], parts: ["reviews", "store"], stale_days: 7 },
    });

    // Discovery needs a key.
    expect(screen.getByRole("button", { name: "Find new games" })).toBeDisabled();
    expect(screen.getByText("not set")).toBeInTheDocument();

    // Year selection narrows the scope.
    await userEvent.click(document.querySelector<HTMLButtonElement>("#refresh-year-2023")!);
    await waitFor(() =>
      expect(calls.at(-1)?.body).toMatchObject({ refresh: { years: [2023] } }),
    );

    await userEvent.click(screen.getByRole("button", { name: "Update games" }));
    expect(await screen.findByTestId("job-panel")).toHaveTextContent("about 60 min left");
    await waitFor(() => expect(changed.length).toBe(1), { timeout: 4000 });
    expect(notes.at(-1)).toContain("Refreshed 3704 games.");
    expect(screen.getByTestId("job-panel")).toHaveTextContent("3,704 reviews updated");
  });

  it("disables everything offline", async () => {
    mock((url) => {
      if (url === "/api/data/status") return { ...STATUS, offline: true };
      return { items: 1, requests: 1, seconds: 1, needs_key: false, notes: [] };
    });
    render(
      <DataPage active meta={META} notify={() => undefined} onDataChanged={() => undefined} onOpenSettings={() => undefined} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Offline mode is on");
    await waitFor(() => expect(screen.getByRole("button", { name: "Update games" })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Look up languages" })).toBeDisabled();
  });
});

describe("formatting helpers", () => {
  it("formats durations and compact values", () => {
    expect(duration(30)).toBe("30 s");
    expect(duration(600)).toBe("10 min");
    expect(duration(7400)).toBe("2.1 h");
    expect(compactUsd(150_000)).toBe("$150K");
    expect(compactUsd(42_131_212)).toBe("$42M");
    expect(compactUsd(2_500_000)).toBe("$2.5M");
    expect(compactNumber(12_345)).toBe("12K");
    expect(compactNumber(950)).toBe("950");
    expect(binLabel(100_000, 200_000)).toBe("$100K–$200K");
    expect(binLabel(100_000_000, null)).toBe("$100M+");
  });
});
