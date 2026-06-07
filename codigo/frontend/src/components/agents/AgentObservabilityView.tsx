import {
  Activity,
  AlertTriangle,
  Box,
  Brain,
  Clock3,
  Database,
  FileJson,
  FileText,
  ListChecks,
  MessageSquare,
  Network,
  Quote,
  Route,
  Wrench,
} from "lucide-react";
import { lazy, Suspense, useState, type ReactNode } from "react";

import { StatusItem } from "../common/StatusItem";
import { StatusPill } from "../common/StatusPill";
import { AgentMemoryShowcase } from "./AgentMemoryShowcase";
import { AgentMemoryPanel } from "../memory/AgentMemoryPanel";
import {
  AGENT_PROFILES,
  agentConversationMessages,
  agentEventPlainText,
  agentInitials,
  agentLabel,
  eventsForAgent,
  eventOwnerId,
  kindLabel,
  sourceLabel,
} from "../../lib/agentRuntime";
import { confidenceText, formatEventTime } from "../../lib/formatters";
import type {
  AgentRuntimeEvent,
  ApiRunJobStatus,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  ReasoningMemoryRecord,
  RunSnapshot,
} from "../../types";
import type { AgentConversationMessage } from "../../lib/agentRuntime";

type AgentOfficeMode = "twoD" | "threeD";
type AgentWorkspaceMode = "runtime" | "memory";

const AgentOffice3D = lazy(() =>
  import("./AgentOffice3D").then((module) => ({
    default: module.AgentOffice3D,
  })),
);

export function AgentObservabilityView({
  job,
  events,
  selectedSnapshot,
  selectedAgentId,
  onSelectAgent,
  onOpenEvidence,
  memoryCollections,
  memoryRecords,
  selectedMemoryRecord,
  memorySearchText,
  loadingMemory,
  curatingMemory,
  onMemorySearchChange,
  onSelectMemoryRecord,
  onCurateMemoryRecord,
  onDeleteMemoryRecord,
}: {
  job: ApiRunJobStatus | null;
  events: AgentRuntimeEvent[];
  selectedSnapshot: RunSnapshot | null;
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
  onOpenEvidence?: () => void;
  memoryCollections: MemoryCollectionSummary[];
  memoryRecords: MemoryRecordSummary[];
  selectedMemoryRecord: ReasoningMemoryRecord | null;
  memorySearchText: string;
  loadingMemory: boolean;
  curatingMemory: boolean;
  onMemorySearchChange: (value: string) => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
  onCurateMemoryRecord: (
    memoryRecordId: string,
    action: "exclude" | "restore",
  ) => void;
  onDeleteMemoryRecord: (memoryRecordId: string) => void;
}) {
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const selectedEvents = eventsForAgent(events, selectedAgentId);
  const selectedEvent =
    selectedEvents.length > 0 ? selectedEvents[selectedEvents.length - 1] : null;
  const conversationMessages = agentConversationMessages(events);
  const agentDecisionEvents = events.filter(
    (event) => event.kind === "agent_decision" || event.kind === "supervisor_decision",
  );
  const memoryEvents = events.filter((event) => event.kind === "memory_retrieval");
  const executorEvents = events.filter((event) => event.kind === "executor_result");
  const errorEvents = events.filter((event) => event.kind === "error");
  const activeAgents = AGENT_PROFILES.filter(
    (agent) => eventsForAgent(events, agent.id).length > 0,
  ).length;
  const [officeMode, setOfficeMode] = useState<AgentOfficeMode>("twoD");
  const [workspaceMode, setWorkspaceMode] = useState<AgentWorkspaceMode>("runtime");
  const showingOffice3D = officeMode === "threeD";

  return (
    <section className="agent-workspace">
      <section className="panel agent-overview-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Investigacion agentica</p>
            <h2>Runtime, memoria y decisiones</h2>
          </div>
          <div className="agent-overview-actions">
            {selectedSnapshot && onOpenEvidence ? (
              <button
                className="secondary-button agent-evidence-link"
                type="button"
                onClick={onOpenEvidence}
              >
                <FileText size={16} />
                Evidencia
              </button>
            ) : null}
            <AgentWorkspaceModeToggle
              mode={workspaceMode}
              onChange={setWorkspaceMode}
            />
            <Activity size={20} />
          </div>
        </div>
        <div className="agent-research-grid">
          <ResearchSignal
            icon={<Brain size={18} />}
            label="Decisiones"
            value={agentDecisionEvents.length.toString()}
            tone="ok"
          />
          <ResearchSignal
            icon={<Database size={18} />}
            label="Memoria"
            value={memoryEvents.length.toString()}
            tone={memoryEvents.length > 0 ? "ok" : "muted"}
          />
          <ResearchSignal
            icon={<Wrench size={18} />}
            label="Ejecutores"
            value={executorEvents.length.toString()}
          />
          <ResearchSignal
            icon={<AlertTriangle size={18} />}
            label="Errores"
            value={errorEvents.length.toString()}
            tone={errorEvents.length > 0 ? "danger" : "ok"}
          />
          <ResearchSignal
            icon={<Network size={18} />}
            label="Agentes activos"
            value={`${activeAgents}/${AGENT_PROFILES.length}`}
          />
          <ResearchSignal
            icon={<Clock3 size={18} />}
            label="Ultimo evento"
            value={latestEvent ? formatEventTime(latestEvent.created_at) : "-"}
          />
        </div>
      </section>

      {workspaceMode === "memory" ? (
        <AgentMemoryShowcase
          events={events}
          selectedAgentId={selectedAgentId}
          memoryCollections={memoryCollections}
          memoryRecords={memoryRecords}
          selectedMemoryRecord={selectedMemoryRecord}
          memorySearchText={memorySearchText}
          loadingMemory={loadingMemory}
          curatingMemory={curatingMemory}
          onSelectAgent={onSelectAgent}
          onMemorySearchChange={onMemorySearchChange}
          onSelectMemoryRecord={onSelectMemoryRecord}
          onCurateMemoryRecord={onCurateMemoryRecord}
          onDeleteMemoryRecord={onDeleteMemoryRecord}
        />
      ) : (
        <>
      <section className={`panel agent-map-panel ${showingOffice3D ? "wide-3d" : ""}`}>
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Runtime</p>
            <h2>{showingOffice3D ? "Oficina 3D agentica" : "Oficina agentica"}</h2>
          </div>
          <div className="agent-office-heading-actions">
            <AgentOfficeModeToggle mode={officeMode} onChange={setOfficeMode} />
            <Network size={20} />
          </div>
        </div>

        {!showingOffice3D ? (
          <div className="agent-live-band">
            <StatusItem icon={<Activity size={18} />} label="Job" value={job?.status ?? "-"} />
            <StatusItem icon={<MessageSquare size={18} />} label="Eventos" value={events.length.toString()} />
            <StatusItem icon={<Brain size={18} />} label="Ultimo" value={latestEvent?.source ?? "-"} />
          </div>
        ) : null}

        {showingOffice3D ? (
          <Suspense
            fallback={
              <p className="empty-state compact-empty">Preparando oficina 3D</p>
            }
          >
            <AgentOffice3D
              events={events}
              selectedAgentId={selectedAgentId}
              onSelectAgent={onSelectAgent}
            />
          </Suspense>
        ) : (
          <div className="agent-office">
            <AgentNodeCard
              agentId="supervisor"
              selectedAgentId={selectedAgentId}
              events={events}
              onSelectAgent={onSelectAgent}
            />
            <div className="agent-branch" aria-hidden="true" />
            <div className="agent-grid">
              {AGENT_PROFILES.filter((agent) => agent.id !== "supervisor").map((agent) => (
                <AgentNodeCard
                  key={agent.id}
                  agentId={agent.id}
                  selectedAgentId={selectedAgentId}
                  events={events}
                  onSelectAgent={onSelectAgent}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      {!showingOffice3D ? (
        <section className="panel agent-detail-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Decision</p>
              <h2>{agentLabel(selectedAgentId)}</h2>
            </div>
            <Brain size={20} />
          </div>
          <AgentRuntimeDetail
            event={selectedEvent}
            eventCount={selectedEvents.length}
            onSelectMemoryRecord={onSelectMemoryRecord}
          />
          <AgentMemoryPanel
            agentId={selectedAgentId}
            events={selectedEvents}
            collections={memoryCollections}
            records={memoryRecords}
            selectedRecord={selectedMemoryRecord}
            searchText={memorySearchText}
            loading={loadingMemory}
            curating={curatingMemory}
            onSearchChange={onMemorySearchChange}
            onSelectRecord={onSelectMemoryRecord}
            onCurateRecord={onCurateMemoryRecord}
            onDeleteRecord={onDeleteMemoryRecord}
          />
        </section>
      ) : null}

      <section className="panel timeline-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Timeline</p>
            <h2>Eventos reales</h2>
          </div>
          <Clock3 size={20} />
        </div>
        <AgentRuntimeTimeline events={events} onSelectAgent={onSelectAgent} />
      </section>

      <section className="panel conversation-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Comunicacion</p>
            <h2>Conversacion</h2>
          </div>
          <MessageSquare size={20} />
        </div>
        <AgentConversation
          messages={conversationMessages}
          onSelectAgent={onSelectAgent}
        />
      </section>
        </>
      )}
    </section>
  );
}

function AgentWorkspaceModeToggle({
  mode,
  onChange,
}: {
  mode: AgentWorkspaceMode;
  onChange: (mode: AgentWorkspaceMode) => void;
}) {
  return (
    <div className="visual-mode-toggle agent-workspace-mode-toggle" aria-label="Vista agentica" role="group">
      <button
        aria-pressed={mode === "runtime"}
        className={mode === "runtime" ? "active" : ""}
        onClick={() => onChange("runtime")}
        title="Mostrar runtime agentico"
        type="button"
      >
        <Activity size={15} />
        <span>Runtime</span>
      </button>
      <button
        aria-pressed={mode === "memory"}
        className={mode === "memory" ? "active" : ""}
        onClick={() => onChange("memory")}
        title="Mostrar memoria agentica"
        type="button"
      >
        <Brain size={15} />
        <span>Memoria</span>
      </button>
    </div>
  );
}

function AgentOfficeModeToggle({
  mode,
  onChange,
}: {
  mode: AgentOfficeMode;
  onChange: (mode: AgentOfficeMode) => void;
}) {
  return (
    <div className="visual-mode-toggle agent-office-mode-toggle" aria-label="Modo de oficina agentica" role="group">
      <button
        aria-pressed={mode === "twoD"}
        className={mode === "twoD" ? "active" : ""}
        onClick={() => onChange("twoD")}
        title="Mostrar oficina 2D"
        type="button"
      >
        <Network size={15} />
        <span>2D</span>
      </button>
      <button
        aria-pressed={mode === "threeD"}
        className={mode === "threeD" ? "active" : ""}
        onClick={() => onChange("threeD")}
        title="Mostrar oficina 3D"
        type="button"
      >
        <Box size={15} />
        <span>3D</span>
      </button>
    </div>
  );
}

function ResearchSignal({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "danger" | "muted";
}) {
  return (
    <article className={`agent-research-signal tone-${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function AgentRuntimeTimeline({
  events,
  onSelectAgent,
}: {
  events: AgentRuntimeEvent[];
  onSelectAgent: (agentId: string) => void;
}) {
  if (events.length === 0) {
    return <p className="empty-state compact-empty">Sin eventos runtime</p>;
  }

  return (
    <div className="runtime-timeline" aria-label="Timeline de eventos agenticos">
      {events.slice(-60).map((event) => (
        <button
          className={`timeline-event ${event.kind === "error" ? "error" : ""}`}
          key={event.event_id}
          type="button"
          onClick={() => onSelectAgent(eventOwnerId(event))}
        >
          <span>{event.sequence}</span>
          <div>
            <strong>{event.title}</strong>
            <small>
              {formatEventTime(event.created_at)} | {sourceLabel(event)} |{" "}
              {event.stage ?? kindLabel(event.kind)}
            </small>
          </div>
        </button>
      ))}
    </div>
  );
}

function AgentNodeCard({
  agentId,
  selectedAgentId,
  events,
  onSelectAgent,
}: {
  agentId: string;
  selectedAgentId: string;
  events: AgentRuntimeEvent[];
  onSelectAgent: (agentId: string) => void;
}) {
  const profile = AGENT_PROFILES.find((agent) => agent.id === agentId);
  const agentEvents = eventsForAgent(events, agentId);
  const latestEvent =
    agentEvents.length > 0 ? agentEvents[agentEvents.length - 1] : null;
  const isSelected = selectedAgentId === agentId;
  const isActive = events.length > 0 && latestEvent?.sequence === events[events.length - 1].sequence;

  return (
    <button
      className={`agent-node ${isSelected ? "selected" : ""} ${isActive ? "active" : ""}`}
      type="button"
      onClick={() => onSelectAgent(agentId)}
    >
      <span className="agent-avatar">
        {agentId === "supervisor" ? <Network size={18} /> : <Brain size={18} />}
      </span>
      <span>
        <strong>{profile?.label ?? agentId}</strong>
        <small>{profile?.role ?? "Agente"}</small>
      </span>
      <em>{agentEvents.length}</em>
    </button>
  );
}

function AgentRuntimeDetail({
  event,
  eventCount,
  onSelectMemoryRecord,
}: {
  event: AgentRuntimeEvent | null;
  eventCount: number;
  onSelectMemoryRecord?: (memoryRecordId: string) => void;
}) {
  if (event === null) {
    return <p className="empty-state compact-empty">Sin eventos del agente</p>;
  }

  const runtimeSignals = runtimeSignalChips(event);
  const nextStep = event.next_node ?? event.next_stage ?? "-";

  return (
    <div className="agent-detail">
      <section className="agent-decision-card">
        <div className="event-head">
          <StatusPill ok={event.kind !== "error"} label={kindLabel(event.kind)} />
          <span>{eventCount} eventos</span>
        </div>
        <h3>{event.title}</h3>
        <p className="agent-event-summary">{event.summary}</p>
        <AgentEventTranslation event={event} />

        <div className="agent-decision-grid">
          <DecisionFact icon={<FileJson size={16} />} label="Decision" value={event.decision_id ?? "-"} />
          <DecisionFact icon={<Brain size={16} />} label="Confianza" value={confidenceText(event.confidence)} />
          <DecisionFact icon={<ListChecks size={16} />} label="Fase" value={event.stage ?? "-"} />
          <DecisionFact icon={<Route size={16} />} label="Siguiente" value={nextStep} />
        </div>
      </section>

      {event.rationale ? (
        <details className="runtime-block compact-disclosure agent-rationale-block">
          <summary>Rationale</summary>
          <p>{event.rationale}</p>
        </details>
      ) : null}

      {runtimeSignals.length > 0 ? (
        <section className="runtime-block">
          <h4>Herramientas y señales</h4>
          <div className="agent-signal-chip-row">
            {runtimeSignals.map((signal) => (
              <span className={`agent-signal-chip ${signal.tone}`} key={`${signal.label}-${signal.value}`}>
                {signal.label}: {signal.value}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {event.memory_record_ids.length > 0 ? (
        <section className="runtime-block">
          <h4>
            <Quote size={14} />
            Memoria citada
          </h4>
          <div className="memory-chip-row">
            {event.memory_record_ids.map((memoryId) => (
              onSelectMemoryRecord ? (
                <button
                  className="memory-chip memory-chip-button"
                  key={memoryId}
                  type="button"
                  onClick={() => onSelectMemoryRecord(memoryId)}
                >
                  {memoryId}
                </button>
              ) : (
                <span className="memory-chip" key={memoryId}>
                  {memoryId}
                </span>
              )
            ))}
          </div>
        </section>
      ) : null}

      <details className="runtime-block compact-disclosure runtime-payload-details">
        <summary>
          <FileJson size={15} />
          Payload tecnico
        </summary>
        <pre className="runtime-json">{JSON.stringify(event.payload, null, 2)}</pre>
      </details>
    </div>
  );
}

function DecisionFact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="agent-decision-fact">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function runtimeSignalChips(
  event: AgentRuntimeEvent,
): Array<{ label: string; value: string; tone: "neutral" | "warning" | "danger" }> {
  const payload = event.payload;
  const chips: Array<{ label: string; value: string; tone: "neutral" | "warning" | "danger" }> = [];
  const signalKeys: Array<{ key: string; label: string; tone?: "neutral" | "warning" | "danger" }> = [
    { key: "tool_names", label: "tools" },
    { key: "tool_calls", label: "tools" },
    { key: "tools_used", label: "tools" },
    { key: "used_tools", label: "tools" },
    { key: "evidence_refs", label: "evidencia" },
    { key: "guardrail_checks", label: "guardrails", tone: "warning" },
    { key: "required_corrections", label: "correcciones", tone: "warning" },
    { key: "changes_summary", label: "cambios" },
    { key: "accepted_issue_ids", label: "issues aceptadas" },
    { key: "rejected_issue_ids", label: "issues rechazadas", tone: "warning" },
  ];

  for (const signal of signalKeys) {
    const values = stringArrayFromUnknown(payload[signal.key]);
    if (values.length > 0) {
      chips.push({
        label: signal.label,
        value: compactList(values),
        tone: signal.tone ?? "neutral",
      });
    }
  }

  for (const key of ["fallback_reason", "fallback_mode", "fallback_used", "repair_error", "error"]) {
    const value = stringFromUnknown(payload[key]);
    if (value) {
      chips.push({
        label: key.replace(/_/g, " "),
        value,
        tone: key === "error" || key === "repair_error" ? "danger" : "warning",
      });
    }
  }

  const verificationStatus = stringFromUnknown(payload.verification_status);
  if (verificationStatus) {
    chips.push({
      label: "verificacion",
      value: verificationStatus,
      tone:
        verificationStatus === "approved" || verificationStatus === "ok"
          ? "neutral"
          : "warning",
    });
  }

  return chips;
}

function stringArrayFromUnknown(value: unknown): string[] {
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

function compactList(values: string[]): string {
  const visible = values.slice(0, 3);
  const suffix = values.length > visible.length ? ` +${values.length - visible.length}` : "";
  return `${visible.join(", ")}${suffix}`;
}

function AgentEventTranslation({ event }: { event: AgentRuntimeEvent }) {
  return (
    <section className="agent-translation" aria-label="Traduccion del evento JSON">
      <div>
        <span>Lectura humana</span>
        <strong>{agentEventPlainText(event)}</strong>
      </div>
    </section>
  );
}

function AgentConversation({
  messages,
  onSelectAgent,
}: {
  messages: AgentConversationMessage[];
  onSelectAgent: (agentId: string) => void;
}) {
  if (messages.length === 0) {
    return (
      <p className="empty-state compact-empty">
        Sin conversacion agentica todavia
      </p>
    );
  }

  return (
    <div className="agent-chat" aria-label="Conversacion agentica">
      {messages.map((message) => (
        <button
          className={`chat-message ${message.status}`}
          key={message.id}
          type="button"
          onClick={() => onSelectAgent(message.agentId)}
        >
          <span className="chat-avatar">{agentInitials(message.agentLabel)}</span>
          <span className="chat-bubble">
            <span className="chat-meta">
              <strong>{message.agentLabel}</strong>
              <em>{formatEventTime(message.createdAt)}</em>
            </span>
            <span className="chat-role">{message.role}</span>
            <span className="chat-title">{message.title}</span>
            <span className="chat-text">{message.text}</span>
            {message.badges.length > 0 ? (
              <span className="chat-chip-row">
                {message.badges.map((badge) => (
                  <span className="chat-chip" key={`${message.id}-${badge}`}>
                    {badge}
                  </span>
                ))}
              </span>
            ) : null}
          </span>
        </button>
      ))}
    </div>
  );
}
