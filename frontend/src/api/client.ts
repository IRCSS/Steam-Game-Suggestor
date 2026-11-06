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
};
