import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Activity, BarChart3, Box, Brain, GitCompare } from "lucide-react";

import { StatusPill } from "../common/StatusPill";
import { confidenceText, formatMetric, formatSeconds } from "../../lib/formatters";
import {
  formatComparisonMetric,
  metricLabel,
} from "../../lib/runComparison";
import type {
  AgentOperationalRecommendation,
  HealthState,
  ProjectionBoundary,
  ProjectionPoint,
  RunComparison,
  RunIndexEntry,
  RunVisualizationData,
  TemporalRunSeries,
  TemporalSeriesPoint,
  VisualizationMetric,
} from "../../types";

type VisualizationMode = "twoD" | "threeD";
type VisualSectionId = "state" | "metrics" | "agent" | "compare" | "temporal" | "map";

const IndustrialScene3D = lazy(() =>
  import("./IndustrialScene3D").then((module) => ({
    default: module.IndustrialScene3D,
  })),
);

export function VisualizationView({
  comparingRuns,
  comparison,
  runs,
  selectedCompareRunIds,
  selectedRunId,
  data,
  loading,
  onCompare,
  onSelectRun,
  onToggleCompare,
}: {
  comparingRuns: boolean;
  comparison: RunComparison | null;
  runs: RunIndexEntry[];
  selectedCompareRunIds: string[];
  selectedRunId: string | null;
  data: RunVisualizationData | null;
  loading: boolean;
  onCompare: () => void;
  onSelectRun: (runId: string) => void;
  onToggleCompare: (runId: string) => void;
}) {
  const [visualMode, setVisualMode] = useState<VisualizationMode>("twoD");
  const [activeVisualSection, setActiveVisualSection] =
    useState<VisualSectionId>("state");
  const temporalPanelRef = useRef<HTMLElement | null>(null);
  const temporalRun =
    data?.temporal_series?.available && data.temporal_series.runs.length
      ? data.temporal_series.runs[0]
      : null;
  const isRunToFailure = isRunToFailureVisualization(data);
  const showingIndustrialScene = visualMode === "threeD";
  const visualSections = visualSectionOptions(isRunToFailure);
  const visibleVisualSection = visualSections.some(
    (section) => section.id === activeVisualSection,
  )
    ? activeVisualSection
    : visualSections[0].id;

  function handleVisualModeChange(mode: VisualizationMode) {
    setVisualMode(mode);
    if (mode === "threeD") {
      setActiveVisualSection("temporal");
    }
  }

  useEffect(() => {
    if (!showingIndustrialScene || visibleVisualSection !== "temporal") {
      return;
    }
    window.setTimeout(() => {
      temporalPanelRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 0);
  }, [selectedRunId, showingIndustrialScene, visibleVisualSection]);

  return (
    <section className="visualization-workspace">
      <section className="panel visualization-control-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Visualizacion</p>
            <h2>Run analizada</h2>
          </div>
          <BarChart3 size={20} />
        </div>
        <label className="field">
          <span>Run</span>
          <select
            value={selectedRunId ?? ""}
            onChange={(event) => onSelectRun(event.target.value)}
          >
            <option value="" disabled>
              Selecciona una run
            </option>
            {runs.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {run.run_id}
              </option>
            ))}
          </select>
        </label>
        <div className="visualization-control-mode">
          <span>Vista</span>
          <VisualModeToggle mode={visualMode} onChange={handleVisualModeChange} />
        </div>
        {data ? (
          <dl className="meta-list detail-meta">
            <div>
              <dt>dataset</dt>
              <dd>{data.dataset}</dd>
            </div>
            <div>
              <dt>perfil</dt>
              <dd>{profileLabel(data.supervision_profile)}</dd>
            </div>
            <div>
              <dt>etiquetas</dt>
              <dd>{labelSourceLabel(data.label_source)}</dd>
            </div>
            <div>
              <dt>modelo</dt>
              <dd>{data.model_name ?? "-"}</dd>
            </div>
            <div>
              <dt>puntos</dt>
              <dd>
                {data.n_points_sampled}/{data.n_points_total}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="empty-state compact-empty">Selecciona una run con artefactos</p>
        )}
      </section>

      <VisualSectionTabs
        activeSection={visibleVisualSection}
        sections={visualSections}
        onChange={setActiveVisualSection}
      />

      {visibleVisualSection === "metrics" ? (
        <section className="panel visualization-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">
                {isRunToFailure ? "Metricas temporales" : "Metricas"}
              </p>
              <h2>{isRunToFailure ? "Degradacion" : "Rendimiento"}</h2>
            </div>
            <BarChart3 size={20} />
          </div>
          {loading ? (
            <p className="empty-state compact-empty">Cargando visualizacion</p>
          ) : data ? (
            <VisualizationMetricsPanel data={data} />
          ) : (
            <p className="empty-state compact-empty">Sin run seleccionada</p>
          )}
        </section>
      ) : null}

      {isRunToFailure && visibleVisualSection === "state" ? (
        <section className="panel motor-control-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Panel de control</p>
              <h2>Estado del motor</h2>
            </div>
            <Activity size={20} />
          </div>
          {loading ? (
            <p className="empty-state compact-empty">Preparando estado operacional</p>
          ) : temporalRun ? (
            <MotorControlPanel run={temporalRun} data={data!} />
          ) : (
            <p className="empty-state compact-empty">
              {data?.temporal_series?.warnings[0] ??
                "Sin serie temporal para construir estado del motor"}
            </p>
          )}
        </section>
      ) : null}

      {isRunToFailure && visibleVisualSection === "agent" ? (
        <section className="panel agent-recommendation-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recomendacion agentica</p>
              <h2>Lectura operacional</h2>
            </div>
            <Brain size={20} />
          </div>
          {loading ? (
            <p className="empty-state compact-empty">Recuperando decision agentica</p>
          ) : (
            <AgentRecommendationPanel
              recommendation={data?.agent_recommendation ?? null}
            />
          )}
        </section>
      ) : null}

      {visibleVisualSection === "compare" ? (
      <section className="panel visual-comparison-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Comparacion visual</p>
            <h2>Modelos y runs</h2>
          </div>
          <GitCompare size={20} />
        </div>
        <VisualRunComparisonPanel
          comparison={comparison}
          comparingRuns={comparingRuns}
          runs={runs}
          selectedCompareRunIds={selectedCompareRunIds}
          onCompare={onCompare}
          onToggleCompare={onToggleCompare}
        />
      </section>
      ) : null}

      {visibleVisualSection === "temporal" ? (
      <section className="panel temporal-panel" ref={temporalPanelRef}>
        <div className="panel-heading">
          <div>
            <p className="eyebrow">
              {showingIndustrialScene
                ? "Inspeccion 3D"
                : isRunToFailure
                  ? "Curva tecnica"
                  : "Degradacion"}
            </p>
            <h2>
              {showingIndustrialScene
                ? "Sala industrial"
                : isRunToFailure
                  ? "Ventanas y score"
                  : "Serie temporal"}
            </h2>
          </div>
          <div className="visual-mode-heading-actions">
            <VisualModeToggle mode={visualMode} onChange={handleVisualModeChange} />
            <Activity size={20} />
          </div>
        </div>
        {loading ? (
          <p className="empty-state compact-empty">
            {showingIndustrialScene ? "Preparando sala industrial" : "Preparando serie temporal"}
          </p>
        ) : temporalRun ? (
          showingIndustrialScene && data ? (
            <Suspense
              fallback={
                <p className="empty-state compact-empty">Preparando sala industrial</p>
              }
            >
              <IndustrialScene3D data={data} run={temporalRun} />
            </Suspense>
          ) : (
            <TemporalSeriesChart run={temporalRun} />
          )
        ) : (
          <p className="empty-state compact-empty">
            {data?.temporal_series?.warnings[0] ??
              "Sin metadatos temporales en predicciones"}
          </p>
        )}
        {data?.temporal_series?.available && data.temporal_series.n_runs_total > 1 ? (
          <p className="compact-note">
            Trayectoria 1/{data.temporal_series.n_runs_total}
          </p>
        ) : null}
      </section>
      ) : null}

      {visibleVisualSection === "map" ? (
      <section className="panel projection-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">
              {isRunToFailure ? "Diagnostico 2D" : "Espacio 2D"}
            </p>
            <h2>
              {isRunToFailure ? "Mapa de features" : "Agrupacion y anomalias"}
            </h2>
          </div>
          <Activity size={20} />
        </div>
        {loading ? (
          <p className="empty-state compact-empty">Calculando proyeccion</p>
        ) : data?.projection_available ? (
          <ProjectionScatter
            points={data.projection_points}
            boundary={data.projection_boundary}
          />
        ) : (
          <p className="empty-state compact-empty">
            {data?.warnings[0] ?? "Selecciona una run con features y predicciones"}
          </p>
        )}
        <ProjectionNotes
          explanation={data?.projection_explanation ?? null}
          boundaryNote={data?.projection_boundary?.note ?? null}
          warnings={data?.warnings ?? []}
        />
      </section>
      ) : null}
    </section>
  );
}

function visualSectionOptions(
  isRunToFailure: boolean,
): Array<{ id: VisualSectionId; label: string; detail: string }> {
  if (isRunToFailure) {
    return [
      { id: "state", label: "Estado", detail: "motor" },
      { id: "metrics", label: "Metricas", detail: "detalle" },
      { id: "agent", label: "Agente", detail: "decision" },
      { id: "compare", label: "Comparar", detail: "runs" },
      { id: "temporal", label: "Serie", detail: "2D/3D" },
      { id: "map", label: "Mapa", detail: "features" },
    ];
  }
  return [
    { id: "compare", label: "Comparar", detail: "runs" },
    { id: "temporal", label: "Serie", detail: "score" },
    { id: "map", label: "Mapa", detail: "features" },
    { id: "metrics", label: "Metricas", detail: "rendimiento" },
  ];
}

function VisualSectionTabs({
  activeSection,
  sections,
  onChange,
}: {
  activeSection: VisualSectionId;
  sections: Array<{ id: VisualSectionId; label: string; detail: string }>;
  onChange: (section: VisualSectionId) => void;
}) {
  return (
    <nav className="visual-section-tabs" aria-label="Secciones de visualizacion">
      {sections.map((section) => (
        <button
          className={section.id === activeSection ? "active" : ""}
          key={section.id}
          type="button"
          onClick={() => onChange(section.id)}
        >
          <span>{section.label}</span>
          <small>{section.detail}</small>
        </button>
      ))}
    </nav>
  );
}

function ProjectionNotes({
  explanation,
  boundaryNote,
  warnings,
}: {
  explanation: string | null;
  boundaryNote: string | null;
  warnings: string[];
}) {
  const noteCount = [explanation, boundaryNote].filter(Boolean).length + warnings.length;
  if (noteCount === 0) {
    return null;
  }

  return (
    <details className="compact-disclosure visual-notes-disclosure">
      <summary>Notas tecnicas · {noteCount}</summary>
      {explanation ? <p className="projection-note">{explanation}</p> : null}
      {boundaryNote ? <p className="projection-note">{boundaryNote}</p> : null}
      {warnings.length ? (
        <ul className="projection-warnings">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}

function VisualModeToggle({
  mode,
  onChange,
}: {
  mode: VisualizationMode;
  onChange: (mode: VisualizationMode) => void;
}) {
  return (
    <div className="visual-mode-toggle" aria-label="Modo de visualizacion" role="group">
      <button
        aria-pressed={mode === "twoD"}
        className={mode === "twoD" ? "active" : ""}
        onClick={() => onChange("twoD")}
        title="Vista 2D"
        type="button"
      >
        <BarChart3 size={15} />
        <span>2D</span>
      </button>
      <button
        aria-pressed={mode === "threeD"}
        className={mode === "threeD" ? "active" : ""}
        onClick={() => onChange("threeD")}
        title="Vista 3D"
        type="button"
      >
        <Box size={15} />
        <span>3D</span>
      </button>
    </div>
  );
}

function VisualizationMetricsPanel({ data }: { data: RunVisualizationData }) {
  const isRunToFailure = isRunToFailureVisualization(data);
  const primaryMetrics = data.primary_metrics.length ? data.primary_metrics : data.metrics;
  const auxiliaryMetrics = data.auxiliary_metrics.length ? data.auxiliary_metrics : [];

  if (isRunToFailure) {
    return (
      <div className="visual-metrics-stack">
        <VisualizationMetricCards metrics={primaryMetrics} />
        {auxiliaryMetrics.some((metric) => metric.value !== null) ? (
          <section className="auxiliary-metrics">
            <div>
              <strong>Metricas binarias auxiliares</strong>
              <span>
                {labelSourceLabel(data.label_source)} | {data.label_granularity ?? "-"}
              </span>
            </div>
            <MetricBars metrics={auxiliaryMetrics} compact />
          </section>
        ) : null}
      </div>
    );
  }

  return <MetricBars metrics={primaryMetrics} />;
}

function VisualizationMetricCards({ metrics }: { metrics: VisualizationMetric[] }) {
  const visible = metrics.filter((metric) => metric.value !== null);
  if (visible.length === 0) {
    return <p className="empty-state compact-empty">Sin metricas principales</p>;
  }

  return (
    <div className="visual-metric-grid">
      {visible.map((metric) => (
        <div className="visual-metric-card" key={metric.name}>
          <span>{metric.label}</span>
          <strong>{formatVisualizationMetric(metric)}</strong>
          <em>{metric.higher_is_better ? "mejor alto" : "mejor bajo"}</em>
          {metric.note ? <small>{metric.note}</small> : null}
        </div>
      ))}
    </div>
  );
}

function MotorControlPanel({
  run,
  data,
}: {
  run: TemporalRunSeries;
  data: RunVisualizationData;
}) {
  const health = run.current_health_index ?? 0;
  const risk = run.current_risk_index ?? 0;
  const persistentAlertX = run.first_persistent_alert_x;
  const leadTime =
    run.first_persistent_alert_time_to_failure_seconds !== null
      ? formatSeconds(run.first_persistent_alert_time_to_failure_seconds)
      : run.first_alert_time_to_failure_seconds !== null
        ? formatSeconds(run.first_alert_time_to_failure_seconds)
        : "no disponible";
  const failureContext =
    run.failure_reference === "historic_replay" && run.failure_x !== null
      ? "El fallo mostrado procede del replay historico del dataset; no es una prediccion RUL del modelo."
      : "Esta run no trae un marcador de fallo historico suficiente para calcular RUL.";
  const alertContext =
    persistentAlertX !== null
      ? `Aviso sostenido: al menos ${run.persistent_alert_min_windows} ventanas consecutivas en alerta o critico.`
      : `Sin aviso sostenido de ${run.persistent_alert_min_windows} ventanas; los colores intensos pueden ser picos aislados.`;
  const sourceWarning =
    data.label_source && data.label_source !== "official"
      ? `Etiquetas ${labelSourceLabel(data.label_source).toLowerCase()}; no son ground truth oficial por ventana.`
      : "Etiquetas oficiales.";

  return (
    <div className="motor-control-grid">
      <div className={`motor-status-block ${run.current_health_state}`}>
        <span>estado actual</span>
        <strong>{healthStateLabel(run.current_health_state)}</strong>
        <p>{run.current_state_reason}</p>
      </div>
      <div className="motor-meter-block">
        <StateMeter label="salud" value={health} state={run.current_health_state} />
        <StateMeter label="riesgo" value={risk} state={run.current_health_state} invert />
      </div>
      <div className="motor-kpi-grid">
        <div>
          <span>primer pico</span>
          <strong>{formatMetric(run.first_alert_x)}</strong>
        </div>
        <div>
          <span>aviso sostenido</span>
          <strong>{formatMetric(persistentAlertX)}</strong>
        </div>
        <div>
          <span>lead time sost.</span>
          <strong>{leadTime}</strong>
        </div>
        <div>
          <span>alertas</span>
          <strong>{run.alert_points}</strong>
        </div>
        <div>
          <span>picos aislados</span>
          <strong>{run.isolated_alert_points}</strong>
        </div>
        <div>
          <span>racha maxima</span>
          <strong>{run.longest_alert_streak}</strong>
        </div>
      </div>
      <OperationalFlow data={data} run={run} />
      <WindowStateStrip run={run} />
      <details className="compact-disclosure motor-context-note">
        <summary>Contexto tecnico · 3</summary>
        <p>{alertContext}</p>
        <p>{failureContext}</p>
        <p>{sourceWarning}</p>
      </details>
    </div>
  );
}

function AgentRecommendationPanel({
  recommendation,
}: {
  recommendation: AgentOperationalRecommendation | null;
}) {
  if (recommendation === null) {
    return <p className="empty-state compact-empty">Sin recomendacion disponible</p>;
  }

  const available = recommendation.available;
  const source = recommendation.source_agent ?? "evaluator";
  const statusOk = recommendation.status === "approved";
  const muted =
    !available ||
    recommendation.status === "unavailable" ||
    recommendation.status === "caution";
  const detailCount =
    recommendation.evidence_refs.length +
    recommendation.tool_names.length +
    recommendation.guardrail_checks.length +
    recommendation.limitations.length +
    recommendation.debate_points.length +
    (recommendation.modeler_summary ? 1 : 0);

  return (
    <div className={`agent-recommendation ${recommendation.status}`}>
      <div className="agent-recommendation-header">
        <span className="agent-recommendation-icon">
          <Brain size={18} />
        </span>
        <div>
          <span>
            {source} | {recommendation.decision_id ?? "-"}
          </span>
          <strong>{recommendation.title}</strong>
        </div>
        <StatusPill
          ok={statusOk}
          muted={muted}
          label={recommendationStatusLabel(recommendation.status)}
        />
      </div>

      <p className="agent-recommendation-summary">{recommendation.summary}</p>

      <dl className="recommendation-meta">
        <div>
          <dt>confianza</dt>
          <dd>{confidenceText(recommendation.confidence)}</dd>
        </div>
        <div>
          <dt>siguiente</dt>
          <dd>{recommendation.next_action ?? "-"}</dd>
        </div>
        <div>
          <dt>herramientas</dt>
          <dd>{recommendation.tool_names.length}</dd>
        </div>
        <div>
          <dt>evidencias</dt>
          <dd>{recommendation.evidence_refs.length}</dd>
        </div>
      </dl>

      {detailCount > 0 ? (
        <details className="compact-disclosure recommendation-detail-drawer">
          <summary>Evidencia y debate · {detailCount}</summary>
          {recommendation.modeler_summary ? (
            <section className="recommendation-block">
              <h3>Estrategia modelador</h3>
              <p>{recommendation.modeler_summary}</p>
            </section>
          ) : null}

          <div className="recommendation-columns">
            <RecommendationList
              title="Evidencia"
              items={recommendation.evidence_refs}
              compact
            />
            <RecommendationList title="Herramientas" items={recommendation.tool_names} compact />
            <RecommendationList
              title="Guardarrailes"
              items={recommendation.guardrail_checks}
            />
            <RecommendationList title="Cautelas" items={recommendation.limitations} />
            <RecommendationList title="Debate" items={recommendation.debate_points} />
          </div>
        </details>
      ) : null}
    </div>
  );
}

function VisualRunComparisonPanel({
  comparison,
  comparingRuns,
  runs,
  selectedCompareRunIds,
  onCompare,
  onToggleCompare,
}: {
  comparison: RunComparison | null;
  comparingRuns: boolean;
  runs: RunIndexEntry[];
  selectedCompareRunIds: string[];
  onCompare: () => void;
  onToggleCompare: (runId: string) => void;
}) {
  const visibleRuns = runs.slice(0, 12);
  const metrics = comparison ? comparisonMetricsForVisual(comparison) : [];

  return (
    <div className="visual-comparison">
      <div className="visual-compare-toolbar">
        <div className="visual-run-selector" aria-label="Seleccion de runs para comparar">
          {visibleRuns.map((run) => {
            const selected = selectedCompareRunIds.includes(run.run_id);
            return (
              <button
                className={`visual-run-chip ${selected ? "active" : ""}`}
                key={run.run_id}
                type="button"
                onClick={() => onToggleCompare(run.run_id)}
              >
                <span>{run.dataset} · {run.current_stage}</span>
                <strong>{run.run_id}</strong>
              </button>
            );
          })}
        </div>
        <button
          className="secondary-button visual-compare-button"
          type="button"
          disabled={selectedCompareRunIds.length < 2 || comparingRuns}
          onClick={onCompare}
        >
          <GitCompare size={16} />
          {comparingRuns ? "Comparando" : "Comparar"}
        </button>
      </div>

      {comparison === null ? (
        <p className="empty-state compact-empty">
          Selecciona al menos dos runs para comparar modelos y perfiles.
        </p>
      ) : metrics.length === 0 ? (
        <p className="empty-state compact-empty">La comparacion no trae metricas visualizables</p>
      ) : (
        <>
          <div className="visual-comparison-focus">
            <div>
              <span>{comparison.rows.length} runs</span>
              <strong>{comparisonHasDegradation(comparison) ? "Run-to-failure" : "Metricas binarias"}</strong>
            </div>
            <small>
              {comparisonHasDegradation(comparison)
                ? "Prioriza degradacion sostenida, lead time, falsas alarmas nominales y tendencia."
                : "Compara rendimiento binario con F1, precision, recall y falsas alarmas."}
            </small>
          </div>

          <div className="visual-comparison-best-grid">
            {metrics.slice(0, 4).map((metric) => (
              <article className="visual-best-card" key={metric.metric}>
                <span>{metric.label}</span>
                <strong>{metric.bestRunId ?? "-"}</strong>
                <small>
                  mejor {formatComparisonMetric(metric.metric, metric.bestValue)} · peor{" "}
                  {formatComparisonMetric(metric.metric, metric.worstValue)}
                </small>
              </article>
            ))}
          </div>

          <div className="visual-run-matrix">
            {comparison.rows.map((row) => (
              <article className="visual-run-card" key={row.run_id}>
                <div className="visual-run-card-head">
                  <div>
                    <strong>{row.run_id}</strong>
                    <span>{row.model_name ?? "-"} · {row.dataset}</span>
                  </div>
                  <em>{profileLabel(row.supervision_profile)}</em>
                </div>
                <div className="visual-run-bars">
                  {metrics.slice(0, 5).map((metric) => (
                    <VisualComparisonBar
                      key={`${row.run_id}-${metric.metric}`}
                      metric={metric}
                      row={row}
                    />
                  ))}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function VisualComparisonBar({
  metric,
  row,
}: {
  metric: VisualComparisonMetric;
  row: RunComparison["rows"][number];
}) {
  const value = comparisonRowMetricValue(row, metric.metric);
  const width = value === null ? 0 : normalizedComparisonWidth(value, metric.values, metric.higherIsBetter);
  const best = row.run_id === metric.bestRunId;
  return (
    <div className={`visual-run-bar ${best ? "best" : ""}`}>
      <div>
        <span>{metric.label}</span>
        <strong>{formatComparisonMetric(metric.metric, value)}</strong>
      </div>
      <div className="visual-run-bar-track">
        <span style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function RecommendationList({
  compact = false,
  items,
  title,
}: {
  compact?: boolean;
  items: string[];
  title: string;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <section className={`recommendation-block ${compact ? "compact" : ""}`}>
      <h3>{title}</h3>
      <ul className="recommendation-list">
        {items.map((item) => (
          <li key={`${title}-${item}`}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function StateMeter({
  label,
  value,
  state,
  invert = false,
}: {
  label: string;
  value: number;
  state: HealthState;
  invert?: boolean;
}) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div className="state-meter">
      <div>
        <span>{label}</span>
        <strong>{formatMetric(value)}</strong>
      </div>
      <div className={`state-meter-track ${state} ${invert ? "risk" : "health"}`}>
        <span style={{ width: `${bounded}%` }} />
      </div>
    </div>
  );
}

function OperationalFlow({
  data,
  run,
}: {
  data: RunVisualizationData;
  run: TemporalRunSeries;
}) {
  const steps = [
    {
      label: "ventanas",
      value: `${run.n_points_total}`,
      detail: temporalAxisLabel(run.x_axis),
    },
    {
      label: "detector",
      value: data.model_name ?? "-",
      detail: "score de anomalia",
    },
    {
      label: "estado",
      value: healthStateLabel(run.current_health_state),
      detail: `${run.longest_alert_streak} ventanas seguidas max.`,
    },
    {
      label: "agente",
      value: "Qwen/LLM",
      detail: "interpreta evidencia",
    },
  ];

  return (
    <div className="operational-flow" aria-label="Flujo de lectura operacional">
      {steps.map((step, index) => (
        <div className="operational-step" key={step.label}>
          <span>{step.label}</span>
          <strong>{step.value}</strong>
          <em>{step.detail}</em>
          {index < steps.length - 1 ? <i aria-hidden="true" /> : null}
        </div>
      ))}
    </div>
  );
}

function WindowStateStrip({ run }: { run: TemporalRunSeries }) {
  const points = run.points.slice(0, 180);
  return (
    <div className="window-state-strip">
      <div>
        <strong>ventanas procesadas</strong>
        <span>
          {run.n_points_sampled}/{run.n_points_total} visibles | {run.alert_episodes} episodios
        </span>
      </div>
      <div className="window-strip-track" aria-label="Estados por ventana">
        {points.map((point) => (
          <span
            className={`window-strip-segment ${point.health_state}`}
            key={point.window_id}
            title={`${point.window_id} | ${healthStateLabel(point.health_state)} | salud ${formatMetric(point.health_index)} | riesgo ${formatMetric(point.risk_index)}`}
          />
        ))}
      </div>
      <div className="window-strip-legend">
        <span><i className="nominal" /> nominal</span>
        <span><i className="watch" /> vigilancia</span>
        <span><i className="warning" /> alerta</span>
        <span><i className="critical" /> critico</span>
      </div>
    </div>
  );
}

function MetricBars({
  metrics,
  compact = false,
}: {
  metrics: VisualizationMetric[];
  compact?: boolean;
}) {
  const visible = metrics.filter((metric) => metric.value !== null);
  if (visible.length === 0) {
    return <p className="empty-state compact-empty">Sin metricas numericas</p>;
  }

  return (
    <div className={`metric-bars ${compact ? "compact" : ""}`}>
      {visible.map((metric) => {
        const value = metric.value ?? 0;
        const width = `${Math.max(0, Math.min(1, value)) * 100}%`;
        return (
          <div className="metric-bar-row" key={metric.name}>
            <div>
              <strong>{metric.label}</strong>
              <span>{metric.higher_is_better ? "mayor es mejor" : "menor es mejor"}</span>
            </div>
            <div className="metric-bar-track">
              <span style={{ width }} />
            </div>
            <em>{formatMetric(metric.value)}</em>
          </div>
        );
      })}
    </div>
  );
}

function TemporalSeriesChart({ run }: { run: TemporalRunSeries }) {
  if (run.points.length === 0) {
    return <p className="empty-state compact-empty">Sin puntos temporales</p>;
  }

  const width = 760;
  const height = 330;
  const padding = 38;
  const xValues = [
    ...run.points.map((point) => point.x),
    ...(run.first_alert_x !== null ? [run.first_alert_x] : []),
    ...(run.first_persistent_alert_x !== null ? [run.first_persistent_alert_x] : []),
    ...(run.failure_x !== null ? [run.failure_x] : []),
  ];
  const yValues = [
    ...run.points.map((point) => point.anomaly_score),
    ...(run.threshold !== null ? [run.threshold] : []),
  ];
  const xScale = scaleFor(xValues, padding, width - padding);
  const yScale = scaleFor(yValues, height - padding, padding);
  const path = run.points
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command} ${xScale(point.x).toFixed(2)} ${yScale(point.anomaly_score).toFixed(2)}`;
    })
    .join(" ");
  const thresholdY = run.threshold === null ? null : yScale(run.threshold);
  const stateBands = run.points.map((point, index) => {
    const currentX = xScale(point.x);
    const left =
      index === 0
        ? padding
        : (xScale(run.points[index - 1].x) + currentX) / 2;
    const right =
      index === run.points.length - 1
        ? width - padding
        : (currentX + xScale(run.points[index + 1].x)) / 2;
    return {
      key: `${point.window_id}-band`,
      state: point.health_state,
      x: Math.max(padding, left),
      width: Math.max(1, Math.min(width - padding, right) - Math.max(padding, left)),
    };
  });

  return (
    <div className="temporal-wrap">
      <dl className="temporal-summary">
        <div>
          <dt>run</dt>
          <dd>{run.run_id}</dd>
        </div>
        <div>
          <dt>estado actual</dt>
          <dd>
            <TemporalHealthBadge state={run.current_health_state} />
          </dd>
        </div>
        <div>
          <dt>salud</dt>
          <dd>{formatMetric(run.current_health_index)}</dd>
        </div>
        <div>
          <dt>riesgo</dt>
          <dd>{formatMetric(run.current_risk_index)}</dd>
        </div>
        <div>
          <dt>eje</dt>
          <dd>{temporalAxisLabel(run.x_axis)}</dd>
        </div>
        <div>
          <dt>primer pico</dt>
          <dd>{formatMetric(run.first_alert_x)}</dd>
        </div>
        <div>
          <dt>aviso sost.</dt>
          <dd>{formatMetric(run.first_persistent_alert_x)}</dd>
        </div>
        <div>
          <dt>lead sost.</dt>
          <dd>{formatSeconds(run.first_persistent_alert_time_to_failure_seconds)}</dd>
        </div>
        <div>
          <dt>racha max.</dt>
          <dd>{run.longest_alert_streak}</dd>
        </div>
      </dl>
      <details className="compact-disclosure temporal-note-details">
        <summary>Motivo estado</summary>
        <p className="temporal-state-note">{run.current_state_reason}</p>
      </details>
      <svg
        className="temporal-score-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Serie temporal de degradacion"
      >
        <rect className="temporal-bg" x="0" y="0" width={width} height={height} rx="8" />
        {stateBands.map((band) => (
          <rect
            className={`temporal-state-band ${band.state}`}
            height={height - padding * 2}
            key={band.key}
            width={band.width}
            x={band.x}
            y={padding}
          />
        ))}
        <line className="temporal-axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="temporal-axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        {thresholdY !== null ? (
          <line
            className="temporal-threshold"
            x1={padding}
            x2={width - padding}
            y1={thresholdY}
            y2={thresholdY}
          />
        ) : null}
        {run.failure_x !== null ? (
          <line
            className="temporal-failure"
            x1={xScale(run.failure_x)}
            x2={xScale(run.failure_x)}
            y1={padding}
            y2={height - padding}
          />
        ) : null}
        <path className="temporal-line" d={path} />
        {run.first_alert_x !== null ? (
          <circle
            className="temporal-first-alert"
            cx={xScale(run.first_alert_x)}
            cy={yScale(scoreAtX(run, run.first_alert_x))}
            r="6"
          >
            <title>
              {`Primer pico | x ${formatMetric(run.first_alert_x)} | lead ${formatSeconds(run.first_alert_time_to_failure_seconds)}`}
            </title>
          </circle>
        ) : null}
        {run.first_persistent_alert_x !== null ? (
          <circle
            className="temporal-persistent-alert"
            cx={xScale(run.first_persistent_alert_x)}
            cy={yScale(scoreAtX(run, run.first_persistent_alert_x))}
            r="6"
          >
            <title>
              {`Aviso sostenido | x ${formatMetric(run.first_persistent_alert_x)} | lead ${formatSeconds(run.first_persistent_alert_time_to_failure_seconds)}`}
            </title>
          </circle>
        ) : null}
        {run.points.map((point) => (
          <circle
            className={`temporal-point ${point.health_state}`}
            cx={xScale(point.x)}
            cy={yScale(point.anomaly_score)}
            key={point.window_id}
            r={point.health_state === "critical" ? 4.2 : point.health_state === "warning" ? 3.7 : 2.5}
          >
            <title>
              {`${point.window_id} | ${healthStateLabel(point.health_state)} | salud ${formatMetric(point.health_index)} | score ${formatMetric(point.anomaly_score)} | x ${formatMetric(point.x)}`}
            </title>
          </circle>
        ))}
      </svg>
      <div className="temporal-legend">
        <span><i className="legend-score" /> score</span>
        <span><i className="legend-threshold" /> umbral</span>
        <span><i className="legend-first-alert" /> primer pico</span>
        <span><i className="legend-persistent-alert" /> aviso sostenido</span>
        <span><i className="legend-failure" /> fallo</span>
        <span><i className="legend-health-warning" /> warning</span>
        <span><i className="legend-health-critical" /> critico</span>
      </div>
      <TemporalHealthIndexChart run={run} />
      <TemporalEpisodeRail run={run} />
    </div>
  );
}

function TemporalHealthIndexChart({ run }: { run: TemporalRunSeries }) {
  const points = run.points.filter(
    (point) => point.health_index !== null,
  );
  if (points.length < 2) {
    return null;
  }

  const width = 760;
  const height = 150;
  const paddingX = 38;
  const paddingY = 24;
  const xValues = [
    ...run.points.map((point) => point.x),
    ...(run.first_alert_x !== null ? [run.first_alert_x] : []),
    ...(run.first_persistent_alert_x !== null ? [run.first_persistent_alert_x] : []),
    ...(run.failure_x !== null ? [run.failure_x] : []),
  ];
  const xScale = scaleFor(xValues, paddingX, width - paddingX);
  const yScale = (value: number) =>
    paddingY + (100 - Math.max(0, Math.min(100, value))) / 100 * (height - paddingY * 2);
  const path = points
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command} ${xScale(point.x).toFixed(2)} ${yScale(point.health_index ?? 0).toFixed(2)}`;
    })
    .join(" ");

  return (
    <section className="temporal-health-chart">
      <div className="temporal-chart-heading">
        <strong>Health Index</strong>
        <span>0 degradado · 100 sano</span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Health Index por ventana"
      >
        <rect className="temporal-bg" x="0" y="0" width={width} height={height} rx="8" />
        {[25, 50, 75].map((value) => (
          <line
            className="temporal-health-grid"
            key={value}
            x1={paddingX}
            x2={width - paddingX}
            y1={yScale(value)}
            y2={yScale(value)}
          />
        ))}
        <line className="temporal-axis" x1={paddingX} x2={width - paddingX} y1={height - paddingY} y2={height - paddingY} />
        <line className="temporal-axis" x1={paddingX} x2={paddingX} y1={paddingY} y2={height - paddingY} />
        <path className="temporal-health-line" d={path} />
        {points.map((point) => (
          <circle
            className={`temporal-health-point ${point.health_state}`}
            cx={xScale(point.x)}
            cy={yScale(point.health_index ?? 0)}
            key={`${point.window_id}-health`}
            r={point.health_state === "critical" ? 3.8 : point.health_state === "warning" ? 3.4 : 2.5}
          >
            <title>
              {`${point.window_id} | HI ${formatMetric(point.health_index)} | ${healthStateLabel(point.health_state)} | x ${formatMetric(point.x)}`}
            </title>
          </circle>
        ))}
      </svg>
    </section>
  );
}

function TemporalEpisodeRail({ run }: { run: TemporalRunSeries }) {
  const episodes = alertEpisodes(run.points);
  const markers = temporalMarkers(run);
  const domain = temporalDomain(run);
  const position = (value: number) => boundedPercent(value, domain);

  return (
    <section className="temporal-episode-rail">
      <div className="temporal-chart-heading">
        <strong>Episodios de alerta</strong>
        <span>{episodes.length} tramos · {run.isolated_alert_points} picos aislados</span>
      </div>
      <div className="temporal-episode-track" aria-label="Episodios y marcadores temporales">
        {episodes.length === 0 ? <span className="temporal-empty-track" /> : null}
        {episodes.map((episode) => {
          const left = position(episode.startX);
          const right = position(episode.endX);
          return (
            <span
              className={`temporal-episode ${episode.critical ? "critical" : "warning"}`}
              key={episode.id}
              style={{
                left: `${left}%`,
                width: `${Math.max(1.8, right - left)}%`,
              }}
              title={`${episode.points} ventanas | ${episode.critical ? "critico" : "alerta"} | x ${formatMetric(episode.startX)}-${formatMetric(episode.endX)}`}
            />
          );
        })}
        {markers.map((marker) => (
          <span
            className={`temporal-rail-marker ${marker.kind}`}
            key={marker.kind}
            style={{ left: `${position(marker.x)}%` }}
            title={`${marker.label} | x ${formatMetric(marker.x)}`}
          />
        ))}
      </div>
      <div className="temporal-episode-legend">
        <span><i className="warning" /> episodio alerta</span>
        <span><i className="critical" /> episodio critico</span>
        <span><i className="marker first" /> primer pico</span>
        <span><i className="marker persistent" /> sostenido</span>
        <span><i className="marker failure" /> fallo</span>
      </div>
    </section>
  );
}

function TemporalHealthBadge({ state }: { state: HealthState }) {
  return <span className={`temporal-health-badge ${state}`}>{healthStateLabel(state)}</span>;
}

function scoreAtX(run: TemporalRunSeries, x: number): number {
  let closest = run.points[0];
  for (const point of run.points) {
    if (Math.abs(point.x - x) < Math.abs(closest.x - x)) {
      closest = point;
    }
  }
  return closest.anomaly_score;
}

interface AlertEpisode {
  id: string;
  startX: number;
  endX: number;
  points: number;
  critical: boolean;
}

function alertEpisodes(points: TemporalSeriesPoint[]): AlertEpisode[] {
  const episodes: AlertEpisode[] = [];
  let current: AlertEpisode | null = null;
  for (const point of points) {
    const alert = point.health_state === "warning" || point.health_state === "critical";
    if (!alert) {
      current = null;
      continue;
    }
    if (current === null) {
      current = {
        id: `${point.window_id}-episode`,
        startX: point.x,
        endX: point.x,
        points: 1,
        critical: point.health_state === "critical",
      };
      episodes.push(current);
      continue;
    }
    current.endX = point.x;
    current.points += 1;
    current.critical = current.critical || point.health_state === "critical";
  }
  return episodes;
}

function temporalMarkers(run: TemporalRunSeries): Array<{
  kind: "first" | "persistent" | "failure";
  label: string;
  x: number;
}> {
  return [
    run.first_alert_x === null
      ? null
      : { kind: "first" as const, label: "primer pico", x: run.first_alert_x },
    run.first_persistent_alert_x === null
      ? null
      : { kind: "persistent" as const, label: "aviso sostenido", x: run.first_persistent_alert_x },
    run.failure_x === null
      ? null
      : { kind: "failure" as const, label: "fallo", x: run.failure_x },
  ].filter((item): item is { kind: "first" | "persistent" | "failure"; label: string; x: number } => item !== null);
}

function temporalDomain(run: TemporalRunSeries): { min: number; max: number } {
  const values = [
    ...run.points.map((point) => point.x),
    ...(run.first_alert_x !== null ? [run.first_alert_x] : []),
    ...(run.first_persistent_alert_x !== null ? [run.first_persistent_alert_x] : []),
    ...(run.failure_x !== null ? [run.failure_x] : []),
  ];
  if (values.length === 0) {
    return { min: 0, max: 1 };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  return min === max ? { min: min - 0.5, max: max + 0.5 } : { min, max };
}

function boundedPercent(value: number, domain: { min: number; max: number }): number {
  const raw = ((value - domain.min) / (domain.max - domain.min)) * 100;
  return Math.max(0, Math.min(100, raw));
}

interface VisualComparisonMetric {
  metric: string;
  label: string;
  higherIsBetter: boolean;
  bestRunId: string | null;
  bestValue: number | null;
  worstValue: number | null;
  values: number[];
}

function comparisonMetricsForVisual(comparison: RunComparison): VisualComparisonMetric[] {
  const sourceMetrics = comparisonHasDegradation(comparison)
    ? comparison.degradation_metrics
    : comparison.metrics;
  return sourceMetrics
    .map((metric) => {
      const values = comparison.rows
        .map((row) => comparisonRowMetricValue(row, metric.metric))
        .filter((value): value is number => value !== null);
      return {
        metric: metric.metric,
        label: metricLabel(metric.metric),
        higherIsBetter: metric.higher_is_better,
        bestRunId: metric.best_run_id,
        bestValue: metric.best_value,
        worstValue: metric.worst_value,
        values,
      };
    })
    .filter((metric) => metric.values.length > 0);
}

function comparisonHasDegradation(comparison: RunComparison): boolean {
  return (comparison.degradation_metrics ?? []).length > 0;
}

function comparisonRowMetricValue(
  row: RunComparison["rows"][number],
  metric: string,
): number | null {
  const values: Record<string, number | null | undefined> = {
    precision: row.precision,
    recall: row.recall,
    f1_score: row.f1_score,
    false_positive_rate: row.false_positive_rate,
    degradation_detected_before_failure_rate: row.degradation_detected_before_failure_rate,
    degradation_mean_lead_time_to_failure: row.degradation_mean_lead_time_to_failure,
    degradation_mean_false_alarm_rate_nominal: row.degradation_mean_false_alarm_rate_nominal,
    degradation_mean_score_trend_spearman: row.degradation_mean_score_trend_spearman,
    degradation_missed_runs: row.degradation_missed_runs,
    degradation_mean_initial_final_separation: row.degradation_mean_initial_final_separation,
  };
  return values[metric] ?? null;
}

function normalizedComparisonWidth(
  value: number,
  values: number[],
  higherIsBetter: boolean,
): number {
  if (values.length === 0) {
    return 0;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return 100;
  }
  const normalized = (value - min) / (max - min);
  const oriented = higherIsBetter ? normalized : 1 - normalized;
  return Math.max(8, Math.min(100, oriented * 100));
}

function temporalAxisLabel(axis: TemporalRunSeries["x_axis"]): string {
  if (axis === "relative_life") {
    return "vida relativa";
  }
  if (axis === "time_since_start_seconds") {
    return "segundos desde inicio";
  }
  return "indice de ventana";
}

function healthStateLabel(state: HealthState): string {
  const labels: Record<HealthState, string> = {
    nominal: "nominal",
    watch: "vigilancia",
    warning: "alerta",
    critical: "critico",
  };
  return labels[state];
}

function recommendationStatusLabel(status: AgentOperationalRecommendation["status"]): string {
  const labels: Record<AgentOperationalRecommendation["status"], string> = {
    approved: "aprobada",
    caution: "cautela",
    needs_revision: "revision",
    blocked: "bloqueada",
    unavailable: "sin decision",
  };
  return labels[status];
}

function ProjectionScatter({
  points,
  boundary,
}: {
  points: ProjectionPoint[];
  boundary: ProjectionBoundary | null;
}) {
  if (points.length === 0) {
    return <p className="empty-state compact-empty">Sin puntos proyectados</p>;
  }

  const width = 760;
  const height = 440;
  const padding = 34;
  const xs = [
    ...points.map((point) => point.x),
    ...(boundary ? [boundary.center_x - boundary.radius_x, boundary.center_x + boundary.radius_x] : []),
  ];
  const ys = [
    ...points.map((point) => point.y),
    ...(boundary ? [boundary.center_y - boundary.radius_y, boundary.center_y + boundary.radius_y] : []),
  ];
  const xScale = scaleFor(xs, padding, width - padding);
  const yScale = scaleFor(ys, height - padding, padding);
  const hasPredictions = points.some((point) => point.predicted_anomaly !== null);

  return (
    <div className="scatter-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Proyeccion 2D de ventanas">
        <rect className="scatter-bg" x="0" y="0" width={width} height={height} rx="8" />
        <line className="scatter-axis" x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} />
        <line className="scatter-axis" x1={padding} x2={padding} y1={padding} y2={height - padding} />
        {boundary ? (
          <ellipse
            className="scatter-boundary"
            cx={xScale(boundary.center_x)}
            cy={yScale(boundary.center_y)}
            rx={Math.abs(xScale(boundary.center_x + boundary.radius_x) - xScale(boundary.center_x))}
            ry={Math.abs(yScale(boundary.center_y + boundary.radius_y) - yScale(boundary.center_y))}
          />
        ) : null}
        {points.map((point) => {
          const anomaly = point.predicted_anomaly === 1;
          return (
            <circle
              className={anomaly ? "scatter-point anomaly" : "scatter-point normal"}
              cx={xScale(point.x)}
              cy={yScale(point.y)}
              key={point.window_id}
              r={anomaly ? 4.2 : 2.7}
            >
              <title>
                {`${point.window_id} | ${point.label ?? "-"} | score ${formatMetric(point.anomaly_score)}`}
              </title>
            </circle>
          );
        })}
      </svg>
      <div className="scatter-legend">
        <span>
          <i className="legend-normal" />
          {hasPredictions ? "normal/prediccion 0" : "ventanas proyectadas"}
        </span>
        {hasPredictions ? (
          <>
            <span><i className="legend-anomaly" /> anomalia detectada</span>
            <span><i className="legend-boundary" /> frontera aproximada</span>
          </>
        ) : null}
      </div>
    </div>
  );
}

function isRunToFailureVisualization(data: RunVisualizationData | null): boolean {
  if (data === null) {
    return false;
  }
  return (
    data.supervision_profile === "run_to_failure_degradation" ||
    data.metric_families.includes("run_to_failure_degradation")
  );
}

function profileLabel(profile: string | null): string {
  if (profile === "run_to_failure_degradation") {
    return "run-to-failure";
  }
  if (profile === "binary_fault_classification") {
    return "binario";
  }
  return profile ?? "-";
}

function labelSourceLabel(source: string | null): string {
  const labels: Record<string, string> = {
    official: "Oficial",
    temporal_proxy: "Proxy temporal",
    synthetic: "Sintetica",
    none: "Sin etiquetas",
  };
  return source === null ? "-" : labels[source] ?? source;
}

function formatVisualizationMetric(metric: VisualizationMetric): string {
  if (metric.value === null) {
    return "-";
  }
  if (metric.value_kind === "seconds") {
    return formatSeconds(metric.value);
  }
  if (metric.value_kind === "count") {
    return new Intl.NumberFormat("es-ES", {
      maximumFractionDigits: 0,
    }).format(metric.value);
  }
  if (metric.value_kind === "ratio" && metric.value >= 0 && metric.value <= 1) {
    return `${new Intl.NumberFormat("es-ES", {
      maximumFractionDigits: 1,
    }).format(metric.value * 100)}%`;
  }
  return formatMetric(metric.value);
}

function scaleFor(values: number[], outputMin: number, outputMax: number) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return (value: number) => outputMin + ((value - min) / span) * (outputMax - outputMin);
}
