/**
 * Typed API client for the Pharma Intelligence backend.
 *
 * The access token is kept in memory and mirrored to localStorage so a page
 * reload keeps the session. Every request attaches the bearer token and turns
 * non-2xx responses into an ApiError carrying the backend's error envelope.
 */

import type {
  ActiveMoiety,
  Alert,
  AlertSummary,
  CopilotAnswer,
  DashboardCharts,
  DetectedChange,
  FtfRecord,
  FtfSummary,
  GraphNeighborhood,
  GraphStats,
  Insight,
  Kpis,
  OrangeBookPatent,
  OrangeBookProduct,
  OrangeBookSummary,
  OrangeBookSupplement,
  Page,
  PdeSummary,
  PipelineRun,
  PteApplication,
  PteCertificate,
  PteSummary,
  SavedView,
  SearchResult,
  SourceDefinition,
  TokenResponse,
} from "@/types/api";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;
const TOKEN_KEY = "pharma.token";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let accessToken: string | null = null;

export function setToken(token: string | null) {
  accessToken = token;
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export function getToken(): string | null {
  if (accessToken) return accessToken;
  if (typeof window === "undefined") return null;
  accessToken = window.localStorage.getItem(TOKEN_KEY);
  return accessToken;
}

export function clearToken() {
  setToken(null);
}

function qs(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.append(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers, cache: "no-store" });
  } catch (error) {
    throw new ApiError(0, "network_error", `Cannot reach the API at ${BASE}`, error);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const body = text ? safeJson(text) : null;

  if (!response.ok) {
    const envelope = (body as { error?: { code?: string; message?: string; details?: unknown } })?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "http_error",
      envelope?.message ?? response.statusText,
      envelope?.details,
    );
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  // ---- Auth ----
  async login(username: string, password: string): Promise<TokenResponse> {
    const data = await request<TokenResponse>("/auth/token", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(data.access_token);
    return data;
  },
  me: () => request<{ username: string; role: string; permissions: string[] }>("/auth/me"),

  async register(payload: { full_name: string; email: string; password: string }): Promise<{
    id: string;
    email: string;
    full_name: string;
    role: string;
  }> {
    return request("/auth/register", { method: "POST", body: JSON.stringify(payload) });
  },

  // ---- Dashboard ----
  kpis: async (): Promise<{ kpis: Kpis; alerts: AlertSummary }> => {
    const raw = await request<{ kpis: Kpis; alerts: AlertSummary & { open_total?: number; by_priority?: Record<string, number> } }>(
      "/dashboard/kpis",
    );
    const by = raw.alerts?.by_priority ?? {};
    return {
      kpis: raw.kpis,
      alerts: {
        ...raw.alerts,
        open: raw.alerts?.open ?? raw.alerts?.open_total ?? 0,
        critical: raw.alerts?.critical ?? by.critical ?? 0,
        high: raw.alerts?.high ?? by.high ?? 0,
        medium: raw.alerts?.medium ?? by.medium ?? 0,
        low: raw.alerts?.low ?? by.low ?? 0,
      },
    };
  },
  moduleSummaries: () => request<Record<string, Record<string, number>>>("/dashboard/module-summaries"),
  charts: () => request<DashboardCharts>("/dashboard/charts/all"),

  // ---- FTF ----
  ftfRecords: (params?: Record<string, unknown>) =>
    request<Page<FtfRecord>>(`/ftf/records${qs(params)}`),
  ftfSummary: () => request<FtfSummary>("/ftf/summary"),
  ftfSource: () =>
    request<{
      source_code?: string;
      filename?: string | null;
      version?: number;
      record_count?: number;
      publication_date: string | null;
      publication_label: string | null;
      fetched_at?: string | null;
      url?: string;
    }>("/ftf/source"),
  ftfMonthlyTrend: (months = 36) =>
    request<Array<{ month: string; count: number }>>(`/ftf/analytics/monthly-trend${qs({ months })}`),
  ftfTherapyAreas: (limit = 10) =>
    request<Array<{ therapy_area: string; filings: number }>>(
      `/ftf/analytics/therapy-areas${qs({ limit })}`,
    ),

  // ---- PTE ----
  pteApplications: (params?: Record<string, unknown>) =>
    request<Page<PteApplication>>(`/pte/applications${qs(params)}`),
  pteCertificates: (params?: Record<string, unknown>) =>
    request<Page<PteCertificate>>(`/pte/certificates${qs(params)}`),
  pteSummary: () => request<PteSummary>("/pte/summary"),
  pteMonthlyTrend: (months = 60) =>
    request<Array<{ month: string; count: number }>>(`/pte/analytics/monthly-trend${qs({ months })}`),
  pteExtensionDistribution: () =>
    request<Array<{ band: string; count: number }>>("/pte/analytics/extension-distribution"),

  // ---- PDE ----
  pdeMoieties: (params?: Record<string, unknown>) =>
    request<Page<ActiveMoiety>>(`/pde/moieties${qs(params)}`),
  pdeSummary: () => request<PdeSummary>("/pde/summary"),
  pdeYearlyTrend: (years = 15) =>
    request<Array<{ year: number; count: number }>>(`/pde/analytics/yearly-trend${qs({ years })}`),
  pdeTopSponsors: (limit = 15) =>
    request<Array<{ sponsor: string; count: number }>>(`/pde/analytics/top-sponsors${qs({ limit })}`),

  // ---- Orange Book ----
  obProducts: (params?: Record<string, unknown>) =>
    request<Page<OrangeBookProduct>>(`/orange-book/products${qs(params)}`),
  obPatents: (params?: Record<string, unknown>) =>
    request<Page<OrangeBookPatent>>(`/orange-book/patents${qs(params)}`),
  obSupplements: (limit = 24) =>
    request<OrangeBookSupplement[]>(`/orange-book/supplements${qs({ limit })}`),
  obCompare: () => request<Record<string, unknown>>("/orange-book/supplements/compare"),
  obDocuments: () =>
    request<
      Array<{
        id: string;
        source_code: string;
        filename: string;
        url: string;
        version?: string | null;
        is_current: boolean;
        byte_size?: number | null;
        publication_date?: string | null;
        fetched_at?: string | null;
      }>
    >("/orange-book/documents"),
  obSummary: () => request<OrangeBookSummary>("/orange-book/summary"),

  // ---- Changes / insights ----
  changes: (params?: Record<string, unknown>) =>
    request<Page<DetectedChange>>(`/changes${qs(params)}`),
  insights: (params?: Record<string, unknown>) => request<Page<Insight>>(`/insights${qs(params)}`),

  // ---- Alerts ----
  alerts: (params?: Record<string, unknown>) => request<Page<Alert>>(`/alerts${qs(params)}`),
  alertSummary: async (): Promise<AlertSummary> => {
    const raw = await request<AlertSummary & { open_total?: number; by_priority?: Record<string, number> }>(
      "/alerts/summary",
    );
    const by = raw.by_priority ?? {};
    return {
      ...raw,
      open: raw.open ?? raw.open_total ?? 0,
      critical: raw.critical ?? by.critical ?? 0,
      high: raw.high ?? by.high ?? 0,
      medium: raw.medium ?? by.medium ?? 0,
      low: raw.low ?? by.low ?? 0,
    };
  },
  updateAlert: (id: string, body: { status?: string; acknowledged_by?: string }) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  // ---- Search / graph ----
  search: (q: string, limit = 25) => request<SearchResult>(`/search${qs({ q, limit })}`),
  drug360: (id: string) => request<Record<string, unknown>>(`/drugs/${id}/360`),
  graphStats: () => request<GraphStats>("/graph/stats"),
  graphNeighborhood: (type: string, key: string, depth = 2) =>
    request<GraphNeighborhood>(
      `/graph/nodes/${encodeURIComponent(type)}/${encodeURIComponent(key)}/neighborhood${qs({ depth })}`,
    ),

  // ---- Copilot ----
  copilotAsk: (question: string, useLlm = true, conversationId?: string) =>
    request<CopilotAnswer>("/copilot/ask", {
      method: "POST",
      body: JSON.stringify({ question, use_llm: useLlm, conversation_id: conversationId }),
    }),
  copilotSuggested: () => request<string[]>("/copilot/suggested-questions"),

  // ---- Sources / pipeline ----
  sources: () => request<SourceDefinition[]>("/sources"),
  pipelineRuns: (limit = 20) => request<Page<PipelineRun>>(`/pipeline/runs${qs({ page_size: limit })}`),
  triggerPipeline: (body: Record<string, unknown> = {}) =>
    request<{ status: string; message: string }>("/pipeline/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ---- Saved views ----
  savedViews: () => request<SavedView[]>("/dashboard/views"),
  createView: (body: Record<string, unknown>) =>
    request<SavedView>("/dashboard/views", { method: "POST", body: JSON.stringify(body) }),
  deleteView: (id: string) =>
    request<{ deleted: boolean }>(`/dashboard/views/${id}`, { method: "DELETE" }),

  // ---- Exports (browser download) ----
  exportUrl: (path: string, params?: Record<string, unknown>) => `${API}${path}${qs(params)}`,
};

export { BASE as API_BASE };
