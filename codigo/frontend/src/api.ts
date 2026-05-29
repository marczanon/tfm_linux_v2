import type {
  ApiRunRequest,
  ApiRunResponse,
  DatasetAdapterInfo,
  DatasetDescribeRequest,
  DatasetDescribeResponse,
  HealthResponse,
  ApiRunJobStatus,
  AgentRuntimeEvent,
  ArtifactRef,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunSnapshot,
  AgentMemoryTarget,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  MemoryRole,
  ReasoningMemoryRecord,
} from "./types";

const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL ?? "/api");

export class ApiClientError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.detail = detail;
  }
}

export async function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}

export async function listRuns(filters: Partial<RunFilters> = {}): Promise<RunIndexEntry[]> {
  const query = new URLSearchParams();
  if (filters.dataset) {
    query.set("dataset", filters.dataset);
  }
  if (filters.current_stage) {
    query.set("current_stage", filters.current_stage);
  }
  if (filters.approved !== undefined && filters.approved !== null) {
    query.set("approved", String(filters.approved));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<RunIndexEntry[]>(`/runs${suffix}`);
}

export async function getRun(runId: string): Promise<RunSnapshot> {
  return apiRequest<RunSnapshot>(`/runs/${encodeURIComponent(runId)}`);
}

export async function getRunArtifacts(runId: string): Promise<ArtifactRef[]> {
  return apiRequest<ArtifactRef[]>(`/runs/${encodeURIComponent(runId)}/artifacts`);
}

export async function getRunReport(runId: string): Promise<string> {
  return apiTextRequest(`/runs/${encodeURIComponent(runId)}/report`);
}

export async function compareRuns(runIds: string[]): Promise<RunComparison> {
  const query = new URLSearchParams();
  for (const runId of runIds) {
    query.append("run_ids", runId);
  }
  return apiRequest<RunComparison>(`/runs/compare?${query.toString()}`);
}

export async function listDatasetAdapters(): Promise<DatasetAdapterInfo[]> {
  return apiRequest<DatasetAdapterInfo[]>("/datasets/adapters");
}

export async function describeDataset(
  payload: DatasetDescribeRequest,
): Promise<DatasetDescribeResponse> {
  return apiRequest<DatasetDescribeResponse>("/datasets/describe", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createDryRun(payload: ApiRunRequest): Promise<ApiRunResponse> {
  return apiRequest<ApiRunResponse>("/runs", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      dry_run: true,
      background: false,
    }),
  });
}

export async function createBackgroundRun(
  payload: ApiRunRequest,
): Promise<ApiRunResponse> {
  return apiRequest<ApiRunResponse>("/runs", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      dry_run: false,
      background: true,
    }),
  });
}

export async function getRunJob(jobId: string): Promise<ApiRunJobStatus> {
  return apiRequest<ApiRunJobStatus>(`/run-jobs/${encodeURIComponent(jobId)}`);
}

export async function getRunJobEvents(
  jobId: string,
  afterSequence: number | null = null,
): Promise<AgentRuntimeEvent[]> {
  const query = new URLSearchParams();
  if (afterSequence !== null) {
    query.set("after_sequence", String(afterSequence));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<AgentRuntimeEvent[]>(
    `/run-jobs/${encodeURIComponent(jobId)}/events${suffix}`,
  );
}

export async function listMemoryCollections(): Promise<MemoryCollectionSummary[]> {
  return apiRequest<MemoryCollectionSummary[]>("/memory/collections");
}

export async function listMemoryRecords(filters: {
  target_agent?: AgentMemoryTarget | null;
  dataset?: string | null;
  memory_role?: MemoryRole | null;
  reusable_only?: boolean;
  search_text?: string | null;
} = {}): Promise<MemoryRecordSummary[]> {
  const query = new URLSearchParams();
  if (filters.target_agent) {
    query.set("target_agent", filters.target_agent);
  }
  if (filters.dataset) {
    query.set("dataset", filters.dataset);
  }
  if (filters.memory_role) {
    query.set("memory_role", filters.memory_role);
  }
  if (filters.reusable_only !== undefined) {
    query.set("reusable_only", String(filters.reusable_only));
  }
  if (filters.search_text) {
    query.set("search_text", filters.search_text);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<MemoryRecordSummary[]>(`/memory/records${suffix}`);
}

export async function getMemoryRecord(
  memoryRecordId: string,
): Promise<ReasoningMemoryRecord> {
  return apiRequest<ReasoningMemoryRecord>(
    `/memory/records/${encodeURIComponent(memoryRecordId)}`,
  );
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ApiClientError(response.status, errorMessage(response, detail), detail);
  }

  return (await response.json()) as T;
}

async function apiTextRequest(path: string, init: RequestInit = {}): Promise<string> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "text/markdown,text/plain,*/*",
      ...init.headers,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorDetail(response);
    throw new ApiClientError(response.status, errorMessage(response, detail), detail);
  }

  return response.text();
}

async function parseErrorDetail(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorMessage(response: Response, detail: unknown): string {
  if (isApiDetail(detail)) {
    if (typeof detail.detail === "string") {
      return detail.detail;
    }
    return JSON.stringify(detail.detail);
  }
  if (typeof detail === "string") {
    return detail;
  }
  return `HTTP ${response.status} ${response.statusText}`;
}

function isApiDetail(value: unknown): value is { detail: unknown } {
  return typeof value === "object" && value !== null && "detail" in value;
}

function normalizeBaseUrl(value: string): string {
  if (value === "/") {
    return "";
  }
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
