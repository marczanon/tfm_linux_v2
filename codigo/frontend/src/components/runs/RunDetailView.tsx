import { BarChart3 } from "lucide-react";
import type { ReactNode } from "react";

import { StatusPill } from "../common/StatusPill";
import { RunEvidenceHub } from "../reports/ReportPanels";
import { formatMetric } from "../../lib/formatters";
import { runStatusLabel } from "../../lib/labels";
import type { ArtifactRef, RunIndexEntry, RunSnapshot } from "../../types";

export function RunDetailView({
  entry,
  snapshot,
  artifacts,
  report,
  auditReport,
  reportDebate,
  loading,
}: {
  entry: RunIndexEntry | null;
  snapshot: RunSnapshot | null;
  artifacts: ArtifactRef[];
  report: string | null;
  auditReport: string | null;
  reportDebate: string | null;
  loading: boolean;
}) {
  if (loading) {
    return <p className="empty-state compact-empty">Cargando run</p>;
  }
  if (snapshot === null) {
    return <p className="empty-state compact-empty">Selecciona una run</p>;
  }

  return (
    <section className="run-detail">
      <div className="section-heading">
        <div>
          <h3>{snapshot.run_id}</h3>
          <p>{snapshot.dataset}</p>
        </div>
        <StatusPill
          ok={snapshot.approved === true}
          label={runStatusLabel(snapshot.current_stage, snapshot.approved)}
          muted={snapshot.approved === null}
        />
      </div>

      <div className="metric-grid">
        <MetricCard icon={<BarChart3 size={16} />} label="Precision" value={entry?.precision ?? null} />
        <MetricCard icon={<BarChart3 size={16} />} label="Recall" value={entry?.recall ?? null} />
        <MetricCard icon={<BarChart3 size={16} />} label="F1" value={entry?.f1_score ?? null} />
        <MetricCard
          icon={<BarChart3 size={16} />}
          label="FPR"
          value={entry?.false_positive_rate ?? null}
        />
      </div>

      <RunEvidenceHub
        artifacts={artifacts}
        auditReport={auditReport}
        entry={entry}
        report={report}
        reportDebate={reportDebate}
        snapshot={snapshot}
      />
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: number | null;
}) {
  return (
    <div className="metric-card">
      {icon}
      <span>{label}</span>
      <strong>{formatMetric(value)}</strong>
    </div>
  );
}
