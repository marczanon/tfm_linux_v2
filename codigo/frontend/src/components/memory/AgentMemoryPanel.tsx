import { useMemo } from "react";

import { StatusPill } from "../common/StatusPill";
import {
  isRecord,
  kindLabel,
  numberValue,
  recordFromPayload,
  stringArrayFromPayload,
  stringFromPayload,
  stringValue,
} from "../../lib/agentRuntime";
import { formatEventTime, formatMetric } from "../../lib/formatters";
import {
  memoryTargetForAgent,
  outcomeLabel,
  recordStateLabel,
  roleLabel,
  sourceTypeLabel,
  verdictLabel,
} from "../../lib/memoryRecords";
import type {
  AgentRuntimeEvent,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  ReasoningMemoryRecord,
} from "../../types";

export function AgentMemoryPanel({
  agentId,
  events,
  collections,
  records,
  selectedRecord,
  searchText,
  loading,
  curating,
  onSearchChange,
  onSelectRecord,
  onCurateRecord,
  onDeleteRecord,
}: {
  agentId: string;
  events: AgentRuntimeEvent[];
  collections: MemoryCollectionSummary[];
  records: MemoryRecordSummary[];
  selectedRecord: ReasoningMemoryRecord | null;
  searchText: string;
  loading: boolean;
  curating: boolean;
  onSearchChange: (value: string) => void;
  onSelectRecord: (memoryRecordId: string) => void;
  onCurateRecord: (memoryRecordId: string, action: "exclude" | "restore") => void;
  onDeleteRecord: (memoryRecordId: string) => void;
}) {
  const target = memoryTargetForAgent(agentId);
  const collection = collections.find((item) => item.target_agent === target) ?? null;
  const sourceTypes = collection?.source_types ?? {};
  const retrievedMemoryIds = useMemo(
    () =>
      new Set(
        events
          .filter((event) => event.kind === "memory_retrieval" || event.memory_context_id !== null)
          .flatMap((event) => event.memory_record_ids),
      ),
    [events],
  );
  const citedMemoryIds = useMemo(
    () => new Set(events.flatMap((event) => event.memory_record_ids)),
    [events],
  );
  const lifecycleStages = [
    {
      label: "candidatos",
      value: sourceTypes.memory_candidate ?? 0,
      detail: "destilados",
      tone: "candidate",
    },
    {
      label: "indexados",
      value: collection?.n_records ?? 0,
      detail: collection?.collection_name ?? target,
      tone: "indexed",
    },
    {
      label: "recuperados",
      value: retrievedMemoryIds.size,
      detail: "runtime actual",
      tone: "reusable",
    },
    {
      label: "usados",
      value: citedMemoryIds.size,
      detail: "citados por agente",
      tone: "used",
    },
    {
      label: "auditorias",
      value: sourceTypes.memory_usage_audit ?? 0,
      detail: "uso posterior",
      tone: "audited",
    },
  ];

  return (
    <section className="runtime-block memory-panel">
      <div className="section-heading">
        <div>
          <h3>Cockpit de memoria</h3>
          <p>{collection?.collection_name ?? target}</p>
        </div>
        <StatusPill
          ok={(collection?.n_records ?? 0) > 0}
          label={`${collection?.n_records ?? 0} recuerdos`}
          muted={(collection?.n_records ?? 0) === 0}
        />
      </div>

      <div className="memory-cockpit-grid">
        <MemoryStat label="Total" value={collection?.n_records ?? 0} />
        <MemoryStat label="Reutilizables" value={collection?.n_reusable ?? 0} />
        <MemoryStat label="Datasets" value={collection?.datasets.length ?? 0} />
        <MemoryStat label="Excluidos" value={collection?.n_excluded ?? 0} tone="warning" />
      </div>

      <MemoryLifecycleStrip stages={lifecycleStages} />

      <div className="memory-distribution-grid">
        <MemoryDistribution
          title="Roles"
          entries={collection?.memory_roles ?? {}}
          labelFor={roleLabel}
        />
        <MemoryDistribution
          title="Origen"
          entries={collection?.source_types ?? {}}
          labelFor={sourceTypeLabel}
        />
      </div>

      <MemoryRuntimeFlow
        events={events}
        onSelectRecord={onSelectRecord}
      />

      <label className="field compact-field">
        <span>Buscar</span>
        <input
          value={searchText}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      {loading ? (
        <p className="empty-state compact-empty">Cargando memoria</p>
      ) : (
        <MemoryRecordList
          records={records}
          selectedRecordId={selectedRecord?.memory_record_id ?? null}
          usedRecordIds={citedMemoryIds}
          onSelectRecord={onSelectRecord}
        />
      )}

      <MemoryRecordDetail
        record={selectedRecord}
        curating={curating}
        onCurateRecord={onCurateRecord}
        onDeleteRecord={onDeleteRecord}
      />
    </section>
  );
}

function MemoryStat({
  label,
  value,
  tone = "normal",
}: {
  label: string;
  value: number;
  tone?: "normal" | "warning";
}) {
  return (
    <div className={`memory-stat ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MemoryLifecycleStrip({
  stages,
}: {
  stages: { label: string; value: number; detail: string; tone: string }[];
}) {
  return (
    <div className="memory-lifecycle" aria-label="Ciclo de vida de memoria">
      {stages.map((stage) => (
        <div className={`memory-lifecycle-step ${stage.tone}`} key={stage.label}>
          <span>{stage.label}</span>
          <strong>{stage.value}</strong>
          <small>{stage.detail}</small>
        </div>
      ))}
    </div>
  );
}

function MemoryDistribution({
  title,
  entries,
  labelFor,
}: {
  title: string;
  entries: Record<string, number>;
  labelFor: (value: string) => string;
}) {
  const sortedEntries = Object.entries(entries).sort((left, right) => right[1] - left[1]);
  return (
    <section className="memory-distribution">
      <h4>{title}</h4>
      {sortedEntries.length === 0 ? (
        <p>sin datos</p>
      ) : (
        <div className="memory-chip-row">
          {sortedEntries.slice(0, 6).map(([key, value]) => (
            <span className="memory-chip subtle" key={key}>
              {labelFor(key)} · {value}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function MemoryRuntimeFlow({
  events,
  onSelectRecord,
}: {
  events: AgentRuntimeEvent[];
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  const memoryEvents = events.filter(
    (event) =>
      event.kind === "memory_retrieval" ||
      event.memory_context_id !== null ||
      event.memory_record_ids.length > 0,
  );
  const visibleEvents = memoryEvents.slice(-6).reverse();

  return (
    <section className="memory-runtime-flow">
      <div>
        <h4>Runtime</h4>
        <span>{memoryEvents.length} eventos con memoria</span>
      </div>
      {visibleEvents.length === 0 ? (
        <p className="empty-state compact-empty">Sin recuperaciones en el agente seleccionado</p>
      ) : (
        <div className="memory-flow-list">
          {visibleEvents.map((event) => {
            const retrievalEvent = stringFromPayload(event.payload, "retrieval_event");
            const flowItems = memoryFlowItems(event);
            const meta = memoryFlowMeta(event);
            const query = recordFromPayload(event.payload, "query");
            const queryText = stringValue(query?.query_text);
            const citedIds = stringArrayFromPayload(event.payload, "cited_memory_record_ids");
            const ignoredIds = stringArrayFromPayload(event.payload, "ignored_memory_record_ids");
            const fallbackIds = event.memory_record_ids;
            return (
              <article className="memory-flow-event" key={event.event_id}>
                <div>
                  <strong>{retrievalEventLabel(retrievalEvent, event.kind)}</strong>
                  <span>{formatEventTime(event.created_at)} · {event.memory_context_id ?? "sin contexto"}</span>
                </div>
                {meta.length > 0 ? (
                  <div className="memory-flow-meta">
                    {meta.map((item) => (
                      <span key={`${event.event_id}-${item.label}`}>
                        {item.label}: <strong>{item.value}</strong>
                      </span>
                    ))}
                  </div>
                ) : null}
                <p>{event.summary}</p>
                {queryText ? (
                  <p className="memory-query-excerpt">{shortText(queryText, 220)}</p>
                ) : null}
                {flowItems.length > 0 ? (
                  <div className="memory-flow-items">
                    {flowItems.map((item) => (
                      <button
                        className="memory-flow-item"
                        key={`${event.event_id}-${item.memoryRecordId}`}
                        type="button"
                        onClick={() => onSelectRecord(item.memoryRecordId)}
                      >
                        <strong>
                          #{item.rank ?? "-"} · sim {formatSimilarity(item.similarity)}
                        </strong>
                        <span>{item.memoryRecordId}</span>
                        <em>
                          {roleLabel(item.memoryRole ?? "")} · {sourceTypeLabel(item.sourceType ?? "")} · {item.dataset ?? "-"}
                        </em>
                      </button>
                    ))}
                  </div>
                ) : null}
                {citedIds.length > 0 || ignoredIds.length > 0 || fallbackIds.length > 0 ? (
                  <div className="memory-chip-row">
                    {(citedIds.length > 0 ? citedIds : fallbackIds).slice(0, 4).map((memoryId) => (
                      <button
                        className="memory-chip memory-chip-button"
                        key={`${event.event_id}-cited-${memoryId}`}
                        type="button"
                        onClick={() => onSelectRecord(memoryId)}
                      >
                        usado · {memoryId}
                      </button>
                    ))}
                    {ignoredIds.slice(0, 4).map((memoryId) => (
                      <button
                        className="memory-chip subtle memory-chip-button"
                        key={`${event.event_id}-ignored-${memoryId}`}
                        type="button"
                        onClick={() => onSelectRecord(memoryId)}
                      >
                        ignorado · {memoryId}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

interface MemoryFlowItem {
  memoryRecordId: string;
  rank: number | null;
  similarity: number | null;
  memoryRole: string | null;
  sourceType: string | null;
  dataset: string | null;
}

function retrievalEventLabel(
  retrievalEvent: string | null,
  fallbackKind: AgentRuntimeEvent["kind"],
): string {
  const labels: Record<string, string> = {
    retrieval_unavailable: "RAG no disponible",
    retrieval_requested: "Consulta solicitada",
    retrieval_returned: "Contexto recuperado",
    retrieval_used: "Memoria usada",
    retrieval_rejected_by_agent: "Memoria ignorada",
  };
  return retrievalEvent === null ? kindLabel(fallbackKind) : labels[retrievalEvent] ?? retrievalEvent;
}

function memoryFlowMeta(event: AgentRuntimeEvent): { label: string; value: string }[] {
  const query = recordFromPayload(event.payload, "query");
  const items = [
    {
      label: "backend",
      value: stringFromPayload(event.payload, "retrieval_backend"),
    },
    {
      label: "embedding",
      value: stringFromPayload(event.payload, "embedding_model"),
    },
    {
      label: "top_k",
      value: stringValue(query?.top_k),
    },
    {
      label: "min_sim",
      value: stringValue(query?.min_similarity),
    },
    {
      label: "dataset",
      value: stringValue(query?.dataset),
    },
  ];
  return items.filter((item): item is { label: string; value: string } => item.value !== null);
}

function memoryFlowItems(event: AgentRuntimeEvent): MemoryFlowItem[] {
  const value = event.payload.items;
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .map((item) => {
      const memoryRecordId = stringValue(item.memory_record_id);
      if (memoryRecordId === null) {
        return null;
      }
      return {
        memoryRecordId,
        rank: numberValue(item.rank),
        similarity: numberValue(item.similarity),
        memoryRole: stringValue(item.memory_role),
        sourceType: stringValue(item.source_type),
        dataset: stringValue(item.dataset),
      };
    })
    .filter((item): item is MemoryFlowItem => item !== null);
}

function formatSimilarity(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 3,
  }).format(value);
}

function shortText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}

function MemoryRecordList({
  records,
  selectedRecordId,
  usedRecordIds,
  onSelectRecord,
}: {
  records: MemoryRecordSummary[];
  selectedRecordId: string | null;
  usedRecordIds: Set<string>;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  if (records.length === 0) {
    return <p className="empty-state compact-empty">Sin recuerdos para el filtro actual</p>;
  }

  return (
    <div className="memory-record-list">
      {records.slice(0, 10).map((record) => (
        <button
          className={`memory-record-row ${record.exclude_from_context ? "excluded" : ""} ${
            usedRecordIds.has(record.memory_record_id) ? "used" : ""
          } ${
            record.memory_record_id === selectedRecordId ? "selected" : ""
          }`}
          key={record.memory_record_id}
          type="button"
          onClick={() => onSelectRecord(record.memory_record_id)}
        >
          <div>
            <strong>{record.memory_record_id}</strong>
            <span>
              {record.dataset ?? "-"} | {roleLabel(record.memory_role)} | {sourceTypeLabel(record.source_type)}
            </span>
          </div>
          <p>{record.summary}</p>
          <span className="memory-record-badges">
            {record.reusable_as_context ? <em>reutilizable</em> : null}
            {record.exclude_from_context ? <em>excluido</em> : null}
            {usedRecordIds.has(record.memory_record_id) ? <em>citado</em> : null}
          </span>
        </button>
      ))}
    </div>
  );
}

function MemoryRecordDetail({
  record,
  curating,
  onCurateRecord,
  onDeleteRecord,
}: {
  record: ReasoningMemoryRecord | null;
  curating: boolean;
  onCurateRecord: (memoryRecordId: string, action: "exclude" | "restore") => void;
  onDeleteRecord: (memoryRecordId: string) => void;
}) {
  if (record === null) {
    return null;
  }
  const metricEntries = Object.entries(record.metrics ?? {});
  const embeddingText =
    record.embedding_model === null
      ? "sin embedding"
      : `${record.embedding_model}${record.embedding_dimension ? ` · ${record.embedding_dimension} dim` : ""}`;

  return (
    <section className="memory-record-detail">
      <div className="event-head">
        <StatusPill
          ok={record.reusable_as_context && !record.exclude_from_context}
          label={recordStateLabel(record)}
          muted={!record.exclude_from_context}
        />
        <span>{verdictLabel(record.human_verdict)}</span>
      </div>
      <div className="memory-curation-actions">
        {record.exclude_from_context ? (
          <button
            type="button"
            disabled={curating}
            onClick={() => onCurateRecord(record.memory_record_id, "restore")}
          >
            Restaurar
          </button>
        ) : (
          <button
            type="button"
            disabled={curating}
            onClick={() => onCurateRecord(record.memory_record_id, "exclude")}
          >
            Excluir de RAG
          </button>
        )}
        <button
          className="danger-button"
          type="button"
          disabled={curating}
          onClick={() => onDeleteRecord(record.memory_record_id)}
        >
          Borrar
        </button>
      </div>
      <h4>{record.summary}</h4>
      <dl className="meta-list detail-meta">
        <div>
          <dt>run_id</dt>
          <dd>{record.run_id ?? "-"}</dd>
        </div>
        <div>
          <dt>decision_id</dt>
          <dd>{record.decision_id ?? "-"}</dd>
        </div>
        <div>
          <dt>origen</dt>
          <dd>{sourceTypeLabel(record.source_type)}</dd>
        </div>
        <div>
          <dt>resultado</dt>
          <dd>{outcomeLabel(record.outcome)}</dd>
        </div>
        <div>
          <dt>embedding</dt>
          <dd>{embeddingText}</dd>
        </div>
        <div>
          <dt>vector_id</dt>
          <dd>{record.vector_id ?? "-"}</dd>
        </div>
      </dl>
      {record.tags.length > 0 ? (
        <div className="memory-chip-row">
          {record.tags.slice(0, 10).map((tag) => (
            <span className="memory-chip subtle" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      {metricEntries.length > 0 ? (
        <div className="memory-metric-grid">
          {metricEntries.slice(0, 8).map(([metric, value]) => (
            <div className="memory-metric" key={metric}>
              <span>{metric}</span>
              <strong>{formatMetric(value)}</strong>
            </div>
          ))}
        </div>
      ) : null}
      <pre className="memory-content">{record.content}</pre>
      {record.source_path ? (
        <p className="memory-source-path">{record.source_path}</p>
      ) : null}
    </section>
  );
}
