import type { Page, Route } from "@playwright/test";

import type {
  DatasetAdapterInfo,
  HealthResponse,
  LLMStatusResponse,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  MemoryStatusResponse,
  MonitoringSessionCreateRequest,
  MonitoringSessionView,
  MonitoringReviewDispatchRequest,
  MonitoringStepRequest,
  MonitoringStepResponse,
  ReasoningMemoryRecord,
} from "../../../src/types";
import {
  EXACT_SEVEN_AGENTS_SCENARIO,
  agentRunScenario,
  type AgentRunScenario,
  type AgentRunScenarioId,
} from "../fixtures/agentRuns";
import {
  MONITORING_REVIEW_GATE_FIXTURE,
  MONITORING_REPLAY_SCENARIO,
  type MonitoringReplayScenario,
} from "../fixtures/monitoringReplay";

export interface MockApiController {
  assertNoUnhandledApiRequests(): void;
  dispose(): Promise<void>;
  readonly unhandledApiRequests: string[];
}

export interface MonitoringMockApiController extends MockApiController {
  readonly campaignRequests: number;
  readonly dispatchRequests: MonitoringReviewDispatchRequest[];
  readonly sessionRequests: MonitoringSessionCreateRequest[];
  readonly sessionGetRequests: number;
  readonly stepRequests: MonitoringStepRequest[];
  readonly tickListAfterSequences: number[];
  releaseDispatchResponse(): void;
}

export const FIXTURE_MEMORY_RECORDS: MemoryRecordSummary[] = [
  memoryRecord(
    "mem-compatible",
    "positive_example",
    "Ejemplo oficial compatible para seleccionar un detector no supervisado.",
  ),
  memoryRecord(
    "mem-effective",
    "positive_example",
    "Antecedente oficial recuperable que el agente puede decidir no utilizar.",
  ),
  memoryRecord(
    "mem-filtered",
    "boundary_case",
    "Caso de frontera valido en el corpus, pero no necesariamente aplicable a cada perfil.",
  ),
];

export const FIXTURE_MEMORY_COLLECTIONS: MemoryCollectionSummary[] = [
  {
    collection_name: "modeler_memory",
    datasets: ["nasa_ims_bearing"],
    human_verdicts: { correct: 3 },
    latest_created_at: "2026-08-09T12:00:00.000Z",
    memory_roles: { boundary_case: 1, positive_example: 2 },
    n_excluded: 0,
    n_records: 3,
    n_reusable: 3,
    source_types: { decision_episode: 3 },
    target_agent: "modeler",
  },
];

export const FIXTURE_MEMORY_STATUS: MemoryStatusResponse = {
  backend: {
    backend_name: "qdrant",
    configured_backend: "qdrant",
    diagnostic: null,
    embedding_model: "nomic-embed-text:fixture",
    error_type: null,
    operational: true,
  },
  checked_at: "2026-08-10T09:30:00.000Z",
  corpus: {
    available: true,
    candidate_queue_available: true,
    candidate_queue_diagnostic: null,
    candidate_queue_error_type: null,
    corpus_fingerprint: "fixture-corpus-modeler-v1",
    frozen_manifest_available: true,
    n_reusable_agents: 1,
    n_reusable_datasets: 1,
    official_records: 3,
    official_reusable_records: 3,
    pending_candidates: 0,
    reusable_agent_coverage: ["modeler"],
    reusable_dataset_coverage: ["nasa_ims_bearing"],
    reusable_records: 3,
    shared_methodology_records: 0,
    shared_methodology_reusable_records: 0,
    total_records: 3,
  },
  scientific_readiness: {
    blockers: [
      {
        code: "insufficient_dataset_coverage",
        message: "La fixture solo cubre un dataset y no representa un benchmark cientifico.",
      },
      {
        code: "insufficient_agent_coverage",
        message: "La fixture solo cubre la memoria del modelador.",
      },
    ],
    minimum_reusable_agents: 3,
    minimum_reusable_datasets: 2,
    ready_for_memory_effect_benchmark: false,
  },
};

const FIXTURE_HEALTH: HealthResponse = {
  allowed_raw_roots: ["/fixtures/data"],
  dataset_uploads_dir: "/fixtures/uploads",
  memory_dir: "/fixtures/memory",
  runs_dir: "/fixtures/runs",
  status: "ok",
};

const FIXTURE_LLM_STATUS: LLMStatusResponse = {
  available: true,
  detail: null,
  host: "http://fixture-llm.invalid",
  model: "qwen3.5:fixture",
  model_available: true,
  models: ["qwen3.5:fixture"],
  provider: "ollama",
  think: false,
  timeout_seconds: 30,
};

const FIXTURE_ADAPTERS: DatasetAdapterInfo[] = [
  {
    adapter_id: "nasa_ims_bearing",
    dataset_id: "nasa_ims_bearing",
    display_name: "NASA IMS Bearing · fixture E2E",
    is_experimental: false,
    notes: "Adaptador simulado; no ejecuta procesamiento de datos.",
    supported_source_formats: ["directory"],
    supports_descriptor: true,
    supports_manifest: true,
  },
];

/**
 * Instala un backend API determinista para probar la vista Agentes.
 *
 * El corpus global es deliberadamente identico en todos los escenarios. La
 * condicion RAG solo se codifica en `/runs/:id/events`; el indice y snapshot
 * reflejan el identificador y los recuentos de esa traza. Toda URL API no
 * contemplada responde 501 y queda registrada.
 */
export async function installAgentMockApi(
  page: Page,
  selectedScenario: AgentRunScenario | AgentRunScenarioId =
    EXACT_SEVEN_AGENTS_SCENARIO,
): Promise<MockApiController> {
  const scenario = typeof selectedScenario === "string"
    ? agentRunScenario(selectedScenario)
    : selectedScenario;
  const unhandledApiRequests: string[] = [];

  const handler = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    const path = url.pathname;

    if (method !== "GET") {
      return unhandled(route, unhandledApiRequests, method, url);
    }

    if (path === "/api/health") {
      return json(route, FIXTURE_HEALTH);
    }
    if (path === "/api/llm/status") {
      return json(route, FIXTURE_LLM_STATUS);
    }
    if (path === "/api/datasets/adapters") {
      return json(route, FIXTURE_ADAPTERS);
    }
    if (path === "/api/runs") {
      return json(route, [scenario.run]);
    }

    const runPath = `/api/runs/${encodeURIComponent(scenario.run.run_id)}`;
    if (path === runPath) {
      return json(route, scenario.snapshot);
    }
    if (path === `${runPath}/artifacts`) {
      return json(route, []);
    }
    if (path === `${runPath}/events`) {
      return json(route, scenario.events);
    }
    if (
      path === `${runPath}/report`
      || path === `${runPath}/audit-report`
      || path === `${runPath}/report-debate`
    ) {
      return text(route, "");
    }
    if (path === `${runPath}/visualization`) {
      return json(route, null);
    }

    if (path === "/api/memory/status") {
      return json(route, FIXTURE_MEMORY_STATUS);
    }
    if (path === "/api/memory/collections") {
      return json(route, FIXTURE_MEMORY_COLLECTIONS);
    }
    if (path === "/api/memory/records") {
      return json(route, filteredMemoryRecords(url));
    }
    const memoryRecordPrefix = "/api/memory/records/";
    if (path.startsWith(memoryRecordPrefix)) {
      const memoryRecordId = decodeURIComponent(path.slice(memoryRecordPrefix.length));
      const record = FIXTURE_MEMORY_RECORDS.find(
        (candidate) => candidate.memory_record_id === memoryRecordId,
      );
      return record
        ? json(route, detailedMemoryRecord(record))
        : notFound(route, `Recuerdo no incluido en la fixture: ${memoryRecordId}`);
    }

    return unhandled(route, unhandledApiRequests, method, url);
  };

  await page.route("**/api/**", handler);

  return {
    assertNoUnhandledApiRequests() {
      if (unhandledApiRequests.length > 0) {
        throw new Error(
          `Llamadas API E2E no manejadas:\n${unhandledApiRequests.join("\n")}`,
        );
      }
    },
    async dispose() {
      await page.unroute("**/api/**", handler);
    },
    unhandledApiRequests,
  };
}

/** Alias corto para specs. */
export const mockAgentApi = installAgentMockApi;

/** Backend cerrado para el replay: cada step avanza una fixture causal conocida. */
export async function installMonitoringMockApi(
  page: Page,
  selectedScenario: MonitoringReplayScenario = MONITORING_REPLAY_SCENARIO,
): Promise<MonitoringMockApiController> {
  const scenario = structuredClone(selectedScenario);
  const unhandledApiRequests: string[] = [];
  const sessionRequests: MonitoringSessionCreateRequest[] = [];
  const stepRequests: MonitoringStepRequest[] = [];
  const dispatchRequests: MonitoringReviewDispatchRequest[] = [];
  let campaignRequests = 0;
  let latestCampaign = scenario.campaign ?? scenario.campaignUpdates?.[0] ?? null;
  let sessionGetRequests = 0;
  const tickListAfterSequences: number[] = [];
  let currentSession: MonitoringSessionView = structuredClone(scenario.initialSession);
  let nextStepIndex = 0;
  let releaseDispatchGate: () => void = () => undefined;
  const dispatchGate = scenario.dispatch
    ? new Promise<void>((resolve) => {
        releaseDispatchGate = resolve;
      })
    : Promise.resolve();

  const handler = async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method().toUpperCase();
    const path = url.pathname;

    if (method === "GET" && path === "/api/health") {
      return json(route, FIXTURE_HEALTH);
    }
    if (method === "GET" && path === "/api/llm/status") {
      return json(route, FIXTURE_LLM_STATUS);
    }
    if (method === "GET" && path === "/api/datasets/adapters") {
      return json(route, FIXTURE_ADAPTERS);
    }
    if (method === "GET" && path === "/api/runs") {
      return json(route, []);
    }
    if (method === "GET" && path === "/api/monitoring/review-gates/current") {
      return json(route, MONITORING_REVIEW_GATE_FIXTURE);
    }
    if (method === "GET" && path === "/api/monitoring/evidence-campaigns/current") {
      campaignRequests += 1;
      if (
        scenario.campaignFailure &&
        campaignRequests > scenario.campaignFailure.afterRequestCount &&
        (
          scenario.campaignFailure.untilRequestCount === undefined ||
          campaignRequests <= scenario.campaignFailure.untilRequestCount
        )
      ) {
        return json(
          route,
          { detail: "Fallo de campaña inyectado por la fixture." },
          scenario.campaignFailure.status,
        );
      }
      const updates = scenario.campaignUpdates;
      latestCampaign = updates?.length
        ? updates[Math.min(campaignRequests - 1, updates.length - 1)]
        : scenario.campaign ?? null;
      return latestCampaign
        ? json(route, latestCampaign)
        : notFound(route, "Campaña de evidencia no publicada en esta fixture.");
    }
    if (
      method === "GET" &&
      scenario.childJob &&
      path === `/api/run-jobs/${encodeURIComponent(scenario.childJob.job_id)}`
    ) {
      return json(route, scenario.childJob);
    }
    if (
      method === "GET" &&
      scenario.childJob &&
      path === `/api/run-jobs/${encodeURIComponent(scenario.childJob.job_id)}/events`
    ) {
      const afterSequence = Number(url.searchParams.get("after_sequence") ?? 0);
      return json(
        route,
        scenario.childJob.events.filter((event) => event.sequence > afterSequence),
      );
    }
    if (method === "GET" && path === "/api/memory/status") {
      return json(route, FIXTURE_MEMORY_STATUS);
    }
    if (method === "GET" && path === "/api/memory/collections") {
      return json(route, FIXTURE_MEMORY_COLLECTIONS);
    }
    if (method === "GET" && path === "/api/memory/records") {
      return json(route, filteredMemoryRecords(url));
    }
    if (method === "GET" && scenario.childRunScenario) {
      const childRunPath = `/api/runs/${encodeURIComponent(scenario.childRunScenario.run.run_id)}`;
      if (path === childRunPath) {
        return json(route, scenario.childRunScenario.snapshot);
      }
      if (path === `${childRunPath}/artifacts`) {
        return json(route, []);
      }
      if (path === `${childRunPath}/events`) {
        return json(route, scenario.childRunScenario.events);
      }
      if (
        path === `${childRunPath}/report` ||
        path === `${childRunPath}/audit-report` ||
        path === `${childRunPath}/report-debate`
      ) {
        return text(route, "");
      }
      if (path === `${childRunPath}/visualization`) {
        return json(route, null);
      }
    }
    if (method === "GET" && path === "/api/monitoring/sources") {
      return json(route, [scenario.source]);
    }
    if (method === "POST" && path === "/api/monitoring/sessions") {
      const payload = request.postDataJSON() as MonitoringSessionCreateRequest;
      sessionRequests.push(payload);
      currentSession = structuredClone(scenario.initialSession);
      nextStepIndex = 0;
      return json(route, currentSession, 201);
    }

    const sessionPath = `/api/monitoring/sessions/${encodeURIComponent(currentSession.config.session_id)}`;
    if (method === "GET" && path === sessionPath) {
      sessionGetRequests += 1;
      return json(route, currentSession);
    }
    if (method === "GET" && path === `${sessionPath}/ticks`) {
      const afterSequence = Number(url.searchParams.get("after_sequence") ?? 0);
      tickListAfterSequences.push(afterSequence);
      const publishedCursor = latestCampaign?.execution_cursor
        ?? currentSession.state.execution_cursor
        ?? -1;
      const tickCandidates = [
        ...currentSession.ticks,
        ...scenario.steps.flatMap((step) => step.tick ? [step.tick] : []),
      ];
      const uniqueTicks = [...new Map(
        tickCandidates.map((tick) => [tick.tick_id, tick]),
      ).values()];
      const ticks = uniqueTicks.filter(
        (tick) => tick.cursor <= publishedCursor && tick.sequence > afterSequence,
      );
      const tickIds = new Set(ticks.map((tick) => tick.tick_id));
      const triggerCandidates = [
        ...currentSession.triggers,
        ...scenario.steps.flatMap((step) => step.triggers),
      ];
      return json(route, {
        after_sequence: afterSequence,
        session_id: currentSession.config.session_id,
        ticks,
        triggers: triggerCandidates.filter(
          (trigger) => trigger.origin_tick_id !== null && tickIds.has(trigger.origin_tick_id),
        ),
      });
    }
    if (method === "GET" && path === `${sessionPath}/child-runs`) {
      return json(route, {
        child_revision: currentSession.child_revision,
        child_runs: currentSession.child_runs,
        session_id: currentSession.config.session_id,
      });
    }
    if (
      method === "POST" &&
      scenario.dispatch &&
      path === `${sessionPath}/triggers/${encodeURIComponent(scenario.dispatch.triggerId)}/dispatch`
    ) {
      const payload = request.postDataJSON() as MonitoringReviewDispatchRequest;
      dispatchRequests.push(payload);
      if (payload.expected_child_revision !== currentSession.child_revision) {
        return json(route, { detail: "Revisión hija CAS inesperada en la fixture." }, 409);
      }
      await dispatchGate;
      const response = structuredClone(scenario.dispatch.response);
      response.receipt.command_id = payload.command_id;
      response.receipt.expected_child_revision = payload.expected_child_revision;
      currentSession = response.session;
      return json(route, response, 202);
    }
    if (method === "POST" && path === `${sessionPath}/step`) {
      const payload = request.postDataJSON() as MonitoringStepRequest;
      stepRequests.push(payload);
      const template = scenario.steps[nextStepIndex];
      if (!template) {
        return json(route, { detail: "La fixture no contiene más pasos." }, 409);
      }
      if (payload.expected_revision !== currentSession.state.revision) {
        return json(route, { detail: "Revisión CAS inesperada en la fixture." }, 409);
      }
      const response: MonitoringStepResponse = structuredClone(template);
      response.receipt.command_id = payload.command_id;
      response.receipt.expected_revision = payload.expected_revision;
      response.state.last_command_id = payload.command_id;
      currentSession = {
        ...currentSession,
        state: response.state,
        ticks: response.tick
          ? [...currentSession.ticks, response.tick]
          : currentSession.ticks,
        triggers: [...currentSession.triggers, ...response.triggers],
      };
      nextStepIndex += 1;
      return json(route, response);
    }

    return unhandled(route, unhandledApiRequests, method, url);
  };

  await page.route("**/api/**", handler);

  return {
    assertNoUnhandledApiRequests() {
      if (unhandledApiRequests.length > 0) {
        throw new Error(
          `Llamadas API E2E no manejadas:\n${unhandledApiRequests.join("\n")}`,
        );
      }
    },
    dispatchRequests,
    get campaignRequests() {
      return campaignRequests;
    },
    get sessionGetRequests() {
      return sessionGetRequests;
    },
    releaseDispatchResponse() {
      releaseDispatchGate();
    },
    async dispose() {
      await page.unroute("**/api/**", handler);
    },
    sessionRequests,
    stepRequests,
    tickListAfterSequences,
    unhandledApiRequests,
  };
}

function filteredMemoryRecords(url: URL): MemoryRecordSummary[] {
  const targetAgent = url.searchParams.get("target_agent");
  const dataset = url.searchParams.get("dataset");
  const memoryRole = url.searchParams.get("memory_role");
  const reusableOnly = url.searchParams.get("reusable_only");
  const searchText = url.searchParams.get("search_text")?.trim().toLocaleLowerCase() ?? "";

  return FIXTURE_MEMORY_RECORDS.filter((record) => {
    if (targetAgent && record.target_agent !== targetAgent) return false;
    if (dataset && record.dataset !== dataset) return false;
    if (memoryRole && record.memory_role !== memoryRole) return false;
    if (reusableOnly === "true" && !record.reusable_as_context) return false;
    if (!searchText) return true;
    return [record.memory_record_id, record.summary, ...record.tags]
      .join(" ")
      .toLocaleLowerCase()
      .includes(searchText);
  });
}

function memoryRecord(
  memoryRecordId: string,
  memoryRole: MemoryRecordSummary["memory_role"],
  summary: string,
): MemoryRecordSummary {
  return {
    collection_name: "modeler_memory",
    created_at: "2026-08-09T12:00:00.000Z",
    data_provenance: "official",
    dataset: "nasa_ims_bearing",
    decision_id: `historical-${memoryRecordId}:modeler:001`,
    exclude_from_context: false,
    human_verdict: "correct",
    memory_record_id: memoryRecordId,
    memory_role: memoryRole,
    outcome: "validated",
    reusable_as_context: true,
    run_id: `historical-${memoryRecordId}`,
    source_agent_name: "modeler",
    source_path: null,
    source_type: "decision_episode",
    summary,
    tags: ["e2e", "controlled-fixture", "nasa-ims"],
    target_agent: "modeler",
  };
}

function detailedMemoryRecord(record: MemoryRecordSummary): ReasoningMemoryRecord {
  return {
    ...record,
    content:
      `${record.summary} Este contenido existe para comprobar la divulgacion progresiva; `
      + "no acredita influencia sobre ninguna run por si solo.",
    embedding_dimension: 768,
    embedding_model: "nomic-embed-text:fixture",
    embedding_version: "fixture-v1",
    metrics: {},
    postmortem_id: null,
    source_hash: `hash-${record.memory_record_id}`,
    vector_id: `vector-${record.memory_record_id}`,
  };
}

async function json(route: Route, value: unknown, status = 200): Promise<void> {
  await route.fulfill({
    body: JSON.stringify(value),
    contentType: "application/json; charset=utf-8",
    headers: { "Cache-Control": "no-store" },
    status,
  });
}

async function notFound(route: Route, detail: string): Promise<void> {
  await json(route, { detail }, 404);
}

async function text(route: Route, value: string): Promise<void> {
  await route.fulfill({
    body: value,
    contentType: "text/plain; charset=utf-8",
    headers: { "Cache-Control": "no-store" },
    status: 200,
  });
}

async function unhandled(
  route: Route,
  unhandledApiRequests: string[],
  method: string,
  url: URL,
): Promise<void> {
  const requestLabel = `${method} ${url.pathname}${url.search}`;
  unhandledApiRequests.push(requestLabel);
  await json(route, { detail: `API mock no configurada: ${requestLabel}` }, 501);
}
