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
  const runtimeSummary = useMemo(
    () => buildMemoryRuntimeSummary(events, records),
    [events, records],
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
      value: runtimeSummary.retrievedIds.size,
      detail: "runtime actual",
      tone: "reusable",
    },
    {
      label: "usados",
      value: runtimeSummary.citedIds.size,
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
    <details className="runtime-block memory-panel memory-panel-disclosure">
      <summary className="memory-panel-summary">
        <div>
          <h3>Memoria agentica</h3>
          <p>{collection?.collection_name ?? target}</p>
        </div>
        <StatusPill
          ok={(collection?.n_records ?? 0) > 0}
          label={`${collection?.n_records ?? 0} recuerdos`}
          muted={(collection?.n_records ?? 0) === 0}
        />
      </summary>

      <div className="memory-panel-body">
        <div className="memory-cockpit-grid">
          <MemoryStat label="Total" value={collection?.n_records ?? 0} />
          <MemoryStat label="Reutilizables" value={collection?.n_reusable ?? 0} />
          <MemoryStat label="Datasets" value={collection?.datasets.length ?? 0} />
          <MemoryStat label="Excluidos" value={collection?.n_excluded ?? 0} tone="warning" />
        </div>

        <MemoryLifecycleStrip stages={lifecycleStages} />

        <MemoryRuntimeSummaryCard
          summary={runtimeSummary}
          onSelectRecord={onSelectRecord}
        />

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
            citedRecordIds={runtimeSummary.citedIds}
            ignoredRecordIds={runtimeSummary.ignoredIds}
            onSelectRecord={onSelectRecord}
          />
        )}

        <MemoryRecordDetail
          record={selectedRecord}
          curating={curating}
          onCurateRecord={onCurateRecord}
          onDeleteRecord={onDeleteRecord}
        />
      </div>
    </details>
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

function MemoryRuntimeSummaryCard({
  summary,
  onSelectRecord,
}: {
  summary: MemoryRuntimeSummary;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  const usageEntries = memoryUsageSummaryEntries(summary.usageCounts);
  return (
    <section className="memory-retrieval-summary">
      <div className="memory-retrieval-head">
        <div>
          <h4>Retrieval actual</h4>
          <p>{summary.latestContextId ?? "sin contexto activo"}</p>
        </div>
        <span className={`memory-quality-badge ${summary.signal.tone}`}>
          {summary.signal.label}
        </span>
      </div>

      <div className="memory-retrieval-grid">
        <MemoryStat label="Recuperados" value={summary.retrievedIds.size} />
        <MemoryStat label="Usados" value={summary.citedIds.size} />
        <MemoryStat label="Ignorados" value={summary.ignoredIds.size} />
        <MemoryStat label="Excluidos" value={summary.excludedIds.size} tone="warning" />
      </div>

      {summary.latestUsageSummary ? (
        <details className="compact-disclosure memory-summary-disclosure">
          <summary>Resumen de uso</summary>
          <p className="memory-usage-summary">
            {shortText(summary.latestUsageSummary, 260)}
          </p>
        </details>
      ) : null}

      <div className="memory-flow-meta">
        <span>
          sim media: <strong>{formatSimilarity(summary.averageSimilarity)}</strong>
        </span>
        <span>
          sim max: <strong>{formatSimilarity(summary.maxSimilarity)}</strong>
        </span>
        <span>
          cautelas: <strong>{summary.cautionCount}</strong>
        </span>
      </div>

      {usageEntries.length > 0 ? (
        <div className="memory-usage-strip">
          {usageEntries.map((entry) => (
            <span className={`memory-use-chip ${entry.tone}`} key={entry.usage}>
              {entry.label} · {entry.count}
            </span>
          ))}
        </div>
      ) : null}

      {summary.ignoredIds.size > 0 || summary.excludedIds.size > 0 ? (
        <div className="memory-chip-row">
          {Array.from(summary.ignoredIds).slice(0, 3).map((memoryId) => (
            <button
              className="memory-chip subtle memory-chip-button"
              key={`summary-ignored-${memoryId}`}
              type="button"
              onClick={() => onSelectRecord(memoryId)}
            >
              ignorado · {memoryId}
            </button>
          ))}
          {Array.from(summary.excludedIds).slice(0, 3).map((memoryId) => (
            <button
              className="memory-chip excluded memory-chip-button"
              key={`summary-excluded-${memoryId}`}
              type="button"
              onClick={() => onSelectRecord(memoryId)}
            >
              excluido · {memoryId}
            </button>
          ))}
        </div>
      ) : null}
    </section>
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
            const usageSummary = stringFromPayload(event.payload, "memory_usage_summary");
            const recordUses = memoryRecordUses(event);
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
                <p className="memory-event-summary">{event.summary}</p>
                {queryText || usageSummary ? (
                  <details className="compact-disclosure memory-flow-disclosure">
                    <summary>Consulta y uso</summary>
                    {queryText ? (
                      <p className="memory-query-excerpt">{shortText(queryText, 220)}</p>
                    ) : null}
                    {usageSummary ? (
                      <p className="memory-usage-summary">
                        {shortText(usageSummary, 260)}
                      </p>
                    ) : null}
                  </details>
                ) : null}
                {flowItems.length > 0 ? (
                  <div className="memory-flow-items">
                    {flowItems.map((item) => (
                      <MemoryFlowItemButton
                        item={item}
                        key={`${event.event_id}-${item.memoryRecordId}`}
                        onSelectRecord={onSelectRecord}
                      />
                    ))}
                  </div>
                ) : null}
                {recordUses.length > 0 ? (
                  <MemoryRecordUseList
                    uses={recordUses}
                    onSelectRecord={onSelectRecord}
                  />
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
  humanVerdict: string | null;
  outcome: string | null;
  tags: string[];
}

interface MemoryRecordUseView {
  memoryRecordId: string;
  usage: "followed" | "adapted" | "contradicted" | "ignored" | string;
  influenceSummary: string;
  riskMitigation: string | null;
}

function MemoryFlowItemButton({
  item,
  onSelectRecord,
}: {
  item: MemoryFlowItem;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  const signal = retrievalSignal(item);
  return (
    <button
      className="memory-flow-item"
      type="button"
      onClick={() => onSelectRecord(item.memoryRecordId)}
    >
      <span className="memory-flow-item-top">
        <strong>
          #{item.rank ?? "-"} · sim {formatSimilarity(item.similarity)}
        </strong>
        <em className={`memory-quality-badge ${signal.tone}`}>{signal.label}</em>
      </span>
      <span>{item.memoryRecordId}</span>
      <em>
        {roleLabel(item.memoryRole ?? "")} · {sourceTypeLabel(item.sourceType ?? "")} · {item.dataset ?? "-"}
      </em>
      {signal.reason ? <small>{signal.reason}</small> : null}
    </button>
  );
}

function MemoryRecordUseList({
  uses,
  onSelectRecord,
}: {
  uses: MemoryRecordUseView[];
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  return (
    <div className="memory-record-use-list">
      {uses.map((use) => {
        const label = memoryUseLabel(use.usage);
        return (
          <button
            className={`memory-record-use ${label.tone}`}
            key={`${use.memoryRecordId}-${use.usage}`}
            type="button"
            onClick={() => onSelectRecord(use.memoryRecordId)}
          >
            <span>{label.label}</span>
            <strong>{use.memoryRecordId}</strong>
            <em>{shortText(use.influenceSummary, 160)}</em>
            {use.riskMitigation ? <small>{shortText(use.riskMitigation, 160)}</small> : null}
          </button>
        );
      })}
    </div>
  );
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
        humanVerdict: stringValue(item.human_verdict),
        outcome: stringValue(item.outcome),
        tags: stringArrayFromUnknown(item.tags),
      };
    })
    .filter((item): item is MemoryFlowItem => item !== null);
}

interface MemoryRuntimeSummary {
  retrievedIds: Set<string>;
  citedIds: Set<string>;
  ignoredIds: Set<string>;
  excludedIds: Set<string>;
  usageCounts: Record<string, number>;
  latestUsageSummary: string | null;
  latestContextId: string | null;
  averageSimilarity: number | null;
  maxSimilarity: number | null;
  cautionCount: number;
  signal: { label: string; tone: "ok" | "warning" | "danger" | "muted" };
}

function buildMemoryRuntimeSummary(
  events: AgentRuntimeEvent[],
  records: MemoryRecordSummary[],
): MemoryRuntimeSummary {
  const retrievedIds = new Set<string>();
  const citedIds = new Set<string>();
  const ignoredIds = new Set<string>();
  const excludedIds = new Set(
    records
      .filter((record) => record.exclude_from_context || record.memory_role === "excluded")
      .map((record) => record.memory_record_id),
  );
  const usageCounts: Record<string, number> = {};
  const similarities: number[] = [];
  let latestUsageSummary: string | null = null;
  let latestContextId: string | null = null;
  let cautionCount = 0;
  let dangerCount = 0;

  for (const event of events) {
    if (event.memory_context_id) {
      latestContextId = event.memory_context_id;
    }
    for (const memoryId of eventRetrievedMemoryIds(event)) {
      retrievedIds.add(memoryId);
    }
    for (const memoryId of eventCitedMemoryIds(event)) {
      citedIds.add(memoryId);
    }
    for (const memoryId of eventIgnoredMemoryIds(event)) {
      ignoredIds.add(memoryId);
    }
    const usageSummary = stringFromPayload(event.payload, "memory_usage_summary");
    if (usageSummary) {
      latestUsageSummary = usageSummary;
    }
    for (const use of memoryRecordUses(event)) {
      usageCounts[use.usage] = (usageCounts[use.usage] ?? 0) + 1;
    }
    for (const item of memoryFlowItems(event)) {
      if (item.similarity !== null) {
        similarities.push(item.similarity);
      }
      const signal = retrievalSignal(item);
      if (signal.tone === "danger") {
        dangerCount += 1;
      } else if (signal.tone === "warning") {
        cautionCount += 1;
      }
    }
  }

  for (const memoryId of citedIds) {
    ignoredIds.delete(memoryId);
  }

  const averageSimilarity =
    similarities.length === 0
      ? null
      : similarities.reduce((total, value) => total + value, 0) / similarities.length;
  const maxSimilarity =
    similarities.length === 0 ? null : Math.max(...similarities);

  return {
    retrievedIds,
    citedIds,
    ignoredIds,
    excludedIds,
    usageCounts,
    latestUsageSummary,
    latestContextId,
    averageSimilarity,
    maxSimilarity,
    cautionCount: cautionCount + dangerCount,
    signal: memoryRuntimeSignal({
      retrievedCount: retrievedIds.size,
      citedCount: citedIds.size,
      cautionCount,
      dangerCount,
    }),
  };
}

function eventRetrievedMemoryIds(event: AgentRuntimeEvent): string[] {
  const explicitIds = stringArrayFromPayload(event.payload, "retrieved_memory_record_ids");
  if (explicitIds.length > 0) {
    return explicitIds;
  }
  const retrievalEvent = stringFromPayload(event.payload, "retrieval_event");
  if (retrievalEvent === "retrieval_returned") {
    return event.memory_record_ids;
  }
  return memoryFlowItems(event).map((item) => item.memoryRecordId);
}

function eventCitedMemoryIds(event: AgentRuntimeEvent): string[] {
  const explicitIds = stringArrayFromPayload(event.payload, "cited_memory_record_ids");
  if (explicitIds.length > 0) {
    return explicitIds;
  }
  const retrievalEvent = stringFromPayload(event.payload, "retrieval_event");
  if (retrievalEvent === "retrieval_used" || event.kind !== "memory_retrieval") {
    return event.memory_record_ids;
  }
  return [];
}

function eventIgnoredMemoryIds(event: AgentRuntimeEvent): string[] {
  return stringArrayFromPayload(event.payload, "ignored_memory_record_ids");
}

function memoryRecordUses(event: AgentRuntimeEvent): MemoryRecordUseView[] {
  const value = event.payload.memory_record_uses;
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .map((item) => {
      const memoryRecordId = stringValue(item.memory_record_id);
      const usage = stringValue(item.usage);
      const influenceSummary = stringValue(item.influence_summary);
      if (!memoryRecordId || !usage || !influenceSummary) {
        return null;
      }
      return {
        memoryRecordId,
        usage,
        influenceSummary,
        riskMitigation: stringValue(item.risk_mitigation),
      };
    })
    .filter((item): item is MemoryRecordUseView => item !== null);
}

function retrievalSignal(
  item: MemoryFlowItem,
): { label: string; tone: "ok" | "warning" | "danger" | "muted"; reason: string | null } {
  const tags = new Set(item.tags.map((tag) => tag.toLowerCase()));
  if (
    item.humanVerdict === "unsafe" ||
    item.humanVerdict === "incorrect" ||
    tags.has("manual_exclude") ||
    tags.has("exclude_candidate")
  ) {
    return {
      label: "revisar",
      tone: "danger",
      reason: verdictLabel(item.humanVerdict),
    };
  }
  if (item.similarity !== null && item.similarity < 0.05) {
    return {
      label: "sim baja",
      tone: "danger",
      reason: "similitud inferior a 0.05",
    };
  }
  if (item.similarity !== null && item.similarity < 0.2) {
    return {
      label: "cautela",
      tone: "warning",
      reason: "similitud inferior a 0.20",
    };
  }
  if (
    item.memoryRole === "warning" ||
    item.memoryRole === "negative_example" ||
    item.memoryRole === "boundary_case"
  ) {
    return {
      label: "cautela",
      tone: "warning",
      reason: roleLabel(item.memoryRole),
    };
  }
  if (item.sourceType === "memory_usage_audit") {
    return {
      label: "auditoria",
      tone: "warning",
      reason: "fuente de auditoria",
    };
  }
  if (
    item.humanVerdict === "partially_correct" ||
    item.humanVerdict === "needs_more_evidence" ||
    item.outcome === "overcorrected" ||
    item.outcome === "contradicted"
  ) {
    return {
      label: "cautela",
      tone: "warning",
      reason: `${verdictLabel(item.humanVerdict)} · ${outcomeLabel(item.outcome)}`,
    };
  }
  return {
    label: "estable",
    tone: item.similarity === null ? "muted" : "ok",
    reason: null,
  };
}

function memoryRuntimeSignal({
  retrievedCount,
  citedCount,
  cautionCount,
  dangerCount,
}: {
  retrievedCount: number;
  citedCount: number;
  cautionCount: number;
  dangerCount: number;
}): MemoryRuntimeSummary["signal"] {
  if (retrievedCount === 0) {
    return { label: "sin retrieval", tone: "muted" };
  }
  if (dangerCount > 0) {
    return { label: "riesgo visible", tone: "danger" };
  }
  if (citedCount === 0) {
    return { label: "recuperada sin uso", tone: "warning" };
  }
  if (cautionCount > 0) {
    return { label: "uso con cautela", tone: "warning" };
  }
  return { label: "uso trazable", tone: "ok" };
}

function memoryUseLabel(
  usage: string,
): { label: string; tone: "support" | "adapt" | "contradict" | "ignored" } {
  if (usage === "followed") {
    return { label: "apoya", tone: "support" };
  }
  if (usage === "adapted") {
    return { label: "adapta", tone: "adapt" };
  }
  if (usage === "contradicted") {
    return { label: "contradice", tone: "contradict" };
  }
  return { label: usage === "ignored" ? "ignora" : usage, tone: "ignored" };
}

function memoryUsageSummaryEntries(
  usageCounts: Record<string, number>,
): Array<{ usage: string; label: string; count: number; tone: "support" | "adapt" | "contradict" | "ignored" }> {
  return Object.entries(usageCounts).map(([usage, count]) => {
    const label = memoryUseLabel(usage);
    return {
      usage,
      label: label.label,
      count,
      tone: label.tone,
    };
  });
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => stringValue(item))
    .filter((item): item is string => item !== null);
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
  citedRecordIds,
  ignoredRecordIds,
  onSelectRecord,
}: {
  records: MemoryRecordSummary[];
  selectedRecordId: string | null;
  citedRecordIds: Set<string>;
  ignoredRecordIds: Set<string>;
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
            citedRecordIds.has(record.memory_record_id) ? "used" : ""
          } ${
            ignoredRecordIds.has(record.memory_record_id) ? "ignored" : ""
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
            {citedRecordIds.has(record.memory_record_id) ? <em>usado</em> : null}
            {ignoredRecordIds.has(record.memory_record_id) ? <em>ignorado</em> : null}
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
