import type { components } from "./schema";

type Schemas = components["schemas"];
export type GameReport = Schemas["GameReport"];
export type GameSummary = Schemas["GameSummary"];
export type MetaResponse = Schemas["MetaResponse"];
export type StudyFilters = Schemas["StudyFiltersModel"];
export type SuggestionQuery = Schemas["SuggestionQuery"];
export type SuggestionRequest = Schemas["SuggestionRequest"];
export type SuggestionResponse = Schemas["SuggestionResponse"];
export type CountResponse = Schemas["CountResponse"];
export type HistoryResponse = Schemas["HistoryResponse"];
export type SettingsView = Schemas["SettingsView"];
export type SettingsUpdate = Schemas["SettingsUpdate"];
export type StudiesResponse = Schemas["StudiesResponse"];
export type StudyItem = Schemas["StudyItem"];
export type LanguageStatus = Schemas["LanguageStatusResponse"];
export type JpegExportResponse = Schemas["JpegExportResponse"];
export type DatasetExportResponse = Schemas["DatasetExportResponse"];
export type DataStatus = Schemas["DataStatus"];
export type JobView = Schemas["JobView"];
export type JobRequest = Schemas["JobRequest"];
export type JobPreview = Schemas["JobPreview"];
export type RefreshOptions = Schemas["RefreshOptions"];
export type DiscoverOptions = Schemas["DiscoverOptions"];
export type ChartsRequest = Schemas["ChartsRequest"];
export type ChartsResponse = Schemas["ChartsResponse"];
export type HistoryResponse2 = Schemas["HistoryResponseModel"];
export type ResearchView = Schemas["ResearchView"];
export type ResearchStatus = Schemas["ResearchStatus"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "The local backend is not reachable.");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

const post = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
  signal,
});

export const api = {
  meta: () => request<MetaResponse>("/api/meta"),
  search: (q: string, signal?: AbortSignal) =>
    request<{ items: GameSummary[] }>(`/api/games?q=${encodeURIComponent(q)}&limit=12`, {
      signal,
    }),
  resolve: (q: string) => request<GameReport>(`/api/games/resolve?q=${encodeURIComponent(q)}`),
  game: (appid: number) => request<GameReport>(`/api/games/${appid}`),
  count: (body: SuggestionQuery, signal?: AbortSignal) =>
    request<CountResponse>("/api/suggestions/count", post(body, signal)),
  suggest: (body: SuggestionRequest) =>
    request<SuggestionResponse>("/api/suggestions", post(body)),
  history: (sessionId: string) =>
    request<HistoryResponse>(`/api/sessions/${sessionId}/history`),
  recordView: (sessionId: string, appid: number) =>
    request<HistoryResponse>(`/api/sessions/${sessionId}/views`, post({ appid })),
  clearHistory: (sessionId: string) =>
    request<HistoryResponse>(`/api/sessions/${sessionId}/clear`, post({})),

  studies: () => request<StudiesResponse>("/api/studies"),
  addStudy: (appid: number) => request<GameReport>(`/api/studies/${appid}`, { method: "PUT" }),
  removeStudy: (appid: number) =>
    request<GameReport>(`/api/studies/${appid}`, { method: "DELETE" }),

  settings: () => request<SettingsView>("/api/settings"),
  saveSettings: (body: SettingsUpdate) =>
    request<SettingsView>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),

  languageStatus: () => request<LanguageStatus>("/api/languages/status"),

  dataStatus: () => request<DataStatus>("/api/data/status"),
  previewJob: (body: JobRequest, signal?: AbortSignal) =>
    request<JobPreview>("/api/data/jobs/preview", post(body, signal)),
  startJob: (body: JobRequest) => request<JobView>("/api/data/jobs", post(body)),
  currentJob: () => request<JobView>("/api/data/jobs/current"),
  cancelJob: () => request<JobView>("/api/data/jobs/cancel", post({})),
  testSteamKey: () => request<{ ok: boolean; message: string }>("/api/data/test-key", post({})),

  charts: (body: ChartsRequest, signal?: AbortSignal) =>
    request<ChartsResponse>("/api/charts/overview", post(body, signal)),
  gameHistory: (appid: number) => request<HistoryResponse2>(`/api/charts/history/${appid}`),

  researchStatus: () => request<ResearchStatus>("/api/research/status"),
  research: (appid: number) => request<ResearchView>(`/api/research/${appid}`),
  startResearch: (appid: number, kind: Schemas["StartResearchRequest"]["kind"]) =>
    request<JobView>(`/api/research/${appid}`, post({ kind })),
  researchJob: () => request<JobView>("/api/research/job"),
  cancelResearch: () => request<JobView>("/api/research/job/cancel", post({})),

  artworkUrl: (appid: number) => `/api/games/${appid}/artwork`,
  exportJpeg: (appid: number, imageBase64: string) =>
    request<JpegExportResponse>("/api/exports/jpeg", post({ appid, image_base64: imageBase64 })),
  exportDataset: () => request<DatasetExportResponse>("/api/exports/dataset", post({})),
  openFolder: async (target: "data" | "export" | "app") => {
    const response = await fetch("/api/system/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
    if (!response.ok) throw new ApiError(response.status, "Could not open the folder.");
  },
};
