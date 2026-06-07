import {
  Brain,
  Database,
  FileText,
  Quote,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";

import { AgentMemoryPanel } from "../memory/AgentMemoryPanel";
import {
  AGENT_PROFILES,
  agentInitials,
  eventsForAgent,
} from "../../lib/agentRuntime";
import {
  memoryTargetForAgent,
  recordStateLabel,
  roleLabel,
  sourceTypeLabel,
} from "../../lib/memoryRecords";
import type {
  AgentRuntimeEvent,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  ReasoningMemoryRecord,
} from "../../types";

const DEFAULT_AGENT_TOOLS: Record<string, string[]> = {
  supervisor: ["orquesta fases", "prioriza ruta", "controla cierre"],
  cleaner: ["perfil estadistico", "limpieza de senal", "control de calidad"],
  structurer: ["ventanas temporales", "features", "particiones"],
  modeler: ["entrenamiento", "umbrales", "comparacion modelos"],
  evaluator: ["metricas", "riesgo", "aprobacion"],
  report_writer: ["informe", "evidencia", "resumen tecnico"],
  report_verifier: ["auditoria", "guardrails", "correcciones"],
};

export function AgentMemoryShowcase({
  events,
  selectedAgentId,
  memoryCollections,
  memoryRecords,
  selectedMemoryRecord,
  memorySearchText,
  loadingMemory,
  curatingMemory,
  onSelectAgent,
  onMemorySearchChange,
  onSelectMemoryRecord,
  onCurateMemoryRecord,
  onDeleteMemoryRecord,
}: {
  events: AgentRuntimeEvent[];
  selectedAgentId: string;
  memoryCollections: MemoryCollectionSummary[];
  memoryRecords: MemoryRecordSummary[];
  selectedMemoryRecord: ReasoningMemoryRecord | null;
  memorySearchText: string;
  loadingMemory: boolean;
  curatingMemory: boolean;
  onSelectAgent: (agentId: string) => void;
  onMemorySearchChange: (value: string) => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
  onCurateMemoryRecord: (
    memoryRecordId: string,
    action: "exclude" | "restore",
  ) => void;
  onDeleteMemoryRecord: (memoryRecordId: string) => void;
}) {
  const selectedProfile =
    AGENT_PROFILES.find((agent) => agent.id === selectedAgentId) ??
    AGENT_PROFILES[0];
  const selectedEvents = eventsForAgent(events, selectedProfile.id);
  const selectedTarget = memoryTargetForAgent(selectedProfile.id);
  const selectedCollection =
    memoryCollections.find((collection) => collection.target_agent === selectedTarget) ??
    null;
  const selectedRecords = recordsForAgent(memoryRecords, selectedProfile.id);
  const selectedTools = toolsForAgent(events, selectedProfile.id);
  const selectedCitedIds = citedMemoryIds(selectedEvents);
  const featuredRecords = featuredMemoryRecords(selectedRecords, selectedCitedIds);
  const state = memoryState(selectedRecords, selectedCitedIds);

  return (
    <section className="panel agent-memory-showcase">
      <div className="panel-heading memory-showcase-heading">
        <div>
          <p className="eyebrow">Memoria agentica</p>
          <h2>Seleccion de agentes</h2>
        </div>
        <Brain size={20} />
      </div>

      <div className="memory-agent-select" aria-label="Seleccion de agente para memoria">
        {AGENT_PROFILES.map((agent) => {
          const agentEvents = eventsForAgent(events, agent.id);
          const agentRecords = recordsForAgent(memoryRecords, agent.id);
          const agentCitedIds = citedMemoryIds(agentEvents);
          const agentTools = toolsForAgent(events, agent.id);
          const agentState = memoryState(agentRecords, agentCitedIds);
          return (
            <button
              aria-pressed={agent.id === selectedProfile.id}
              className={`memory-agent-card agent-tone-${agent.id} ${
                agent.id === selectedProfile.id ? "selected" : ""
              }`}
              key={agent.id}
              type="button"
              onClick={() => onSelectAgent(agent.id)}
            >
              <span className="memory-agent-token">
                {agent.id === "supervisor" ? <ShieldCheck size={16} /> : agentInitials(agent.label)}
              </span>
              <span className="memory-agent-card-main">
                <strong>{agent.label}</strong>
                <small>{agent.role}</small>
              </span>
              <span className={`memory-agent-state ${agentState.tone}`}>
                {agentState.label}
              </span>
              <span className="memory-agent-card-meta">
                <em>{agentRecords.length} rec</em>
                <em>{agentTools.length} tools</em>
              </span>
            </button>
          );
        })}
      </div>

      <div className={`memory-stage agent-tone-${selectedProfile.id}`}>
        <section className="memory-character-card">
          <div className="memory-character-figure" aria-hidden="true">
            <span className="memory-figure-crown" />
            <span className="memory-figure-head" />
            <span className="memory-figure-body">
              <span className="memory-figure-badge" />
            </span>
            <span className="memory-figure-legs">
              <i />
              <i />
            </span>
          </div>
          <div className="memory-character-copy">
            <span className={`memory-agent-state ${state.tone}`}>{state.label}</span>
            <h3>{selectedProfile.label}</h3>
            <p>{selectedProfile.role}</p>
          </div>

          <div className="memory-character-stats">
            <MemoryMiniStat icon={<Database size={15} />} label="records" value={selectedRecords.length} />
            <MemoryMiniStat
              icon={<Quote size={15} />}
              label="citados"
              value={selectedCitedIds.size}
            />
            <MemoryMiniStat icon={<Wrench size={15} />} label="tools" value={selectedTools.length} />
          </div>

          <div className="memory-tool-row">
            {selectedTools.slice(0, 7).map((tool) => (
              <span className="memory-tool-chip" key={`${selectedProfile.id}-${tool}`}>
                {tool}
              </span>
            ))}
          </div>
        </section>

        <section className="memory-brief-board">
          <div className="memory-brief-head">
            <div>
              <span>{selectedCollection?.collection_name ?? selectedTarget}</span>
              <h3>Recuerdos utiles</h3>
            </div>
            <span className="memory-brief-count">
              {selectedCollection?.n_reusable ?? selectedRecords.filter((record) => record.reusable_as_context).length}
            </span>
          </div>

          {featuredRecords.length === 0 ? (
            <p className="empty-state compact-empty">Sin recuerdos indexados para este agente</p>
          ) : (
            <div className="memory-brief-grid">
              {featuredRecords.map((record) => (
                <button
                  className={`memory-brief-card ${
                    selectedMemoryRecord?.memory_record_id === record.memory_record_id ? "selected" : ""
                  } ${selectedCitedIds.has(record.memory_record_id) ? "cited" : ""}`}
                  key={record.memory_record_id}
                  type="button"
                  onClick={() => onSelectMemoryRecord(record.memory_record_id)}
                >
                  <span className="memory-brief-card-top">
                    <em>{roleLabel(record.memory_role)}</em>
                    <em>{sourceTypeLabel(record.source_type)}</em>
                    <em>{recordStateLabel(record)}</em>
                  </span>
                  <strong>{humanMemorySentence(record)}</strong>
                  <span className="memory-brief-card-meta">
                    <FileText size={14} />
                    {record.dataset ?? record.run_id ?? "sin dataset"}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      <details className="compact-disclosure memory-technical-drawer">
        <summary>Detalle tecnico de memoria</summary>
        <AgentMemoryPanel
          agentId={selectedProfile.id}
          events={selectedEvents}
          collections={memoryCollections}
          records={selectedRecords}
          selectedRecord={selectedMemoryRecord}
          searchText={memorySearchText}
          loading={loadingMemory}
          curating={curatingMemory}
          onSearchChange={onMemorySearchChange}
          onSelectRecord={onSelectMemoryRecord}
          onCurateRecord={onCurateMemoryRecord}
          onDeleteRecord={onDeleteMemoryRecord}
        />
      </details>
    </section>
  );
}

function MemoryMiniStat({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: number;
}) {
  return (
    <span className="memory-mini-stat">
      {icon}
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

function recordsForAgent(
  records: MemoryRecordSummary[],
  agentId: string,
): MemoryRecordSummary[] {
  const target = memoryTargetForAgent(agentId);
  const targetRecords = records.filter((record) => record.target_agent === target);
  if (target !== "shared_methodology") {
    return targetRecords;
  }
  const specificRecords = targetRecords.filter((record) => {
    const source = record.source_agent_name ?? "";
    return source === agentId || source.includes(agentId);
  });
  return specificRecords.length > 0 ? specificRecords : targetRecords;
}

function featuredMemoryRecords(
  records: MemoryRecordSummary[],
  citedIds: Set<string>,
): MemoryRecordSummary[] {
  return [...records]
    .sort((left, right) => {
      const citedDiff =
        Number(citedIds.has(right.memory_record_id)) -
        Number(citedIds.has(left.memory_record_id));
      if (citedDiff !== 0) {
        return citedDiff;
      }
      const reusableDiff =
        Number(right.reusable_as_context) - Number(left.reusable_as_context);
      if (reusableDiff !== 0) {
        return reusableDiff;
      }
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    })
    .slice(0, 5);
}

function toolsForAgent(events: AgentRuntimeEvent[], agentId: string): string[] {
  const tools = new Set(DEFAULT_AGENT_TOOLS[agentId] ?? []);
  const toolKeys = ["tool_names", "tool_calls", "tools_used", "used_tools", "tools"];
  for (const event of eventsForAgent(events, agentId)) {
    for (const key of toolKeys) {
      for (const tool of stringArrayFromUnknown(event.payload[key])) {
        tools.add(shortLabel(tool, 34));
      }
    }
  }
  return Array.from(tools).slice(0, 8);
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) {
    const scalar = stringFromUnknown(value);
    return scalar ? [scalar] : [];
  }
  return value
    .map((item) => stringFromUnknown(item))
    .filter((item): item is string => item !== null);
}

function stringFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value && typeof value === "object") {
    const candidate = value as { name?: unknown; tool_name?: unknown; label?: unknown };
    for (const field of [candidate.name, candidate.tool_name, candidate.label]) {
      if (typeof field === "string" && field.trim().length > 0) {
        return field.trim();
      }
    }
  }
  return null;
}

function citedMemoryIds(events: AgentRuntimeEvent[]): Set<string> {
  const ids = new Set<string>();
  for (const event of events) {
    for (const memoryId of event.memory_record_ids) {
      ids.add(memoryId);
    }
    for (const memoryId of stringArrayFromUnknown(event.payload.cited_memory_record_ids)) {
      ids.add(memoryId);
    }
  }
  return ids;
}

function memoryState(
  records: MemoryRecordSummary[],
  citedIds: Set<string>,
): { label: string; tone: "ok" | "warning" | "danger" | "muted" } {
  if (records.some((record) => record.exclude_from_context || record.memory_role === "excluded")) {
    return { label: "revisar", tone: "danger" };
  }
  if (citedIds.size > 0) {
    return { label: "citada", tone: "ok" };
  }
  if (records.some((record) => record.reusable_as_context)) {
    return { label: "recuperable", tone: "ok" };
  }
  if (records.length > 0) {
    return { label: "indexada", tone: "warning" };
  }
  return { label: "sin memoria", tone: "muted" };
}

function humanMemorySentence(record: MemoryRecordSummary): string {
  const cleaned = record.summary
    .replace(/[`*_#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const fallback = `${roleLabel(record.memory_role)} desde ${sourceTypeLabel(record.source_type)}`;
  const sentence = cleaned.length > 0 ? cleaned : fallback;
  return ensureSentence(shortLabel(sentence, 180));
}

function shortLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}

function ensureSentence(value: string): string {
  if (/[.!?]$/.test(value)) {
    return value;
  }
  return `${value}.`;
}
