import type { AgentRuntimeEvent } from "../types";
import {
  AGENT_PROFILES,
  agentDecisionEventsForAgent,
  agentDecisionEvidenceModel,
  agentLabel,
  eventEmittingAgentId,
  eventsForAgent,
} from "./agentRuntime";
import type { AgentHypothesisViewModel } from "./agentRuntime";

export type AgentOfficeNodeState =
  | "idle"
  | "active"
  | "decision"
  | "memory"
  | "error";

export interface AgentOfficeNode {
  cssColor: string;
  debateCount: number;
  decisionCount: number;
  errorCount: number;
  eventCount: number;
  hypothesisCount: number;
  id: string;
  label: string;
  latestKind: AgentRuntimeEvent["kind"] | null;
  latestStage: string | null;
  latestSummary: string | null;
  latestEvent: AgentRuntimeEvent | null;
  memoryCount: number;
  primaryHypothesis: AgentHypothesisViewModel | null;
  proposalHypothesisCount: number;
  role: string;
  selected: boolean;
  signalBadges: AgentOfficeSignalBadge[];
  state: AgentOfficeNodeState;
  stateLabel: string;
  threeColor: number;
  toolCount: number;
  x: number;
  z: number;
}

export interface AgentOfficeSignalBadge {
  label: string;
  tone: "neutral" | "ok" | "warning" | "danger";
}

export interface AgentOfficeConnection {
  color: number;
  fromAgentId: string;
  intensity: number;
  kind: "supervisor" | "transition";
  sequence: number | null;
  toAgentId: string;
}

export interface AgentOfficeModel {
  activeAgentId: string | null;
  activeAgents: number;
  connections: AgentOfficeConnection[];
  eventCount: number;
  hasRuntimeEvents: boolean;
  latestEvent: AgentRuntimeEvent | null;
  nodes: AgentOfficeNode[];
  selectedNode: AgentOfficeNode | null;
}

const AGENT_POSITIONS: Record<string, { x: number; z: number }> = {
  supervisor: { x: 0, z: -1.45 },
  cleaner: { x: -2.35, z: -0.45 },
  structurer: { x: -1.2, z: 0.72 },
  modeler: { x: 0, z: 0.02 },
  evaluator: { x: 1.2, z: 0.72 },
  report_writer: { x: 2.35, z: -0.45 },
  report_verifier: { x: 0, z: 1.72 },
};

const STATE_STYLE: Record<
  AgentOfficeNodeState,
  { cssColor: string; stateLabel: string; threeColor: number }
> = {
  active: {
    cssColor: "#0f766e",
    stateLabel: "activo",
    threeColor: 0x0f766e,
  },
  decision: {
    cssColor: "#d97706",
    stateLabel: "decision",
    threeColor: 0xd97706,
  },
  error: {
    cssColor: "#dc2626",
    stateLabel: "error",
    threeColor: 0xdc2626,
  },
  idle: {
    cssColor: "#64748b",
    stateLabel: "reposo",
    threeColor: 0x64748b,
  },
  memory: {
    cssColor: "#2563eb",
    stateLabel: "actividad RAG",
    threeColor: 0x2563eb,
  },
};

export function buildAgentOfficeModel(
  events: AgentRuntimeEvent[],
  selectedAgentId: string,
): AgentOfficeModel {
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const activeAgentId = latestEvent ? eventEmittingAgentId(latestEvent) : null;

  const nodes = AGENT_PROFILES.map((agent) => {
    const relatedEvents = eventsForAgent(events, agent.id);
    const agentEvents = agentDecisionEventsForAgent(events, agent.id);
    const latestAgentEvent =
      agentEvents.length > 0 ? agentEvents[agentEvents.length - 1] : null;
    const latestRelatedEvent =
      relatedEvents.length > 0 ? relatedEvents[relatedEvents.length - 1] : null;
    const decisionCount = agentEvents.length;
    const decisionModels = agentEvents
      .filter(
        (event) => event.kind === "agent_decision" || event.kind === "supervisor_decision",
      )
      .map(agentDecisionEvidenceModel);
    const completeEffectiveHypotheses = decisionModels
      .map((item) => item.primaryHypothesis)
      .filter(
        (item): item is AgentHypothesisViewModel =>
          item !== null && item.contractComplete,
      );
    const proposalHypothesisCount = decisionModels.reduce(
      (total, item) => total + Math.max(0, item.hypotheses.length - 1),
      0,
    );
    const primaryHypothesis = decisionModels.length > 0
      ? decisionModels[decisionModels.length - 1].primaryHypothesis
      : null;
    const memoryCount = relatedEvents.filter(
      (event) => event.kind === "memory_retrieval",
    ).length;
    const errorCount = relatedEvents.filter(
      (event) => event.kind === "error" && event.agent_name === agent.id,
    ).length;
    const toolCount = relatedEvents.reduce(
      (total, event) => total + countToolSignals(event),
      0,
    );
    const debateCount = agentEvents.filter(hasDebateSignal).length;
    const state = agentNodeState({
      activeAgentId,
      agentId: agent.id,
      latestAgentEvent,
      latestRelatedEvent,
      decisionCount,
    });
    const style = STATE_STYLE[state];
    const position = AGENT_POSITIONS[agent.id] ?? { x: 0, z: 0 };

    return {
      cssColor: style.cssColor,
      debateCount,
      decisionCount,
      errorCount,
      eventCount: decisionCount,
      hypothesisCount: completeEffectiveHypotheses.length,
      id: agent.id,
      label: agentLabel(agent.id),
      latestKind: latestAgentEvent?.kind ?? null,
      latestStage: latestAgentEvent?.stage ?? null,
      latestSummary: latestAgentEvent?.summary ?? null,
      latestEvent: latestAgentEvent,
      memoryCount,
      primaryHypothesis,
      proposalHypothesisCount,
      role: agent.role,
      selected: selectedAgentId === agent.id,
      signalBadges: signalBadges({
        debateCount,
        decisionCount,
        errorCount,
        eventCount: decisionCount,
        hypothesisCount: completeEffectiveHypotheses.length,
        memoryCount,
        state,
        toolCount,
      }),
      state,
      stateLabel: style.stateLabel,
      threeColor: style.threeColor,
      toolCount,
      x: position.x,
      z: position.z,
    };
  });

  return {
    activeAgentId,
    activeAgents: nodes.filter((node) => node.decisionCount > 0).length,
    connections: buildAgentConnections(events, nodes),
    eventCount: events.length,
    hasRuntimeEvents: events.length > 0,
    latestEvent,
    nodes,
    selectedNode: nodes.find((node) => node.id === selectedAgentId) ?? null,
  };
}

function agentNodeState({
  activeAgentId,
  agentId,
  decisionCount,
  latestAgentEvent,
  latestRelatedEvent,
}: {
  activeAgentId: string | null;
  agentId: string;
  decisionCount: number;
  latestAgentEvent: AgentRuntimeEvent | null;
  latestRelatedEvent: AgentRuntimeEvent | null;
}): AgentOfficeNodeState {
  if (latestAgentEvent?.kind === "error") {
    return "error";
  }
  if (activeAgentId === agentId) {
    return "active";
  }
  if (
    latestRelatedEvent?.kind === "memory_retrieval"
    && (latestAgentEvent === null || latestRelatedEvent.sequence > latestAgentEvent.sequence)
  ) {
    return "memory";
  }
  if (decisionCount > 0) {
    return "decision";
  }
  return "idle";
}

function buildAgentConnections(
  events: AgentRuntimeEvent[],
  nodes: AgentOfficeNode[],
): AgentOfficeConnection[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  return events
    .filter((event) => event.kind === "supervisor_decision" && event.next_node)
    .flatMap((event) => {
      const targetId = agentIdForPipelineNode(event.next_node!);
      const target = targetId ? nodeById.get(targetId) : null;
      if (!target || targetId === "supervisor") return [];
      const resolvedTargetId = target.id;
      return [{
        color: target.threeColor,
        fromAgentId: "supervisor",
        intensity: 0.72,
        kind: "supervisor" as const,
        sequence: event.sequence,
        toAgentId: resolvedTargetId,
      }];
    })
    .slice(-14);
}

function agentIdForPipelineNode(node: string): string | null {
  const agentNodes: Record<string, string> = {
    cleaner: "cleaner",
    cleaner_agent: "cleaner",
    structurer: "structurer",
    structuring_agent: "structurer",
    modeler: "modeler",
    modeling_agent: "modeler",
    evaluator: "evaluator",
    evaluation_agent: "evaluator",
    report_writer: "report_writer",
    report_verifier: "report_verifier",
  };
  return agentNodes[node.trim().toLowerCase()] ?? null;
}

function countToolSignals(event: AgentRuntimeEvent): number {
  return event.payload.tool_observation !== undefined
    || event.payload.observation_id !== undefined
    ? 1
    : 0;
}

function hasDebateSignal(event: AgentRuntimeEvent): boolean {
  return (
    eventEmittingAgentId(event) === "report_verifier" ||
    payloadStringArray(event.payload, "required_corrections").length > 0 ||
    payloadStringArray(event.payload, "changes_summary").length > 0 ||
    payloadStringArray(event.payload, "accepted_issue_ids").length > 0 ||
    payloadStringArray(event.payload, "rejected_issue_ids").length > 0 ||
    Boolean(stringFromUnknown(event.payload.verification_status))
  );
}

function signalBadges({
  debateCount,
  decisionCount,
  errorCount,
  eventCount,
  hypothesisCount,
  memoryCount,
  state,
  toolCount,
}: {
  debateCount: number;
  decisionCount: number;
  errorCount: number;
  eventCount: number;
  hypothesisCount: number;
  memoryCount: number;
  state: AgentOfficeNodeState;
  toolCount: number;
}): AgentOfficeSignalBadge[] {
  const badges: AgentOfficeSignalBadge[] = [];
  if (eventCount === 0) {
    badges.push({ label: "sin decisiones", tone: "neutral" });
    return badges;
  }
  badges.push({ label: state === "active" ? "activo" : `${eventCount} decisiones`, tone: "ok" });
  if (decisionCount > 0) {
    badges.push({ label: `${decisionCount} decisiones`, tone: "warning" });
  }
  if (hypothesisCount > 0) {
    badges.push({ label: `${hypothesisCount} hipotesis completas`, tone: "ok" });
  }
  if (memoryCount > 0) {
    badges.push({
      label: `${memoryCount} ${memoryCount === 1 ? "evento RAG" : "eventos RAG"}`,
      tone: "neutral",
    });
  }
  if (toolCount > 0) {
    badges.push({ label: `${toolCount} observaciones tool`, tone: "neutral" });
  }
  if (debateCount > 0) {
    badges.push({ label: `${debateCount} debate`, tone: "warning" });
  }
  if (errorCount > 0) {
    badges.push({ label: `${errorCount} errores`, tone: "danger" });
  }
  return badges.slice(0, 4);
}

function payloadStringArray(
  payload: Record<string, unknown>,
  key: string,
): string[] {
  const value = payload[key];
  if (Array.isArray(value)) {
    return value
      .map((item) => stringFromUnknown(item))
      .filter((item): item is string => item !== null);
  }
  const scalar = stringFromUnknown(value);
  return scalar ? [scalar] : [];
}

function stringFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value && typeof value === "object") {
    const candidate = value as { name?: unknown; tool_name?: unknown };
    for (const field of [candidate.name, candidate.tool_name]) {
      if (typeof field === "string" && field.trim().length > 0) {
        return field.trim();
      }
    }
  }
  return null;
}
