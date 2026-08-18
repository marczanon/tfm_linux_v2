import type {
  HealthState,
  MonitoringTriggerEvent,
  ReplayAssetSpec,
  ReplayTick,
} from "../../types";
import { useEffect, useRef, useState } from "react";

const CHART_WIDTH = 960;
const CHART_HEIGHT = 260;
const PADDING = { top: 34, right: 22, bottom: 40, left: 62 };

export function MonitoringReplayChart({
  ticks,
  triggers,
  modeledAsset,
  totalTicks,
  executionCursor,
  inspectionCursor,
  selectedTriggerId,
  onInspect,
  onSelectTrigger,
}: {
  ticks: ReplayTick[];
  triggers: MonitoringTriggerEvent[];
  modeledAsset: ReplayAssetSpec | null;
  totalTicks: number;
  executionCursor: number | null;
  inspectionCursor: number | null;
  selectedTriggerId: string | null;
  onInspect: (cursor: number) => void;
  onSelectTrigger: (trigger: MonitoringTriggerEvent) => void;
}) {
  const points = modeledAsset
    ? ticks.flatMap((tick) => {
        const frame = tick.frames.find(
          (candidate) =>
            candidate.asset_id === modeledAsset.asset_id &&
            candidate.channel_id === modeledAsset.channel_id &&
            candidate.analysis_status === "modeled",
        );
        return frame && frame.analysis_status === "modeled"
          ? [{
              cursor: tick.cursor,
              gapDetected: frame.gap_detected,
              intervalSeconds: frame.interval_seconds,
              score: frame.score,
              threshold: frame.threshold,
            }]
          : [];
      })
    : [];
  const values = points.flatMap((point) => [point.score, point.threshold]);
  const rawMin = values.length ? Math.min(...values) : 0;
  const rawMax = values.length ? Math.max(...values) : 1;
  const yPadding = Math.max((rawMax - rawMin) * 0.16, Math.abs(rawMax) * 0.06, 0.01);
  const yMin = Math.min(0, rawMin - yPadding);
  const yMax = rawMax + yPadding;
  const drawableWidth = CHART_WIDTH - PADDING.left - PADDING.right;
  const drawableHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;
  const lastDomainCursor = Math.max(totalTicks - 1, executionCursor ?? 0, 1);
  const xFor = (cursor: number) =>
    PADDING.left + (Math.max(0, cursor) / lastDomainCursor) * drawableWidth;
  const yFor = (value: number) =>
    PADDING.top + ((yMax - value) / Math.max(yMax - yMin, Number.EPSILON)) * drawableHeight;
  const lineSegments = splitAtContinuityGaps(points);
  const gaps = points.filter((point) => point.gapDetected);
  const inspected = points.find((point) => point.cursor === inspectionCursor) ?? null;

  return (
    <div className="monitoring-chart-stack">
      <div className="monitoring-chart-heading">
        <div>
          <p className="eyebrow">Evidencia causal ejecutada</p>
          <h3>Score frente al umbral</h3>
        </div>
        <div className="monitoring-chart-legend" aria-label="Leyenda del gráfico">
          <span><i className="score" />Score</span>
          <span><i className="threshold" />Umbral</span>
          <span><i className="inspection" />Inspección</span>
          <span><i className="gap" />Hueco</span>
        </div>
      </div>

      <svg
        className="monitoring-score-chart"
        role="img"
        aria-label={chartAccessibleName(points.length, gaps.length, executionCursor, inspected)}
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      >
        <rect
          className="monitoring-chart-bg"
          x={PADDING.left}
          y={PADDING.top}
          width={drawableWidth}
          height={drawableHeight}
        />
        {[0, 0.5, 1].map((ratio) => {
          const y = PADDING.top + ratio * drawableHeight;
          const value = yMax - ratio * (yMax - yMin);
          return (
            <g key={ratio}>
              <line
                className="monitoring-chart-grid"
                x1={PADDING.left}
                x2={CHART_WIDTH - PADDING.right}
                y1={y}
                y2={y}
              />
              <text className="monitoring-chart-axis-label" x={PADDING.left - 9} y={y + 4}>
                {formatChartNumber(value)}
              </text>
            </g>
          );
        })}
        {executionCursor !== null && executionCursor < lastDomainCursor ? (
          <rect
            className="monitoring-chart-future"
            x={xFor(executionCursor)}
            y={PADDING.top}
            width={Math.max(0, CHART_WIDTH - PADDING.right - xFor(executionCursor))}
            height={drawableHeight}
          />
        ) : null}
        {gaps.map((point) => (
          <line
            className="monitoring-gap-line"
            key={`gap-${point.cursor}`}
            x1={xFor(point.cursor)}
            x2={xFor(point.cursor)}
            y1={PADDING.top}
            y2={PADDING.top + drawableHeight}
          />
        ))}
        {lineSegments.map((segment, index) => (
          <polyline
            className="monitoring-threshold-line"
            key={`threshold-${index}-${segment[0]?.cursor ?? 0}`}
            points={segment
              .map((point) => `${xFor(point.cursor)},${yFor(point.threshold)}`)
              .join(" ")}
          />
        ))}
        {lineSegments.map((segment, index) => (
          <polyline
            className="monitoring-score-line"
            key={`score-${index}-${segment[0]?.cursor ?? 0}`}
            points={segment
              .map((point) => `${xFor(point.cursor)},${yFor(point.score)}`)
              .join(" ")}
          />
        ))}
        {points.map((point) => (
          <circle
            className="monitoring-score-sample"
            cx={xFor(point.cursor)}
            cy={yFor(point.score)}
            key={`sample-${point.cursor}`}
            r={2.4}
          />
        ))}
        {executionCursor !== null ? (
          <line
            className="monitoring-execution-line"
            x1={xFor(executionCursor)}
            x2={xFor(executionCursor)}
            y1={PADDING.top}
            y2={PADDING.top + drawableHeight}
          />
        ) : null}
        {inspectionCursor !== null ? (
          <line
            className="monitoring-inspection-line"
            x1={xFor(inspectionCursor)}
            x2={xFor(inspectionCursor)}
            y1={PADDING.top}
            y2={PADDING.top + drawableHeight}
          />
        ) : null}
        {inspected ? (
          <circle
            className="monitoring-inspection-point"
            cx={xFor(inspected.cursor)}
            cy={yFor(inspected.score)}
            r={5}
          />
        ) : null}
        <text className="monitoring-chart-axis-caption" x={PADDING.left} y={CHART_HEIGHT - 10}>
          inicio
        </text>
        <text
          className="monitoring-chart-axis-caption end"
          x={CHART_WIDTH - PADDING.right}
          y={CHART_HEIGHT - 10}
        >
          snapshot {totalTicks || "—"}
        </text>
        {points.length === 0 ? (
          <text className="monitoring-chart-empty" x={CHART_WIDTH / 2} y={CHART_HEIGHT / 2}>
            Avanza el replay para revelar evidencia
          </text>
        ) : null}
      </svg>

      <MonitoringStateRail
        ticks={ticks}
        triggers={triggers}
        modeledAsset={modeledAsset}
        totalTicks={totalTicks}
        inspectionCursor={inspectionCursor}
        selectedTriggerId={selectedTriggerId}
        onInspect={onInspect}
        onSelectTrigger={onSelectTrigger}
      />
    </div>
  );
}

function MonitoringStateRail({
  ticks,
  triggers,
  modeledAsset,
  totalTicks,
  inspectionCursor,
  selectedTriggerId,
  onInspect,
  onSelectTrigger,
}: {
  ticks: ReplayTick[];
  triggers: MonitoringTriggerEvent[];
  modeledAsset: ReplayAssetSpec | null;
  totalTicks: number;
  inspectionCursor: number | null;
  selectedTriggerId: string | null;
  onInspect: (cursor: number) => void;
  onSelectTrigger: (trigger: MonitoringTriggerEvent) => void;
}) {
  const states = modeledAsset
    ? ticks.flatMap((tick) => {
        const frame = tick.frames.find(
          (candidate) =>
            candidate.asset_id === modeledAsset.asset_id &&
            candidate.channel_id === modeledAsset.channel_id &&
            candidate.analysis_status === "modeled",
        );
        return frame && frame.analysis_status === "modeled"
          ? [{
              cursor: tick.cursor,
              gapDetected: frame.gap_detected,
              intervalSeconds: frame.interval_seconds,
              state: frame.health_state,
            }]
          : [];
      })
    : [];
  const segments = buildStateSegments(states);
  const gaps = states.filter((entry) => entry.gapDetected);
  const denominator = Math.max(totalTicks - 1, 1);
  const railTrackRef = useRef<HTMLDivElement>(null);
  const [railTrackWidth, setRailTrackWidth] = useState(320);
  useEffect(() => {
    const track = railTrackRef.current;
    if (!track) {
      return;
    }
    const updateWidth = () => setRailTrackWidth(track.getBoundingClientRect().width);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(track);
    return () => observer.disconnect();
  }, []);
  const triggerGroups = groupTriggerMarkers(
    latestTriggerTransitions(triggers).filter((trigger) => trigger.cutoff_cursor !== null),
    denominator,
    railTrackWidth,
  );
  const linkedRunIds = linkedRunIdsByTrigger(triggers);

  return (
    <section className="monitoring-state-rail" aria-labelledby="monitoring-state-rail-title">
      <div className="monitoring-rail-heading">
        <h4 id="monitoring-state-rail-title">Estados y marcadores</h4>
        <span>Solo prefijo ejecutado</span>
      </div>
      <div className="monitoring-state-rail-track" ref={railTrackRef}>
        <div className="monitoring-state-segments">
          {segments.length ? (
            segments.map((segment) => (
              <button
                aria-label={`${healthStateLabel(segment.state)}, snapshots ${segment.start + 1} a ${segment.end + 1}`}
                className={`monitoring-state-segment state-${segment.state}`}
                key={`${segment.start}-${segment.state}`}
                onClick={() => onInspect(segment.end)}
                style={{
                  left: `${(segment.start / denominator) * 100}%`,
                  width: `${Math.max(((segment.end - segment.start + 1) / Math.max(totalTicks, 1)) * 100, 0.45)}%`,
                }}
                title={`${healthStateLabel(segment.state)} · ${segment.start + 1}–${segment.end + 1}`}
                type="button"
              />
            ))
          ) : (
            <span className="monitoring-state-rail-empty">Sin estados ejecutados</span>
          )}
        </div>
        {triggerGroups.map((group) => {
          const representative = group.triggers.find(
            (trigger) => trigger.trigger_id === selectedTriggerId,
          ) ?? preferredMarker(group.triggers);
          const selected = group.triggers.some((trigger) => trigger.trigger_id === selectedTriggerId);
          return (
            <button
              aria-label={triggerMarkerAccessibleName(
                group,
                representative,
                linkedRunIds.get(representative.trigger_id) ?? null,
              )}
              aria-pressed={selected}
              className={`monitoring-trigger-marker lifecycle-${representative.lifecycle_status}${group.triggers.length > 1 ? " grouped" : ""}`}
              data-lifecycle={representative.lifecycle_status}
              data-trigger-count={group.triggers.length}
              data-trigger-id={representative.trigger_id}
              key={`trigger-cursors-${group.startCursor}-${group.endCursor}`}
              onClick={() => onSelectTrigger(representative)}
              style={{ left: `${(group.positionCursor / denominator) * 100}%` }}
              title={triggerMarkerTitle(group, representative)}
              type="button"
            >
              <span aria-hidden="true" className="monitoring-trigger-marker-glyph">
                {triggerLifecycleGlyph(representative.lifecycle_status)}
              </span>
              {group.triggers.length > 1 ? (
                <span aria-hidden="true" className="monitoring-trigger-marker-count">{group.triggers.length}</span>
              ) : null}
            </button>
          );
        })}
        {gaps.map((gap) => (
          <button
            aria-label={`Hueco de continuidad antes del snapshot ${gap.cursor + 1}${gap.intervalSeconds === null ? "" : `, intervalo ${formatInterval(gap.intervalSeconds)}`}`}
            className="monitoring-gap-marker"
            key={`gap-${gap.cursor}`}
            onClick={() => onInspect(gap.cursor)}
            style={{ left: `${(gap.cursor / denominator) * 100}%` }}
            title="Hueco de continuidad"
            type="button"
          />
        ))}
        {inspectionCursor !== null ? (
          <span
            aria-hidden="true"
            className="monitoring-rail-inspection"
            style={{ left: `${(inspectionCursor / denominator) * 100}%` }}
          />
        ) : null}
      </div>
      <div className="monitoring-state-legend" aria-label="Leyenda de estados">
        {(["nominal", "watch", "warning", "critical"] as HealthState[]).map((state) => (
          <span key={state}><i className={`state-${state}`} />{healthStateLabel(state)}</span>
        ))}
        <span><i className="trigger" />Trigger</span>
        <span><i className="gap" />Hueco de continuidad</span>
      </div>
    </section>
  );
}

function buildStateSegments(
  entries: Array<{
    cursor: number;
    gapDetected: boolean;
    state: HealthState;
  }>,
): Array<{ start: number; end: number; state: HealthState }> {
  return entries.reduce<Array<{ start: number; end: number; state: HealthState }>>(
    (segments, entry) => {
      const previous = segments[segments.length - 1];
      if (
        previous &&
        !entry.gapDetected &&
        previous.state === entry.state &&
        previous.end + 1 === entry.cursor
      ) {
        previous.end = entry.cursor;
      } else {
        segments.push({ start: entry.cursor, end: entry.cursor, state: entry.state });
      }
      return segments;
    },
    [],
  );
}

function latestTriggerTransitions(
  triggers: MonitoringTriggerEvent[],
): MonitoringTriggerEvent[] {
  const latest = new Map<string, MonitoringTriggerEvent>();
  for (const trigger of triggers) {
    const current = latest.get(trigger.trigger_id);
    if (
      !current ||
      trigger.lifecycle_revision > current.lifecycle_revision ||
      (
        trigger.lifecycle_revision === current.lifecycle_revision &&
        trigger.sequence >= current.sequence
      )
    ) {
      latest.set(trigger.trigger_id, trigger);
    }
  }
  return [...latest.values()].sort(
    (left, right) => (left.cutoff_cursor ?? -1) - (right.cutoff_cursor ?? -1),
  );
}

interface TriggerMarkerGroup {
  startCursor: number;
  endCursor: number;
  positionCursor: number;
  triggers: MonitoringTriggerEvent[];
}

function groupTriggerMarkers(
  triggers: MonitoringTriggerEvent[],
  denominator: number,
  trackWidth: number,
): TriggerMarkerGroup[] {
  const ordered = [...triggers].sort(
    (left, right) =>
      (left.cutoff_cursor ?? 0) - (right.cutoff_cursor ?? 0) ||
      right.priority - left.priority ||
      right.sequence - left.sequence,
  );
  const minimumDistance = 48;
  return ordered.reduce<TriggerMarkerGroup[]>((groups, trigger) => {
    const cursor = trigger.cutoff_cursor ?? 0;
    const x = (cursor / denominator) * trackWidth;
    const previous = groups[groups.length - 1];
    const previousX = previous
      ? (previous.positionCursor / denominator) * trackWidth
      : Number.NEGATIVE_INFINITY;
    if (previous && x - previousX < minimumDistance) {
      previous.endCursor = Math.max(previous.endCursor, cursor);
      previous.positionCursor = (previous.startCursor + previous.endCursor) / 2;
      previous.triggers.push(trigger);
      previous.triggers.sort(
        (left, right) => right.priority - left.priority || right.sequence - left.sequence,
      );
    } else {
      groups.push({
        startCursor: cursor,
        endCursor: cursor,
        positionCursor: cursor,
        triggers: [trigger],
      });
    }
    return groups;
  }, []);
}

function preferredMarker(triggers: MonitoringTriggerEvent[]): MonitoringTriggerEvent {
  return triggers[0];
}

function triggerMarkerAccessibleName(
  group: TriggerMarkerGroup,
  representative: MonitoringTriggerEvent,
  linkedRunId: string | null,
): string {
  const { triggers } = group;
  const count = triggers.length === 1 ? "1 trigger" : `${triggers.length} triggers agrupados`;
  const location = group.startCursor === group.endCursor
    ? `snapshot ${group.startCursor + 1}`
    : `snapshots ${group.startCursor + 1} a ${group.endCursor + 1}`;
  const asset = representative.asset_id ? `, activo ${representative.asset_id}` : "";
  const run = linkedRunId ? "con run enlazada" : "sin run enlazada";
  return `${count} en ${location}: ${triggerTypeLabel(representative.trigger_type)}, ${triggerLifecycleLabel(representative.lifecycle_status)}${asset}, ${run}`;
}

function linkedRunIdsByTrigger(
  triggers: MonitoringTriggerEvent[],
): Map<string, string> {
  const linked = new Map<string, string>();
  for (const trigger of [...triggers].sort(
    (left, right) =>
      left.lifecycle_revision - right.lifecycle_revision ||
      left.sequence - right.sequence,
  )) {
    if (trigger.child_run_id) {
      linked.set(trigger.trigger_id, trigger.child_run_id);
    }
  }
  return linked;
}

function triggerMarkerTitle(
  group: TriggerMarkerGroup,
  representative: MonitoringTriggerEvent,
): string {
  const { triggers } = group;
  const prefix = triggers.length > 1 ? `${triggers.length} triggers · ` : "";
  return `${prefix}${triggerTypeLabel(representative.trigger_type)} · ${triggerLifecycleLabel(representative.lifecycle_status)}`;
}

function chartAccessibleName(
  pointCount: number,
  gapCount: number,
  executionCursor: number | null,
  inspected: { score: number; threshold: number } | null,
): string {
  const prefix = `Gráfico de score y umbral con ${pointCount} snapshots ejecutados.`;
  const gaps = gapCount === 0
    ? " Sin huecos de continuidad detectados."
    : ` ${gapCount} hueco${gapCount === 1 ? "" : "s"} de continuidad detectado${gapCount === 1 ? "" : "s"}.`;
  const cursor = executionCursor === null
    ? " La ejecución todavía no ha comenzado."
    : ` Cursor de ejecución en snapshot ${executionCursor + 1}.`;
  const inspection = inspected
    ? ` Punto inspeccionado: score ${formatChartNumber(inspected.score)} y umbral ${formatChartNumber(inspected.threshold)}.`
    : "";
  return `${prefix}${gaps}${cursor}${inspection}`;
}

type MonitoringChartPoint = {
  cursor: number;
  gapDetected: boolean;
  intervalSeconds: number | null;
  score: number;
  threshold: number;
};

function splitAtContinuityGaps(
  points: MonitoringChartPoint[],
): MonitoringChartPoint[][] {
  return points.reduce<MonitoringChartPoint[][]>((segments, point) => {
    const current = segments[segments.length - 1];
    if (!current || point.gapDetected) {
      segments.push([point]);
    } else {
      current.push(point);
    }
    return segments;
  }, []);
}

function formatInterval(seconds: number): string {
  if (seconds >= 60 && seconds % 60 === 0) {
    return `${seconds / 60} minutos`;
  }
  return `${formatChartNumber(seconds)} segundos`;
}

function formatChartNumber(value: number): string {
  if (Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.01)) {
    return value.toExponential(1);
  }
  return value.toFixed(2);
}

export function healthStateLabel(state: HealthState): string {
  return {
    nominal: "Nominal",
    watch: "Vigilancia",
    warning: "Advertencia",
    critical: "Crítico",
  }[state];
}

export function triggerTypeLabel(type: MonitoringTriggerEvent["trigger_type"]): string {
  return {
    preflight: "Preflight",
    periodic_review: "Revisión periódica",
    persistent_alert: "Alerta persistente",
    state_transition: "Cambio de estado",
    continuity_gap: "Hueco de continuidad",
    session_close: "Cierre de sesión",
    manual: "Revisión manual",
  }[type];
}

export function triggerLifecycleLabel(
  lifecycle: MonitoringTriggerEvent["lifecycle_status"],
): string {
  return {
    emitted: "Emitido",
    suppressed: "Suprimido",
    coalesced: "Agrupado",
    dispatched: "Despachado",
    running: "En ejecución",
    resolved: "Resuelto",
    failed: "Fallido",
  }[lifecycle];
}

export function triggerLifecycleGlyph(
  lifecycle: MonitoringTriggerEvent["lifecycle_status"],
): string {
  return {
    emitted: "◆",
    suppressed: "⊘",
    coalesced: "⇉",
    dispatched: "→",
    running: "●",
    resolved: "✓",
    failed: "×",
  }[lifecycle];
}
