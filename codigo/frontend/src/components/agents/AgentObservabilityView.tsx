import { Activity, Brain, MessageSquare, Network } from "lucide-react";

import { StatusItem } from "../common/StatusItem";
import { StatusPill } from "../common/StatusPill";
import { AgentMemoryPanel } from "../memory/AgentMemoryPanel";
import {
  AGENT_PROFILES,
  agentConversationMessages,
  agentEventPlainText,
  agentInitials,
  agentLabel,
  eventsForAgent,
  kindLabel,
} from "../../lib/agentRuntime";
import { confidenceText, formatEventTime } from "../../lib/formatters";
import type {
  AgentRuntimeEvent,
  ApiRunJobStatus,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  ReasoningMemoryRecord,
} from "../../types";
import type { AgentConversationMessage } from "../../lib/agentRuntime";

export function AgentObservabilityView({
  job,
  events,
  selectedAgentId,
  onSelectAgent,
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
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
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

  return (
    <section className="agent-workspace">
      <section className="panel agent-map-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Runtime</p>
            <h2>Oficina agentica</h2>
          </div>
          <Network size={20} />
        </div>

        <div className="agent-live-band">
          <StatusItem icon={<Activity size={18} />} label="Job" value={job?.status ?? "-"} />
          <StatusItem icon={<MessageSquare size={18} />} label="Eventos" value={events.length.toString()} />
          <StatusItem icon={<Brain size={18} />} label="Ultimo" value={latestEvent?.source ?? "-"} />
        </div>

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
      </section>

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
    </section>
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

  return (
    <div className="agent-detail">
      <div className="event-head">
        <StatusPill ok={event.kind !== "error"} label={kindLabel(event.kind)} />
        <span>{eventCount} eventos</span>
      </div>
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <AgentEventTranslation event={event} />
      <dl className="meta-list detail-meta">
        <div>
          <dt>decision_id</dt>
          <dd>{event.decision_id ?? "-"}</dd>
        </div>
        <div>
          <dt>confianza</dt>
          <dd>{confidenceText(event.confidence)}</dd>
        </div>
        <div>
          <dt>fase</dt>
          <dd>{event.stage ?? "-"}</dd>
        </div>
        <div>
          <dt>siguiente</dt>
          <dd>{event.next_node ?? event.next_stage ?? "-"}</dd>
        </div>
      </dl>
      {event.rationale ? (
        <section className="runtime-block">
          <h4>Rationale</h4>
          <p>{event.rationale}</p>
        </section>
      ) : null}
      {event.memory_record_ids.length > 0 ? (
        <section className="runtime-block">
          <h4>Memoria citada</h4>
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
      <section className="runtime-block">
        <h4>Payload</h4>
        <pre className="runtime-json">{JSON.stringify(event.payload, null, 2)}</pre>
      </section>
    </div>
  );
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
      <p className="empty-state">
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
