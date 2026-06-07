import type { AgentRuntimeEvent } from "../types";
import {
  AGENT_PROFILES,
  agentLabel,
  eventOwnerId,
  eventsForAgent,
} from "./agentRuntime";

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
  id: string;
  label: string;
  latestKind: AgentRuntimeEvent["kind"] | null;
  latestStage: string | null;
  latestSummary: string | null;
  latestEvent: AgentRuntimeEvent | null;
  memoryCount: number;
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
    stateLabel: "memoria",
    threeColor: 0x2563eb,
  },
};

export function buildAgentOfficeModel(
  events: AgentRuntimeEvent[],
  selectedAgentId: string,
): AgentOfficeModel {
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const activeAgentId = latestEvent ? eventOwnerId(latestEvent) : null;
  const maxEventCount = Math.max(
    1,
    ...AGENT_PROFILES.map((agent) => eventsForAgent(events, agent.id).length),
  );

  const nodes = AGENT_PROFILES.map((agent) => {
    const agentEvents = eventsForAgent(events, agent.id);
    const latestAgentEvent =
      agentEvents.length > 0 ? agentEvents[agentEvents.length - 1] : null;
    const decisionCount = agentEvents.filter(
      (event) =>
        event.kind === "agent_decision" || event.kind === "supervisor_decision",
    ).length;
    const memoryCount = agentEvents.filter(hasMemorySignal).length;
    const errorCount = agentEvents.filter((event) => event.kind === "error").length;
    const toolCount = agentEvents.reduce(
      (total, event) => total + countToolSignals(event),
      0,
    );
    const debateCount = agentEvents.filter(hasDebateSignal).length;
    const state = agentNodeState({
      activeAgentId,
      agentId: agent.id,
      errorCount,
      latestAgentEvent,
      memoryCount,
      decisionCount,
    });
    const style = STATE_STYLE[state];
    const position = AGENT_POSITIONS[agent.id] ?? { x: 0, z: 0 };

    return {
      cssColor: style.cssColor,
      debateCount,
      decisionCount,
      errorCount,
      eventCount: agentEvents.length,
      id: agent.id,
      label: agentLabel(agent.id),
      latestKind: latestAgentEvent?.kind ?? null,
      latestStage: latestAgentEvent?.stage ?? null,
      latestSummary: latestAgentEvent?.summary ?? null,
      latestEvent: latestAgentEvent,
      memoryCount,
      role: agent.role,
      selected: selectedAgentId === agent.id,
      signalBadges: signalBadges({
        debateCount,
        decisionCount,
        errorCount,
        eventCount: agentEvents.length,
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
    activeAgents: nodes.filter((node) => node.eventCount > 0).length,
    connections: buildAgentConnections(events, nodes, maxEventCount),
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
  errorCount,
  latestAgentEvent,
  memoryCount,
}: {
  activeAgentId: string | null;
  agentId: string;
  decisionCount: number;
  errorCount: number;
  latestAgentEvent: AgentRuntimeEvent | null;
  memoryCount: number;
}): AgentOfficeNodeState {
  if (latestAgentEvent?.kind === "error" || errorCount > 0) {
    return "error";
  }
  if (activeAgentId === agentId) {
    return "active";
  }
  if (latestAgentEvent?.kind === "memory_retrieval" || memoryCount > 0) {
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
  maxEventCount: number,
): AgentOfficeConnection[] {
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const transitions = events
    .slice(-36)
    .reduce<AgentOfficeConnection[]>((connections, event, index, recentEvents) => {
      if (index === 0) {
        return connections;
      }
      const previousAgentId = eventOwnerId(recentEvents[index - 1]);
      const nextAgentId = eventOwnerId(event);
      if (
        previousAgentId === nextAgentId ||
        !nodeById.has(previousAgentId) ||
        !nodeById.has(nextAgentId)
      ) {
        return connections;
      }
      const target = nodeById.get(nextAgentId)!;
      connections.push({
        color: target.threeColor,
        fromAgentId: previousAgentId,
        intensity: Math.min(1, 0.28 + connections.length * 0.035),
        kind: "transition",
        sequence: event.sequence,
        toAgentId: nextAgentId,
      });
      return connections;
    }, []);

  if (transitions.length > 0) {
    return transitions.slice(-14);
  }

  return nodes
    .filter((node) => node.id !== "supervisor" && (node.eventCount > 0 || node.selected))
    .map((node) => ({
      color: node.threeColor,
      fromAgentId: "supervisor",
      intensity: Math.max(0.22, Math.min(1, node.eventCount / maxEventCount)),
      kind: "supervisor" as const,
      sequence: null,
      toAgentId: node.id,
    }));
}

function hasMemorySignal(event: AgentRuntimeEvent): boolean {
  return (
    event.kind === "memory_retrieval" ||
    event.memory_record_ids.length > 0 ||
    payloadStringArray(event.payload, "retrieved_memory_record_ids").length > 0 ||
    payloadStringArray(event.payload, "cited_memory_record_ids").length > 0 ||
    payloadStringArray(event.payload, "ignored_memory_record_ids").length > 0
  );
}

function countToolSignals(event: AgentRuntimeEvent): number {
  return [
    "tool_names",
    "tool_calls",
    "tools_used",
    "used_tools",
  ].reduce((total, key) => total + payloadStringArray(event.payload, key).length, 0);
}

function hasDebateSignal(event: AgentRuntimeEvent): boolean {
  return (
    eventOwnerId(event) === "report_verifier" ||
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
  memoryCount,
  state,
  toolCount,
}: {
  debateCount: number;
  decisionCount: number;
  errorCount: number;
  eventCount: number;
  memoryCount: number;
  state: AgentOfficeNodeState;
  toolCount: number;
}): AgentOfficeSignalBadge[] {
  const badges: AgentOfficeSignalBadge[] = [];
  if (eventCount === 0) {
    badges.push({ label: "sin eventos", tone: "neutral" });
    return badges;
  }
  badges.push({ label: state === "active" ? "activo" : `${eventCount} eventos`, tone: "ok" });
  if (decisionCount > 0) {
    badges.push({ label: `${decisionCount} decisiones`, tone: "warning" });
  }
  if (memoryCount > 0) {
    badges.push({ label: `${memoryCount} memoria`, tone: "ok" });
  }
  if (toolCount > 0) {
    badges.push({ label: `${toolCount} tools`, tone: "neutral" });
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
