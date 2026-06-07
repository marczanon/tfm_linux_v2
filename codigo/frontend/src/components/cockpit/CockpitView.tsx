import {
  Activity,
  ArrowRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Database,
  Eye,
  FileText,
  Gauge,
  LineChart,
  MessageSquareText,
  PackageCheck,
  Play,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";

import { confidenceText, formatDate, formatMetric, formatSeconds } from "../../lib/formatters";
import { llmStatusLabel, runStatusLabel } from "../../lib/labels";
import type {
  ApiRunJobStatus,
  ApiRunRequest,
  ArtifactRef,
  DatasetAdapterInfo,
  HealthResponse,
  LLMStatusResponse,
  RunIndexEntry,
  RunSnapshot,
  RunVisualizationData,
} from "../../types";
import type { AppView } from "../../types/ui";
import { StatusPill } from "../common/StatusPill";

export function CockpitView({
  activeJob,
  approvedRuns,
  canExecutePlan,
  completedRuns,
  executing,
  health,
  job,
  llmStatus,
  planning,
  request,
  runs,
  selectedAdapter,
  selectedArtifacts,
  selectedAuditReport,
  selectedReport,
  selectedReportDebate,
  selectedRunEntry,
  selectedSnapshot,
  selectedVisualization,
  loadingFocusRun,
  onExecute,
  onNavigate,
  onOpenRun,
  onRefreshLlm,
}: {
  activeJob: boolean;
  approvedRuns: number;
  canExecutePlan: boolean;
  completedRuns: number;
  executing: boolean;
  health: HealthResponse | null;
  job: ApiRunJobStatus | null;
  llmStatus: LLMStatusResponse | null;
  planning: boolean;
  request: ApiRunRequest;
  runs: RunIndexEntry[];
  selectedAdapter: DatasetAdapterInfo;
  selectedArtifacts: ArtifactRef[];
  selectedAuditReport: string | null;
  selectedReport: string | null;
  selectedReportDebate: string | null;
  selectedRunEntry: RunIndexEntry | null;
  selectedSnapshot: RunSnapshot | null;
  selectedVisualization: RunVisualizationData | null;
  loadingFocusRun: boolean;
  onExecute: () => void;
  onNavigate: (view: AppView) => void;
  onOpenRun: (runId: string, view: AppView) => void;
  onRefreshLlm: () => void;
}) {
  const latestRun = runs[0] ?? null;
  const focusRun = selectedRunEntry ?? latestRun;
  const focusSnapshot =
    selectedSnapshot?.run_id === focusRun?.run_id ? selectedSnapshot : null;
  const focusVisualization =
    selectedVisualization?.run_id === focusRun?.run_id ? selectedVisualization : null;
  const temporalRun = focusVisualization?.temporal_series?.runs[0] ?? null;
  const recommendation = focusVisualization?.agent_recommendation ?? null;
  const apiReady = health?.status === "ok";
  const llmReady = llmStatus?.available === true && llmStatus.model_available === true;
  const llmEnabled = request.use_llm;
  const jobLabel = job?.status ?? "sin job";
  const focusRunId = focusRun?.run_id ?? focusSnapshot?.run_id ?? null;
  const datasetLabel = focusRun?.dataset ?? request.dataset_id ?? selectedAdapter.dataset_id;
  const focusDetailReady = focusRunId !== null && focusSnapshot?.run_id === focusRunId;
  const focusArtifactCount = focusDetailReady
    ? selectedArtifacts.length
    : focusSnapshot?.n_artifacts ?? focusRun?.n_artifacts ?? null;
  const focusDecisionCount = focusRun?.n_decisions ?? focusSnapshot?.n_decisions ?? null;
  const reportReady = focusDetailReady && selectedReport !== null;
  const auditReady = focusDetailReady && selectedAuditReport !== null;
  const debateReady = focusDetailReady && selectedReportDebate !== null;
  const evidenceReady =
    reportReady ||
    auditReady ||
    debateReady ||
    (focusArtifactCount !== null && focusArtifactCount > 0);
  const healthState = temporalRun?.current_health_state ?? "unknown";
  const commandStateLabel = temporalRun
    ? healthStateLabel(temporalRun.current_health_state)
    : activeJob
      ? "Run activa"
      : focusRun
        ? "Run lista"
        : "Preparar";
  const readinessItems = [
    { label: "API", ready: apiReady },
    { label: "LLM", ready: !llmEnabled || llmReady, muted: !llmEnabled },
    { label: "Datos", ready: Boolean(datasetLabel) },
    { label: "Run", ready: Boolean(focusRunId) },
    { label: "Evidencia", ready: evidenceReady },
  ];

  return (
    <section className="cockpit-view">
      <section className={`cockpit-command state-${healthState}`} aria-label="Panel principal">
        <div className="cockpit-command-main">
          <p className="eyebrow">Command deck</p>
          <h2>{commandStateLabel}</h2>
          <div className="cockpit-command-run">
            <span>Run foco</span>
            <strong>{focusRunId ?? "Sin run"}</strong>
          </div>
          <div className="cockpit-chip-row">
            <StatusPill ok={apiReady} label={health?.status ?? "offline"} />
            <StatusPill
              ok={llmEnabled && llmReady}
              muted={!llmEnabled}
              label={llmEnabled ? llmStatusLabel(llmStatus) : "LLM off"}
            />
            <StatusPill
              ok={job?.status === "completed"}
              muted={!activeJob}
              label={jobLabel}
            />
          </div>
        </div>
        <div className="cockpit-command-meter" aria-label="Estado de salud industrial">
          <span>HI</span>
          <strong>{formatMetric(temporalRun?.current_health_index ?? null)}</strong>
          <small>Riesgo {formatMetric(temporalRun?.current_risk_index ?? null)}</small>
        </div>
        <div className="cockpit-readiness-row" aria-label="Preparacion operacional">
          {readinessItems.map((item) => (
            <span
              className={`${item.ready ? "ready" : ""} ${item.muted ? "muted" : ""}`}
              key={item.label}
              title={item.label}
            >
              {item.label}
            </span>
          ))}
        </div>
        <div className="cockpit-actions">
          <button className="primary-button" type="button" onClick={() => onNavigate("pipeline")}>
            <Play size={17} />
            Nueva run
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={onExecute}
            disabled={!canExecutePlan || planning || executing}
          >
            <ArrowRight size={17} />
            Ejecutar
          </button>
          <button className="icon-button" type="button" onClick={onRefreshLlm} title="Actualizar LLM" aria-label="Actualizar LLM">
            <Brain size={17} />
          </button>
        </div>
      </section>

      <section className="cockpit-signal-grid" aria-label="Senales principales">
        <CockpitSignal icon={<Server size={18} />} label="API" value={health?.status ?? "-"} tone={apiReady ? "ok" : "danger"} />
        <CockpitSignal icon={<Brain size={18} />} label="LLM" value={llmEnabled ? llmStatusLabel(llmStatus) : "off"} tone={llmEnabled ? (llmReady ? "ok" : "danger") : "muted"} />
        <CockpitSignal icon={<Database size={18} />} label="Dataset" value={datasetLabel} tone="data" />
        <CockpitSignal icon={<Activity size={18} />} label="Runs" value={`${completedRuns}/${runs.length}`} tone="data" />
        <CockpitSignal icon={<CheckCircle2 size={18} />} label="Aprobadas" value={approvedRuns.toString()} tone="ok" />
        <CockpitSignal icon={<Gauge size={18} />} label="Job" value={jobLabel} tone={activeJob ? "watch" : job?.status === "failed" ? "danger" : "muted"} />
      </section>

      <section className="cockpit-layout">
        <article className="cockpit-card cockpit-run-card cockpit-card-primary">
          <div className="cockpit-card-heading">
            <div>
              <p className="eyebrow">Run foco</p>
              <h3>{focusRunId ?? "Sin run seleccionada"}</h3>
            </div>
            {loadingFocusRun ? (
              <StatusPill ok={false} muted label="cargando" />
            ) : focusRun ? (
              <StatusPill
                ok={focusRun.approved === true}
                muted={focusRun.approved === null}
                label={runStatusLabel(focusRun.current_stage, focusRun.approved)}
              />
            ) : null}
          </div>

          <div className="cockpit-metric-row">
            <MetricTile label="F1" value={formatMetric(focusRun?.f1_score ?? null)} tone="ok" />
            <MetricTile label="Precision" value={formatMetric(focusRun?.precision ?? null)} tone="data" />
            <MetricTile label="Recall" value={formatMetric(focusRun?.recall ?? null)} tone="data" />
            <MetricTile label="FPR" value={formatMetric(focusRun?.false_positive_rate ?? null)} tone="warning" />
            <MetricTile label="Artefactos" value={focusArtifactCount?.toString() ?? "-"} />
            <MetricTile label="Decisiones" value={focusDecisionCount?.toString() ?? "-"} />
          </div>

          <div className="cockpit-run-footer">
            <span>{focusRun ? formatDate(focusRun.created_at) : selectedAdapter.display_name}</span>
            <div className="cockpit-inline-actions">
              {focusRunId ? (
                <>
                  <button className="secondary-button" type="button" onClick={() => onOpenRun(focusRunId, "visualization")}>
                    <Eye size={16} />
                    Visualizar
                  </button>
                  <button className="secondary-button" type="button" onClick={() => onOpenRun(focusRunId, "agents")}>
                    <Users size={16} />
                    Agentes
                  </button>
                </>
              ) : (
                <button className="secondary-button" type="button" onClick={() => onNavigate("pipeline")}>
                  <Play size={16} />
                  Preparar
                </button>
              )}
            </div>
          </div>
        </article>

        <article className="cockpit-card cockpit-health-card">
          <div className="cockpit-card-heading">
            <div>
              <p className="eyebrow">Salud temporal</p>
              <h3>
                {temporalRun
                  ? healthStateLabel(temporalRun.current_health_state)
                  : loadingFocusRun
                    ? "Cargando serie"
                    : "Sin serie cargada"}
              </h3>
            </div>
            <LineChart size={20} />
          </div>
          <div className={`cockpit-health-gauge ${loadingFocusRun ? "is-loading" : ""}`}>
            <div className={`cockpit-health-ring state-${temporalRun?.current_health_state ?? "unknown"}`}>
              <strong>{formatMetric(temporalRun?.current_health_index ?? null)}</strong>
              <span>HI</span>
            </div>
            <div className="cockpit-health-stats">
              <MetricTile label="Riesgo" value={formatMetric(temporalRun?.current_risk_index ?? null)} />
              <MetricTile label="Lead" value={formatSeconds(temporalRun?.first_persistent_alert_time_to_failure_seconds ?? temporalRun?.first_alert_time_to_failure_seconds ?? null)} />
              <MetricTile label="Alertas" value={temporalRun?.alert_episodes.toString() ?? "-"} />
            </div>
          </div>
        </article>

        <article className="cockpit-card cockpit-agent-card">
          <div className="cockpit-card-heading">
            <div>
              <p className="eyebrow">Recomendacion agentica</p>
              <h3>{recommendation?.available ? recommendation.title : "No cargada"}</h3>
            </div>
            <Brain size={20} />
          </div>
          {recommendation?.available ? (
            <>
              <div className="cockpit-agent-state">
                <StatusPill
                  ok={recommendation.status === "approved"}
                  muted={recommendation.status === "caution" || recommendation.status === "unavailable"}
                  label={recommendation.status}
                />
                <span>{confidenceText(recommendation.confidence)}</span>
              </div>
              <div className="cockpit-agent-action">
                <span>Accion</span>
                <strong>{compactActionText(recommendation.next_action ?? recommendation.summary)}</strong>
              </div>
            </>
          ) : (
            <p className="cockpit-empty-copy">
              {loadingFocusRun ? "Cargando recomendacion." : "Sin recomendacion."}
            </p>
          )}
        </article>

        <article className="cockpit-card cockpit-evidence-card">
          <div className="cockpit-card-heading">
            <div>
              <p className="eyebrow">Evidencia</p>
              <h3>{focusDetailReady ? "Trazabilidad lista" : loadingFocusRun ? "Cargando evidencia" : "Sin detalle cargado"}</h3>
            </div>
            <PackageCheck size={20} />
          </div>
          <div className="cockpit-evidence-grid">
            <EvidenceTile
              icon={<FileText size={17} />}
              label="Informe"
              available={reportReady}
              loading={loadingFocusRun}
            />
            <EvidenceTile
              icon={<ShieldCheck size={17} />}
              label="Auditoria"
              available={auditReady}
              loading={loadingFocusRun}
            />
            <EvidenceTile
              icon={<MessageSquareText size={17} />}
              label="Debate"
              available={debateReady}
              loading={loadingFocusRun}
            />
            <EvidenceTile
              icon={<PackageCheck size={17} />}
              label="Artefactos"
              available={focusArtifactCount !== null && focusArtifactCount > 0}
              loading={loadingFocusRun}
              value={focusArtifactCount?.toString()}
            />
          </div>
          {focusRunId ? (
            <button
              className="secondary-button cockpit-wide-action"
              type="button"
              onClick={() => onOpenRun(focusRunId, "pipeline")}
            >
              <FileText size={16} />
              Abrir evidencia
            </button>
          ) : null}
        </article>

        <article className="cockpit-card cockpit-recent-card">
          <div className="cockpit-card-heading">
            <div>
              <p className="eyebrow">Historial</p>
              <h3>Runs recientes</h3>
            </div>
            <BarChart3 size={20} />
          </div>
          {runs.length > 0 ? (
            <div className="cockpit-run-list">
              {runs.slice(0, 5).map((run) => (
                <button
                  className="cockpit-run-row"
                  key={run.run_id}
                  type="button"
                  onClick={() => onOpenRun(run.run_id, "visualization")}
                >
                  <span>{run.run_id}</span>
                  <strong>{formatMetric(run.f1_score)}</strong>
                </button>
              ))}
            </div>
          ) : (
            <p className="cockpit-empty-copy">Sin runs locales.</p>
          )}
        </article>
      </section>
    </section>
  );
}

function CockpitSignal({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "watch" | "danger" | "muted" | "data";
}) {
  return (
    <article className={`cockpit-signal tone-${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function MetricTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "data" | "warning";
}) {
  return (
    <div className={`cockpit-metric-tile tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvidenceTile({
  icon,
  label,
  available,
  loading,
  value,
}: {
  icon: ReactNode;
  label: string;
  available: boolean;
  loading: boolean;
  value?: string;
}) {
  const status = loading ? "cargando" : available ? value ?? "listo" : "sin datos";
  return (
    <div className={`cockpit-evidence-tile ${available ? "ready" : ""}`}>
      {icon}
      <span>{label}</span>
      <strong>{status}</strong>
    </div>
  );
}

function healthStateLabel(value: string): string {
  const labels: Record<string, string> = {
    nominal: "Nominal",
    watch: "Vigilancia",
    warning: "Alerta",
    critical: "Critico",
  };
  return labels[value] ?? value;
}

function compactActionText(value: string): string {
  const labels: Record<string, string> = {
    continue: "Continuar",
    review: "Revisar",
    stop: "Detener",
    investigate: "Investigar",
  };
  return labels[value] ?? value;
}
