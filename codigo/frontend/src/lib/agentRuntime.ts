import { STAGE_LABELS } from "../constants/pipeline";
import { confidenceText } from "./formatters";
import type { AgentRuntimeEvent, PipelineRunStage } from "../types";

export const AGENT_PROFILES = [
  {
    id: "supervisor",
    label: "Supervisor",
    role: "Jefe",
    node: "supervisor",
  },
  {
    id: "cleaner",
    label: "Limpiador",
    role: "Calidad",
    node: "cleaner_agent",
  },
  {
    id: "structurer",
    label: "Estructurador",
    role: "Datos",
    node: "structuring_agent",
  },
  {
    id: "modeler",
    label: "Modelador",
    role: "Modelos",
    node: "modeling_agent",
  },
  {
    id: "evaluator",
    label: "Evaluador",
    role: "Metricas",
    node: "evaluation_agent",
  },
  {
    id: "report_writer",
    label: "Redactor",
    role: "Informe",
    node: "report_writer",
  },
  {
    id: "report_verifier",
    label: "Verificador",
    role: "Auditoria",
    node: "report_verifier",
  },
] as const;

export interface AgentConversationMessage {
  id: string;
  sequence: number;
  agentId: string;
  agentLabel: string;
  role: string;
  title: string;
  text: string;
  createdAt: string;
  stage: string | null;
  status: "normal" | "success" | "warning" | "error";
  badges: string[];
}

export function eventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
): AgentRuntimeEvent[] {
  return events.filter((event) => eventOwnerId(event) === agentId);
}

export function agentConversationMessages(
  events: AgentRuntimeEvent[],
): AgentConversationMessage[] {
  return events
    .filter(isConversationEvent)
    .map((event) => {
      const agentId = eventOwnerId(event);
      const status = conversationStatus(event);
      return {
        id: event.event_id,
        sequence: event.sequence,
        agentId,
        agentLabel: agentLabel(agentId),
        role: conversationRole(agentId),
        title: event.title,
        text: conversationText(event),
        createdAt: event.created_at,
        stage: event.stage,
        status,
        badges: conversationBadges(event),
      };
    });
}

function isConversationEvent(event: AgentRuntimeEvent): boolean {
  if (!["supervisor_decision", "agent_decision", "error"].includes(event.kind)) {
    return false;
  }
  const owner = eventOwnerId(event);
  return AGENT_PROFILES.some((agent) => agent.id === owner);
}

export function eventOwnerId(event: AgentRuntimeEvent): string {
  if (event.agent_name) {
    return event.agent_name;
  }
  if (event.source === "supervisor") {
    return "supervisor";
  }
  if (event.node === "report_verifier") {
    return "report_verifier";
  }
  if (event.node?.includes("modeling")) {
    return "modeler";
  }
  if (event.node?.includes("structuring")) {
    return "structurer";
  }
  if (event.node?.includes("clean")) {
    return "cleaner";
  }
  if (event.node?.includes("evaluation") || event.node === "evaluator") {
    return "evaluator";
  }
  if (event.node?.includes("report")) {
    return "report_writer";
  }
  return "supervisor";
}

function conversationRole(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.role ?? "Agente";
}

function conversationStatus(event: AgentRuntimeEvent): AgentConversationMessage["status"] {
  if (event.kind === "error") {
    return "error";
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus === "approved") {
    return "success";
  }
  if (verificationStatus === "needs_revision" || verificationStatus === "blocked") {
    return "warning";
  }
  const evaluation = recordFromPayload(event.payload, "evaluation");
  const approved = evaluation?.approved;
  if (approved === true) {
    return "success";
  }
  if (approved === false) {
    return "warning";
  }
  return "normal";
}

function conversationText(event: AgentRuntimeEvent): string {
  if (event.kind === "error") {
    return event.summary;
  }
  const agentId = eventOwnerId(event);
  if (agentId === "supervisor") {
    return supervisorConversationText(event);
  }
  if (agentId === "cleaner") {
    const config = recordFromPayload(event.payload, "cleaning_config");
    const strategy = stringValue(config?.strategy_id);
    return strategy
      ? `Propone la estrategia de limpieza ${strategy}.`
      : conciseEventSummary(event);
  }
  if (agentId === "structurer") {
    const config = recordFromPayload(event.payload, "structuring_config");
    const windowSize = stringValue(config?.window_size);
    const featureSet = stringValue(config?.feature_set) ?? stringValue(config?.feature_mode);
    const parts = [
      windowSize ? `ventanas de ${windowSize}` : null,
      featureSet ? `features ${featureSet}` : null,
    ].filter((item): item is string => item !== null);
    return parts.length > 0
      ? `Organiza la serie temporal con ${parts.join(" y ")}.`
      : conciseEventSummary(event);
  }
  if (agentId === "modeler") {
    const config = recordFromPayload(event.payload, "modeling_config");
    const modelName = stringValue(config?.model_name);
    const threshold = stringValue(config?.threshold_quantile);
    if (modelName && threshold) {
      return `Selecciona ${modelName} con umbral cuantilico ${threshold}.`;
    }
    return modelName ? `Selecciona ${modelName} para el modelado.` : conciseEventSummary(event);
  }
  if (agentId === "evaluator") {
    const evaluation = recordFromPayload(event.payload, "evaluation");
    const summary = stringValue(evaluation?.summary);
    const approved = evaluation?.approved;
    if (summary) {
      return approved === false ? `No aprueba la run: ${summary}` : summary;
    }
    return conciseEventSummary(event);
  }
  if (agentId === "report_writer") {
    const revisionRound = stringValue(event.payload.revision_round);
    const changes = stringArrayFromPayload(event.payload, "changes_summary");
    if (revisionRound) {
      return changes.length > 0
        ? `Revisa el informe en la ronda ${revisionRound}: ${joinShortList(changes)}.`
        : `Revisa el informe en la ronda ${revisionRound}.`;
    }
    return "Prepara el informe final con las secciones y evidencias seleccionadas.";
  }
  if (agentId === "report_verifier") {
    const status = stringFromPayload(event.payload, "verification_status");
    const summary = stringFromPayload(event.payload, "human_summary") ?? event.summary;
    const corrections = stringArrayFromPayload(event.payload, "required_corrections");
    const statusText = status ? `Veredicto: ${verificationStatusLabel(status)}.` : "";
    const correctionText =
      corrections.length > 0 ? ` Pide corregir: ${joinShortList(corrections)}.` : "";
    return `${statusText} ${summary}${correctionText}`.trim();
  }
  return conciseEventSummary(event);
}

function supervisorConversationText(event: AgentRuntimeEvent): string {
  const stopReason = stringFromNestedPayload(event.payload, "decision", "stop_reason");
  if (stopReason) {
    return `Cierra la ejecucion: ${stopReason}.`;
  }
  const next = event.next_node ?? event.next_stage;
  if (next) {
    return `Decide continuar hacia ${readableFlowLabel(next)}.`;
  }
  return conciseEventSummary(event);
}

function conversationBadges(event: AgentRuntimeEvent): string[] {
  const badges: string[] = [];
  if (event.stage) {
    badges.push(STAGE_LABELS[event.stage as PipelineRunStage] ?? readableFlowLabel(event.stage));
  }
  if (event.confidence !== null) {
    badges.push(confidenceText(event.confidence));
  }
  if (event.memory_record_ids.length > 0) {
    badges.push(`${event.memory_record_ids.length} memoria`);
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus) {
    badges.push(verificationStatusLabel(verificationStatus));
  }
  const next = event.next_node ?? event.next_stage;
  if (eventOwnerId(event) === "supervisor" && next) {
    badges.push(`sigue: ${readableFlowLabel(next)}`);
  }
  return badges.slice(0, 4);
}

function conciseEventSummary(event: AgentRuntimeEvent): string {
  return event.summary.length > 220 ? `${event.summary.slice(0, 217)}...` : event.summary;
}

export function readableFlowLabel(value: string): string {
  const labels: Record<string, string> = {
    manifest_executor: "manifest",
    profiler_executor: "perfilado",
    cleaner_agent: "limpiador",
    cleaning_executor: "ejecutor de limpieza",
    structuring_agent: "estructurador",
    structuring_executor: "ejecutor de estructuracion",
    modeling_agent: "modelador",
    modeling_executor: "ejecutor de modelado",
    evaluation_executor: "ejecutor de evaluacion",
    evaluation_agent: "evaluador",
    report_writer: "redactor",
    report_verifier: "verificador",
  };
  return labels[value] ?? value.replace(/_/g, " ");
}

function verificationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    approved: "aprobado",
    needs_revision: "requiere revision",
    blocked: "bloqueado",
  };
  return labels[status] ?? status;
}

export function agentInitials(label: string): string {
  return label
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function recordFromPayload(
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = payload[key];
  return isRecord(value) ? value : null;
}

export function stringFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return stringValue(payload[key]);
}

function stringFromNestedPayload(
  payload: Record<string, unknown>,
  key: string,
  nestedKey: string,
): string | null {
  return stringValue(recordFromPayload(payload, key)?.[nestedKey]);
}

export function stringArrayFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string[] {
  const value = payload[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => stringValue(item))
    .filter((item): item is string => item !== null);
}

export function stringValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

export function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function joinShortList(values: string[]): string {
  const visible = values.slice(0, 2);
  const suffix = values.length > visible.length ? ` y ${values.length - visible.length} mas` : "";
  return `${visible.join("; ")}${suffix}`;
}

export function agentLabel(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.label ?? agentId;
}

export function kindLabel(kind: AgentRuntimeEvent["kind"]): string {
  const labels: Record<AgentRuntimeEvent["kind"], string> = {
    job_status: "Job",
    supervisor_decision: "Supervisor",
    agent_decision: "Decision",
    memory_retrieval: "Memoria",
    executor_result: "Ejecutor",
    error: "Error",
  };
  return labels[kind];
}

export function agentEventPlainText(event: AgentRuntimeEvent): string {
  const actor = event.agent_name ? agentLabel(event.agent_name) : sourceLabel(event);
  const stage = event.stage ? ` durante ${STAGE_LABELS[event.stage as PipelineRunStage] ?? event.stage}` : "";
  const confidence =
    event.confidence === null ? "" : ` con confianza ${confidenceText(event.confidence)}`;
  const next = event.next_node ?? event.next_stage;
  const nextText = next ? ` y propone continuar hacia ${next}` : "";
  const memoryText =
    event.memory_record_ids.length > 0
      ? ` usando ${event.memory_record_ids.length} recuerdo(s) como contexto`
      : "";
  const payloadText = payloadPlainText(event.payload);

  if (event.kind === "memory_retrieval") {
    return `${actor} recupera memoria${stage}${memoryText}. ${payloadText}`;
  }
  if (event.kind === "executor_result") {
    return `${actor} registra el resultado del ejecutor${stage}. ${payloadText}`;
  }
  if (event.kind === "supervisor_decision" || event.kind === "agent_decision") {
    return `${actor} toma una decision${stage}${confidence}${nextText}${memoryText}. ${payloadText}`;
  }
  if (event.kind === "error") {
    return `${actor} informa de un error${stage}. ${event.summary}`;
  }
  return `${actor} actualiza el estado del job. ${event.summary}`;
}

function payloadPlainText(payload: Record<string, unknown>): string {
  const candidates = [
    ["model_name", "modelo"],
    ["strategy_id", "estrategia"],
    ["decision_id", "decision"],
    ["status", "estado"],
    ["verification_status", "verificacion"],
    ["debate_round", "ronda"],
    ["human_summary", "resumen"],
    ["message", "mensaje"],
    ["n_records", "recuerdos"],
    ["n_artifacts", "artefactos"],
    ["n_unsupported_claims", "claims sin soporte"],
    ["n_misleading_claims", "claims confusos"],
    ["n_missing_limitations", "limitaciones ausentes"],
    ["threshold", "umbral"],
  ];
  const fragments = candidates
    .map(([key, label]) =>
      payload[key] === undefined ? null : `${label}: ${String(payload[key])}`,
    )
    .filter((item): item is string => item !== null);
  for (const key of ["required_corrections", "changes_summary"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "required_corrections" ? "correcciones" : "cambios"}: ${value.length}`);
    }
  }
  for (const key of ["accepted_issue_ids", "rejected_issue_ids"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "accepted_issue_ids" ? "incidencias aceptadas" : "incidencias rechazadas"}: ${value.length}`);
    }
  }
  return fragments.length > 0
    ? `Campos clave: ${fragments.join(", ")}.`
    : "El JSON adjunto contiene el detalle tecnico completo.";
}

export function sourceLabel(event: AgentRuntimeEvent): string {
  if (event.agent_name) {
    return agentLabel(event.agent_name);
  }
  return kindLabel(event.kind);
}
