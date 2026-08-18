import type {
  AgentRuntimeEvent,
  ApiRunJobStatus,
  RunSnapshot,
} from "../types";
import {
  AGENT_PROFILES,
  agentDecisionEvidenceModel,
  agentDecisionPayload,
  eventEmittingAgentId,
  eventRelatedAgentId,
  isRecord,
  stringArrayFromPayload,
  stringValue,
} from "./agentRuntime";

export type StoryAgenticState =
  | "llm_first_pass"
  | "llm_repaired"
  | "llm_protocol_restricted"
  | "llm_with_overlay"
  | "fallback"
  | "non_agentic"
  | "unknown";

export type StoryMemoryState =
  | "not_observed"
  | "unavailable"
  | "requested"
  | "returned"
  | "returned_empty"
  | "used"
  | "rejected_by_agent"
  | "inconsistent";

export type StoryOutcomeState =
  | "success"
  | "failed"
  | "approved"
  | "not_approved"
  | "needs_revision"
  | "blocked"
  | "routed"
  | "closed"
  | "pending"
  | "unknown";

export interface StoryMemorySummary {
  contextCount: number;
  filteredCount: number;
  filteredIds: string[];
  ignoredCount: number;
  ignoredIds: string[];
  retrievedCount: number;
  retrievedIds: string[];
  state: StoryMemoryState;
  unavailableCount: number;
  usageSummary: string | null;
  usedCount: number;
  usedIds: string[];
}

export interface StoryOutcome {
  eventId: string | null;
  label: string;
  linked: boolean;
  state: StoryOutcomeState;
}

export interface AgentStoryAgent {
  agenticState: StoryAgenticState;
  decisionCount: number;
  decisionId: string | null;
  decisionLabel: string;
  id: string;
  label: string;
  latestDecisionEvent: AgentRuntimeEvent | null;
  memory: StoryMemorySummary;
  outcome: StoryOutcome;
  primaryHypothesis: ReturnType<typeof agentDecisionEvidenceModel>["primaryHypothesis"];
  role: string;
}

export interface AgentStoryStep {
  agentId: string | null;
  event: AgentRuntimeEvent;
  id: string;
  kind: AgentRuntimeEvent["kind"];
  label: string;
  sequence: number;
  stage: string | null;
}

export interface AgentStoryRunSummary {
  approved: boolean | null;
  decisionCount: number;
  errorCount: number;
  fallbackCount: number;
  firstPassCount: number;
  jobStatus: ApiRunJobStatus["status"] | "unknown";
  memory: StoryMemorySummary;
  overlayCount: number;
  participatingAgentCount: number;
  repairedCount: number;
  runId: string | null;
  stage: string | null;
  traceOrigin: "live" | "persisted" | "reconstructed" | "empty";
}

export interface AgentStoryModel {
  agents: AgentStoryAgent[];
  run: AgentStoryRunSummary;
  steps: AgentStoryStep[];
}

const EXECUTOR_AGENTS = new Set(["cleaner", "structurer", "modeler", "report_writer"]);

export function buildAgentStoryModel(
  events: AgentRuntimeEvent[],
  job: ApiRunJobStatus | null,
  snapshot: RunSnapshot | null,
): AgentStoryModel {
  const decisionEvents = events.filter(isDecisionEvent);
  const agenticStates = decisionEvents.map((event) =>
    storyAgenticState(agentDecisionPayload(event)),
  );
  const agents = AGENT_PROFILES.map((profile) => {
    const decisions = decisionEvents.filter(
      (event) => eventEmittingAgentId(event) === profile.id,
    );
    const latestDecisionEvent = decisions.length > 0 ? decisions[decisions.length - 1] : null;
    const evidence = latestDecisionEvent
      ? agentDecisionEvidenceModel(latestDecisionEvent)
      : null;
    return {
      agenticState: latestDecisionEvent
        ? storyAgenticState(agentDecisionPayload(latestDecisionEvent))
        : "unknown",
      decisionCount: decisions.length,
      decisionId: latestDecisionEvent?.decision_id ?? null,
      decisionLabel: latestDecisionEvent
        ? storyDecisionLabel(profile.id, agentDecisionPayload(latestDecisionEvent))
        : "Sin decision en esta run",
      id: profile.id,
      label: profile.label,
      latestDecisionEvent,
      memory: buildStoryMemorySummary(
        memoryEventsForAgent(events, profile.id, latestDecisionEvent),
      ),
      outcome: latestDecisionEvent
        ? storyOutcome(latestDecisionEvent, events)
        : pendingOutcome("Sin participacion registrada"),
      primaryHypothesis: evidence?.primaryHypothesis ?? null,
      role: profile.role,
    } satisfies AgentStoryAgent;
  });

  return {
    agents,
    run: {
      approved: snapshot?.approved ?? job?.snapshot?.approved ?? null,
      decisionCount: decisionEvents.length,
      errorCount: events.filter((event) => event.kind === "error").length,
      fallbackCount: agenticStates.filter((state) => state === "fallback").length,
      firstPassCount: agenticStates.filter((state) => state === "llm_first_pass").length,
      jobStatus: job?.status ?? statusFromEvents(events),
      memory: buildStoryMemorySummary(
        events.filter((event) => event.kind === "memory_retrieval"),
      ),
      overlayCount: agenticStates.filter((state) => state === "llm_with_overlay").length,
      participatingAgentCount: agents.filter((agent) => agent.decisionCount > 0).length,
      repairedCount: agenticStates.filter((state) => state === "llm_repaired").length,
      runId: snapshot?.run_id ?? job?.run_id ?? events[0]?.run_id ?? null,
      stage: snapshot?.current_stage
        ?? job?.snapshot?.current_stage
        ?? (events.length > 0 ? events[events.length - 1].stage : null),
      traceOrigin: storyTraceOrigin(events),
    },
    steps: events
      .filter((event) =>
        event.kind !== "job_status"
        || event.sequence === 1
        || event === events[events.length - 1],
      )
      .map((event) => ({
        agentId: eventRelatedAgentId(event),
        event,
        id: event.event_id,
        kind: event.kind,
        label: storyStepLabel(event),
        sequence: event.sequence,
        stage: event.stage,
      })),
  };
}

export function buildStoryMemorySummary(
  events: AgentRuntimeEvent[],
): StoryMemorySummary {
  const retrieved = new Set<string>();
  const used = new Set<string>();
  const ignored = new Set<string>();
  const filtered = new Set<string>();
  const contexts = new Set<string>();
  const retrievalStates = new Set<string>();
  let unavailableCount = 0;
  let usageSummary: string | null = null;

  for (const event of events) {
    const payload = isDecisionEvent(event) ? agentDecisionPayload(event) : event.payload;
    const queryId = stringValue(payload.query_id);
    const contextId = event.memory_context_id ?? stringValue(payload.memory_context_id);
    const retrievalCycleId = contextId ?? queryId;
    if (retrievalCycleId) contexts.add(retrievalCycleId);
    const retrievalEvent = stringValue(payload.retrieval_event);
    if (retrievalEvent) retrievalStates.add(retrievalEvent);
    if (retrievalEvent === "retrieval_unavailable") unavailableCount += 1;
    for (const id of eventRetrievedIds(event)) retrieved.add(id);
    for (const id of eventUsedIds(event)) used.add(id);
    for (const id of stringArrayFromPayload(payload, "ignored_memory_record_ids")) {
      ignored.add(id);
    }
    for (const id of eventFilteredIds(event)) filtered.add(id);
    usageSummary = stringValue(payload.memory_usage_summary) ?? usageSummary;
  }
  for (const id of used) ignored.delete(id);

  const inconsistentMemoryIds = [...used].some((id) => !retrieved.has(id))
    || [...filtered].some((id) => retrieved.has(id) || used.has(id));

  const state = storyMemoryState({
    contexts: contexts.size,
    ignored: ignored.size,
    inconsistentMemoryIds,
    retrievalStates,
    retrieved: retrieved.size,
    unavailableCount,
    used: used.size,
  });
  return {
    contextCount: contexts.size,
    filteredCount: filtered.size,
    filteredIds: [...filtered],
    ignoredCount: ignored.size,
    ignoredIds: [...ignored],
    retrievedCount: retrieved.size,
    retrievedIds: [...retrieved],
    state,
    unavailableCount,
    usageSummary,
    usedCount: used.size,
    usedIds: [...used],
  };
}

export function storyDecisionLabel(
  agentId: string,
  payload: Record<string, unknown>,
): string {
  if (agentId === "supervisor") {
    const next = stringValue(payload.next_node) ?? stringValue(payload.next_stage) ?? "cierre";
    return `${stringValue(payload.current_stage) ?? "fase"} → ${next.replace(/_/g, " ")}`;
  }
  if (agentId === "cleaner") {
    const config = recordValue(payload.cleaning_config);
    const strategy = stringValue(config?.strategy_id) ?? "politica de limpieza";
    const channel = stringValue(config?.selected_channel);
    return channel ? `${strategy} · ${channel}` : strategy;
  }
  if (agentId === "structurer") {
    const config = recordValue(payload.structuring_config);
    const windowSize = stringValue(config?.window_size);
    const overlap = stringValue(config?.overlap);
    return windowSize
      ? `Ventana ${windowSize}${overlap ? ` · solape ${overlap}` : ""}`
      : "Configuracion temporal";
  }
  if (agentId === "modeler") {
    const config = recordValue(payload.modeling_config) ?? recordValue(payload.retry_config);
    return stringValue(config?.model_name)
      ?? (payload.should_retry === false ? "Detener reintentos" : "Modelo no identificado");
  }
  if (agentId === "evaluator") {
    const evaluation = recordValue(payload.evaluation);
    if (evaluation?.approved === true) return "Aprueba operativamente";
    if (evaluation?.approved === false) return "No aprueba · revisar";
    return "Juicio sin veredicto";
  }
  if (agentId === "report_writer") {
    const round = stringValue(payload.revision_round);
    return round ? `Revisa informe · ronda ${round}` : "Redacta informe tecnico";
  }
  if (agentId === "report_verifier") {
    const status = stringValue(payload.verification_status);
    return status ? `Veredicto · ${status.replace(/_/g, " ")}` : "Verifica el informe";
  }
  return "Decision estructurada";
}

function memoryEventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
  decision: AgentRuntimeEvent | null,
): AgentRuntimeEvent[] {
  const related = events.filter(
    (event) => event.kind === "memory_retrieval" && eventRelatedAgentId(event) === agentId,
  );
  if (!decision) return related;
  const contextId = decision.memory_context_id
    ?? stringValue(agentDecisionPayload(decision).memory_context_id);
  const exact = related.filter((event) =>
    (decision.decision_id !== null && eventDecisionIds(event).includes(decision.decision_id))
    || (contextId !== null && event.memory_context_id === contextId),
  );
  return exact.length > 0 ? [...exact, decision] : [decision];
}

function eventRetrievedIds(event: AgentRuntimeEvent): string[] {
  const payload = isDecisionEvent(event) ? agentDecisionPayload(event) : event.payload;
  const explicit = stringArrayFromPayload(payload, "retrieved_memory_record_ids");
  if (explicit.length > 0) return explicit;
  if (stringValue(payload.retrieval_event) === "retrieval_returned") {
    return event.memory_record_ids;
  }
  const items = payload.items;
  return Array.isArray(items)
    ? items
        .filter(isRecord)
        .map((item) => stringValue(item.memory_record_id))
        .filter((id): id is string => id !== null)
    : [];
}

function eventUsedIds(event: AgentRuntimeEvent): string[] {
  const payload = isDecisionEvent(event) ? agentDecisionPayload(event) : event.payload;
  const explicit = stringArrayFromPayload(payload, "cited_memory_record_ids");
  if (explicit.length > 0) return explicit;
  if (payload.used_memory_context === true) {
    const declared = stringArrayFromPayload(payload, "memory_record_ids");
    return declared.length > 0 ? declared : event.memory_record_ids;
  }
  return stringValue(payload.retrieval_event) === "retrieval_used"
    ? event.memory_record_ids
    : [];
}

function eventFilteredIds(event: AgentRuntimeEvent): string[] {
  const payload = isDecisionEvent(event) ? agentDecisionPayload(event) : event.payload;
  const qualityGate = recordValue(payload.quality_gate);
  const excluded = qualityGate?.excluded;
  if (!Array.isArray(excluded)) return [];
  return excluded
    .filter(isRecord)
    .map((item) => stringValue(item.memory_record_id))
    .filter((id): id is string => id !== null);
}

function storyMemoryState({
  contexts,
  ignored,
  inconsistentMemoryIds,
  retrievalStates,
  retrieved,
  unavailableCount,
  used,
}: {
  contexts: number;
  ignored: number;
  inconsistentMemoryIds: boolean;
  retrievalStates: Set<string>;
  retrieved: number;
  unavailableCount: number;
  used: number;
}): StoryMemoryState {
  if (inconsistentMemoryIds) return "inconsistent";
  if (used > 0) return "used";
  if (retrievalStates.has("retrieval_used")) return used > 0 ? "used" : "inconsistent";
  if (ignored > 0 && retrieved > 0) return "rejected_by_agent";
  if (retrievalStates.has("retrieval_rejected_by_agent")) {
    return retrieved > 0 || ignored > 0 ? "rejected_by_agent" : "returned_empty";
  }
  if (retrievalStates.has("retrieval_returned")) return retrieved > 0 ? "returned" : "returned_empty";
  if (retrievalStates.has("retrieval_requested") || contexts > 0) return "requested";
  if (unavailableCount > 0) return "unavailable";
  return "not_observed";
}

function storyAgenticState(payload: Record<string, unknown>): StoryAgenticState {
  const protocol = recordValue(payload.protocol_trace);
  const proposal = recordValue(protocol?.agent_proposal);
  const traces = [recordValue(payload.generation_trace), recordValue(proposal?.generation_trace)]
    .filter((trace): trace is Record<string, unknown> => trace !== null);
  if (traces.some((trace) => stringValue(trace.origin) === "guardrail_fallback")) {
    return "fallback";
  }
  if (payload.policy_overlay_applied === true) return "llm_with_overlay";
  if (traces.some((trace) => stringValue(trace.validation_status) === "repaired")) {
    return "llm_repaired";
  }
  if (protocol || traces.some((trace) => stringValue(trace.origin) === "protocol_restricted")) {
    return "llm_protocol_restricted";
  }
  const primary = traces[0];
  if (
    primary
    && stringValue(primary.origin) === "llm"
    && stringValue(primary.validation_status) === "validated"
    && Number(primary.attempt_index) === 1
  ) {
    return "llm_first_pass";
  }
  if (primary && stringValue(primary.origin) !== "llm") return "non_agentic";
  return "unknown";
}

function storyOutcome(decision: AgentRuntimeEvent, events: AgentRuntimeEvent[]): StoryOutcome {
  const agentId = eventEmittingAgentId(decision);
  const payload = agentDecisionPayload(decision);
  if (agentId === "supervisor") {
    const next = decision.next_node ?? decision.next_stage ?? stringValue(payload.next_node) ?? stringValue(payload.next_stage);
    return {
      eventId: decision.event_id,
      label: next === "completed" || next === null ? "Flujo cerrado" : `Enruta a ${next.replace(/_/g, " ")}`,
      linked: true,
      state: next === "completed" || next === null ? "closed" : "routed",
    };
  }
  if (agentId === "evaluator") {
    const evaluation = recordValue(payload.evaluation);
    if (evaluation?.approved === true) return linkedOutcome(decision, "approved", "Aprobacion operativa");
    if (evaluation?.approved === false) return linkedOutcome(decision, "not_approved", "No aprobado");
    return pendingOutcome("Juicio sin veredicto");
  }
  if (agentId === "report_verifier") {
    const status = stringValue(payload.verification_status);
    if (status === "approved") return linkedOutcome(decision, "approved", "Informe aprobado");
    if (status === "needs_revision") return linkedOutcome(decision, "needs_revision", "Requiere revision");
    if (status === "blocked") return linkedOutcome(decision, "blocked", "Informe bloqueado");
    return pendingOutcome("Veredicto no registrado");
  }
  if (agentId === null || !decisionExpectsExecutor(agentId, payload)) {
    return linkedOutcome(decision, "success", "Decision registrada");
  }
  const result = events.find(
    (event) => event.kind === "executor_result"
      && event.sequence > decision.sequence
      && decision.decision_id !== null
      && eventDecisionIds(event).includes(decision.decision_id),
  );
  if (!result) return pendingOutcome("Sin resultado de ejecutor enlazado");
  const failed = stringValue(result.payload.status) === "failed"
    || (Array.isArray(result.payload.errors) && result.payload.errors.length > 0);
  return {
    eventId: result.event_id,
    label: result.summary,
    linked: true,
    state: failed ? "failed" : "success",
  };
}

function decisionExpectsExecutor(agentId: string, payload: Record<string, unknown>): boolean {
  if (!EXECUTOR_AGENTS.has(agentId)) return false;
  return !(agentId === "modeler"
    && stringValue(payload.decision_kind) === "modeling_retry"
    && payload.should_retry !== true);
}

function eventDecisionIds(event: AgentRuntimeEvent): string[] {
  return [
    event.decision_id,
    stringValue(event.payload.decision_id),
    stringValue(event.payload.source_decision_id),
    stringValue(event.payload.agent_decision_id),
  ].filter((id): id is string => id !== null);
}

function linkedOutcome(
  decision: AgentRuntimeEvent,
  state: StoryOutcomeState,
  label: string,
): StoryOutcome {
  return { eventId: decision.event_id, label, linked: true, state };
}

function pendingOutcome(label: string): StoryOutcome {
  return { eventId: null, label, linked: false, state: "pending" };
}

function storyStepLabel(event: AgentRuntimeEvent): string {
  const actor = eventRelatedAgentId(event);
  if (event.kind === "memory_retrieval") {
    const state = stringValue(event.payload.retrieval_event)?.replace("retrieval_", "") ?? "actividad";
    return `Memoria · ${state.replace(/_/g, " ")}`;
  }
  if (event.kind === "policy_proposal") return "Propuesta · consultiva, no aplicada";
  if (event.kind === "executor_result") return `Ejecutor · ${event.title.replace(/^Ejecutor\s*/i, "")}`;
  if (event.kind === "error") return `Error · ${actor ?? "sistema"}`;
  return actor ? `${AGENT_PROFILES.find((item) => item.id === actor)?.label ?? actor} · decision` : event.title;
}

function storyTraceOrigin(events: AgentRuntimeEvent[]): AgentStoryRunSummary["traceOrigin"] {
  if (events.length === 0) return "empty";
  const origins = events.map((event) => event.payload.trace_origin);
  if (origins.includes("reconstructed_from_decisions")) return "reconstructed";
  if (origins.includes("persisted_runtime")) return "persisted";
  return "live";
}

function statusFromEvents(events: AgentRuntimeEvent[]): ApiRunJobStatus["status"] | "unknown" {
  const status = stringValue(events.length > 0 ? events[events.length - 1].payload.status : null);
  return status === "queued" || status === "running" || status === "completed" || status === "failed"
    ? status
    : "unknown";
}

function isDecisionEvent(event: AgentRuntimeEvent): boolean {
  return event.kind === "agent_decision" || event.kind === "supervisor_decision";
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}
