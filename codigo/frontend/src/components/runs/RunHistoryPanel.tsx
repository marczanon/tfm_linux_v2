import { GitCompare, ListChecks, RefreshCcw } from "lucide-react";

import { RUN_STAGE_FILTERS } from "../../constants/pipeline";
import { approvalValue, emptyToNull } from "../../lib/forms";
import {
  formatComparisonMetric,
  metricLabel,
} from "../../lib/runComparison";
import { formatDate, formatMetric, formatSeconds } from "../../lib/formatters";
import { runStatusLabel } from "../../lib/labels";
import type {
  ArtifactRef,
  DatasetAdapterInfo,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunSnapshot,
} from "../../types";
import { StatusPill } from "../common/StatusPill";
import { RunDetailView } from "./RunDetailView";

export function RunHistoryPanel({
  adapters,
  comparingRuns,
  comparison,
  filters,
  loading,
  runs,
  selectedArtifacts,
  selectedAuditReport,
  selectedCompareRunIds,
  selectedReport,
  selectedReportDebate,
  selectedRunEntry,
  selectedRunId,
  selectedSnapshot,
  onCompare,
  onFilterChange,
  onResetFilters,
  onSelectRun,
  onToggleCompare,
}: {
  adapters: DatasetAdapterInfo[];
  comparingRuns: boolean;
  comparison: RunComparison | null;
  filters: RunFilters;
  loading: boolean;
  runs: RunIndexEntry[];
  selectedArtifacts: ArtifactRef[];
  selectedAuditReport: string | null;
  selectedCompareRunIds: string[];
  selectedReport: string | null;
  selectedReportDebate: string | null;
  selectedRunEntry: RunIndexEntry | null;
  selectedRunId: string | null;
  selectedSnapshot: RunSnapshot | null;
  onCompare: () => void;
  onFilterChange: (key: keyof RunFilters, value: string | boolean | null) => void;
  onResetFilters: () => void;
  onSelectRun: (runId: string) => void;
  onToggleCompare: (runId: string) => void;
}) {
  return (
    <details className="panel run-history-panel run-history-disclosure">
      <summary className="run-history-summary">
        <div>
          <p className="eyebrow">Registro</p>
          <h2>Runs locales</h2>
        </div>
        <div className="run-history-summary-meta">
          <StatusPill ok={runs.length > 0} muted={runs.length === 0} label={`${runs.length} runs`} />
          <StatusPill
            ok={selectedRunId !== null}
            muted={selectedRunId === null}
            label={selectedRunId ? "run foco" : "sin foco"}
          />
          <ListChecks size={20} />
        </div>
      </summary>

      <div className="run-history-content">
        <div className="panel-actions run-history-actions">
          <button
            className="icon-button"
            type="button"
            onClick={onResetFilters}
            title="Limpiar filtros"
            aria-label="Limpiar filtros"
          >
            <RefreshCcw size={17} />
          </button>
        </div>
        <RunFiltersView filters={filters} adapters={adapters} onChange={onFilterChange} />
        <RunsTable
          runs={runs}
          selectedRunId={selectedRunId}
          selectedCompareRunIds={selectedCompareRunIds}
          onSelectRun={onSelectRun}
          onToggleCompare={onToggleCompare}
        />
        <ComparisonView
          selectedCount={selectedCompareRunIds.length}
          comparison={comparison}
          loading={comparingRuns}
          onCompare={onCompare}
        />
        <RunDetailView
          entry={selectedRunEntry}
          snapshot={selectedSnapshot}
          artifacts={selectedArtifacts}
          report={selectedReport}
          auditReport={selectedAuditReport}
          reportDebate={selectedReportDebate}
          loading={loading}
        />
      </div>
    </details>
  );
}

function RunFiltersView({
  filters,
  adapters,
  onChange,
}: {
  filters: RunFilters;
  adapters: DatasetAdapterInfo[];
  onChange: (key: keyof RunFilters, value: string | boolean | null) => void;
}) {
  return (
    <div className="filter-grid" aria-label="Filtros de runs">
      <label className="field compact-field">
        <span>Dataset</span>
        <select
          value={filters.dataset ?? ""}
          onChange={(event) => onChange("dataset", emptyToNull(event.target.value))}
        >
          <option value="">Todos</option>
          {adapters.map((adapter) => (
            <option key={adapter.dataset_id} value={adapter.dataset_id}>
              {adapter.dataset_id}
            </option>
          ))}
        </select>
      </label>
      <label className="field compact-field">
        <span>Estado</span>
        <select
          value={filters.current_stage ?? ""}
          onChange={(event) => onChange("current_stage", emptyToNull(event.target.value))}
        >
          <option value="">Todos</option>
          {RUN_STAGE_FILTERS.map((stage) => (
            <option key={stage} value={stage}>
              {stage}
            </option>
          ))}
        </select>
      </label>
      <label className="field compact-field">
        <span>Aprobacion</span>
        <select
          value={filters.approved === null ? "" : String(filters.approved)}
          onChange={(event) => onChange("approved", approvalValue(event.target.value))}
        >
          <option value="">Todas</option>
          <option value="true">Aprobadas</option>
          <option value="false">No aprobadas</option>
        </select>
      </label>
    </div>
  );
}

function RunsTable({
  runs,
  selectedRunId,
  selectedCompareRunIds,
  onSelectRun,
  onToggleCompare,
}: {
  runs: RunIndexEntry[];
  selectedRunId: string | null;
  selectedCompareRunIds: string[];
  onSelectRun: (runId: string) => void;
  onToggleCompare: (runId: string) => void;
}) {
  if (runs.length === 0) {
    return <p className="empty-state">Sin runs registradas</p>;
  }

  return (
    <div className="table-wrap">
      <table className="runs-table">
        <thead>
          <tr>
            <th>Comp.</th>
            <th>Run</th>
            <th>Dataset</th>
            <th>Estado</th>
            <th>F1</th>
            <th>Fecha</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr className={run.run_id === selectedRunId ? "selected-row" : ""} key={run.run_id}>
              <td>
                <input
                  aria-label={`Seleccionar ${run.run_id} para comparar`}
                  checked={selectedCompareRunIds.includes(run.run_id)}
                  onChange={() => onToggleCompare(run.run_id)}
                  type="checkbox"
                />
              </td>
              <td>
                <button
                  className="link-button run-id"
                  type="button"
                  onClick={() => onSelectRun(run.run_id)}
                >
                  {run.run_id}
                </button>
              </td>
              <td>{run.dataset}</td>
              <td>
                <StatusPill
                  ok={run.approved === true}
                  label={runStatusLabel(run.current_stage, run.approved)}
                  muted={run.approved === null}
                />
              </td>
              <td>{formatMetric(run.f1_score)}</td>
              <td>{formatDate(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonView({
  selectedCount,
  comparison,
  loading,
  onCompare,
}: {
  selectedCount: number;
  comparison: RunComparison | null;
  loading: boolean;
  onCompare: () => void;
}) {
  const hasDegradation =
    comparison !== null && (comparison.degradation_metrics ?? []).length > 0;
  return (
    <section className="registry-section">
      <div className="section-heading">
        <div>
          <h3>Comparacion</h3>
          <p>{selectedCount} seleccionadas</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          disabled={selectedCount < 2 || loading}
          onClick={onCompare}
        >
          <GitCompare size={16} />
          {loading ? "Comparando" : "Comparar"}
        </button>
      </div>
      {comparison ? (
        <>
          {hasDegradation ? (
            <div className="comparison-focus">
              <div>
                <span>Perfil principal</span>
                <strong>Degradacion run-to-failure</strong>
              </div>
              <small>
                Prioriza primera alerta, lead time, falsas alarmas nominales y
                tendencia del score. Las metricas binarias quedan como apoyo.
              </small>
            </div>
          ) : null}
          {hasDegradation ? (
            <div className="comparison-grid comparison-grid-wide">
              {(comparison.degradation_metrics ?? []).map((metric) => (
                <ComparisonMetricCard metric={metric} key={metric.metric} />
              ))}
            </div>
          ) : null}
          <div className="comparison-grid">
            {comparison.metrics.map((metric) => (
              <ComparisonMetricCard metric={metric} key={metric.metric} />
            ))}
          </div>
          <ComparisonRowsTable rows={comparison.rows} />
        </>
      ) : null}
    </section>
  );
}

function ComparisonMetricCard({
  metric,
}: {
  metric: RunComparison["metrics"][number];
}) {
  return (
    <div className="comparison-card">
      <span>{metricLabel(metric.metric)}</span>
      <strong>{metric.best_run_id ?? "-"}</strong>
      <small>
        mejor {formatComparisonMetric(metric.metric, metric.best_value)} | peor{" "}
        {formatComparisonMetric(metric.metric, metric.worst_value)} | dif.{" "}
        {formatComparisonMetric(metric.metric, metric.spread)}
      </small>
    </div>
  );
}

function ComparisonRowsTable({ rows }: { rows: RunComparison["rows"] }) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Modelo</th>
            <th>Perfil</th>
            <th>Lead</th>
            <th>FAR nominal</th>
            <th>Tendencia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.run_id}>
              <td>{row.run_id}</td>
              <td>{row.model_name ?? "-"}</td>
              <td>
                <span className="comparison-profile">
                  {row.supervision_profile ?? "-"}
                </span>
                {row.label_source ? <small>{row.label_source}</small> : null}
              </td>
              <td>{formatSeconds(row.degradation_mean_lead_time_to_failure)}</td>
              <td>{formatMetric(row.degradation_mean_false_alarm_rate_nominal)}</td>
              <td>{formatMetric(row.degradation_mean_score_trend_spearman)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
