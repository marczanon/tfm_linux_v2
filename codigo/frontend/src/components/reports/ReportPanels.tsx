import {
  Archive,
  FileSearch,
  FileText,
  MessageSquare,
  Package,
  ShieldCheck,
} from "lucide-react";
import type { ReactNode } from "react";

import { StatusPill } from "../common/StatusPill";
import { formatDate, formatMetric } from "../../lib/formatters";
import type { ArtifactRef, RunIndexEntry, RunSnapshot } from "../../types";
import { MarkdownDocumentPreview } from "./ReportDocument";

type EvidenceHubVariant = "focus" | "detail";

export function RunEvidenceHub({
  artifacts,
  auditReport,
  entry,
  loading = false,
  report,
  reportDebate,
  snapshot,
  variant = "detail",
}: {
  artifacts: ArtifactRef[];
  auditReport: string | null;
  entry?: RunIndexEntry | null;
  loading?: boolean;
  report: string | null;
  reportDebate: string | null;
  snapshot: RunSnapshot | null;
  variant?: EvidenceHubVariant;
}) {
  const reportReady = report !== null;
  const auditReady = auditReport !== null;
  const debateReady = reportDebate !== null;
  const evidencePackReady = hasEvidencePack(snapshot, artifacts);
  const artifactsReady = artifacts.length > 0;
  const readyCount = [
    reportReady,
    auditReady,
    debateReady,
    evidencePackReady,
    artifactsReady,
  ].filter(Boolean).length;
  const shellClass =
    variant === "focus"
      ? "panel run-evidence-hub focus-evidence-panel"
      : "registry-section run-evidence-hub";

  if (loading) {
    return (
      <section className={shellClass}>
        <EvidenceHubHeading
          title="Centro de evidencia"
          subtitle="Cargando run"
          readyCount={0}
        />
        <p className="empty-state compact-empty">Cargando evidencia</p>
      </section>
    );
  }

  if (snapshot === null) {
    return (
      <section className={shellClass}>
        <EvidenceHubHeading
          title="Centro de evidencia"
          subtitle="Sin run seleccionada"
          readyCount={0}
        />
        <p className="empty-state compact-empty">Selecciona una run para auditarla</p>
      </section>
    );
  }

  return (
    <section className={shellClass}>
      <EvidenceHubHeading
        title="Centro de evidencia"
        subtitle={snapshot.run_id}
        readyCount={readyCount}
      />

      <div className="evidence-signal-grid" aria-label="Estado de evidencia">
        <EvidenceSignal
          icon={<FileText size={18} />}
          label="Informe"
          value={reportReady ? "listo" : "pendiente"}
          ready={reportReady}
        />
        <EvidenceSignal
          icon={<ShieldCheck size={18} />}
          label="Auditoria"
          value={auditReady ? "lista" : "pendiente"}
          ready={auditReady}
        />
        <EvidenceSignal
          icon={<MessageSquare size={18} />}
          label="Debate"
          value={debateReady ? "listo" : "pendiente"}
          ready={debateReady}
        />
        <EvidenceSignal
          icon={<Archive size={18} />}
          label="Pack"
          value={evidencePackReady ? "persistido" : "sin pack"}
          ready={evidencePackReady}
        />
        <EvidenceSignal
          icon={<Package size={18} />}
          label="Artefactos"
          value={artifacts.length.toString()}
          ready={artifactsReady}
        />
      </div>

      <div className="evidence-fact-strip" aria-label="Resumen auditado de run">
        <EvidenceFact label="Dataset" value={snapshot.dataset} />
        <EvidenceFact label="Fecha" value={formatDate(snapshot.created_at)} />
        <EvidenceFact label="F1" value={formatMetric(entry?.f1_score ?? null)} />
        <EvidenceFact label="Decisiones" value={snapshot.n_decisions.toString()} />
        <EvidenceFact label="Errores" value={snapshot.n_errors.toString()} />
      </div>

      <div className="evidence-document-grid">
        <EvidenceDocumentDisclosure
          available={reportReady}
          icon={<FileText size={18} />}
          title="Informe final"
          statusLabel={reportReady ? "generado" : "pendiente"}
        >
          <MarkdownDocumentPreview
            document={report}
            emptyText="Sin informe disponible"
            kicker="Documento de cierre"
          />
        </EvidenceDocumentDisclosure>

        <EvidenceDocumentDisclosure
          available={auditReady}
          icon={<FileSearch size={18} />}
          title="Auditoria"
          statusLabel={auditReady ? "disponible" : "pendiente"}
        >
          <MarkdownDocumentPreview
            document={auditReport}
            emptyText="Sin auditoria de ejecucion disponible"
            kicker="Auditoria humana"
          />
        </EvidenceDocumentDisclosure>

        <EvidenceDocumentDisclosure
          available={debateReady}
          icon={<MessageSquare size={18} />}
          title="Debate agentico"
          statusLabel={debateReady ? "disponible" : "pendiente"}
        >
          <MarkdownDocumentPreview
            document={reportDebate}
            emptyText="Sin debate controlado disponible"
            kicker="Debate agentico"
          />
        </EvidenceDocumentDisclosure>

        <EvidenceDocumentDisclosure
          available={artifactsReady}
          icon={<Package size={18} />}
          title="Artefactos"
          statusLabel={artifactsReady ? `${artifacts.length}` : "vacio"}
        >
          <ArtifactSummary artifacts={artifacts} />
          <ArtifactList artifacts={artifacts} />
        </EvidenceDocumentDisclosure>
      </div>
    </section>
  );
}

export function FinalReportPanel({
  report,
  snapshot,
}: {
  report: string | null;
  snapshot: RunSnapshot;
}) {
  return (
    <section className="registry-section final-report-section">
      <div className="section-heading">
        <div>
          <h3>Informe final</h3>
          <p>{report ? "Cierre analitico generado" : "Pendiente de generacion"}</p>
        </div>
        <div className="report-heading-actions">
          <StatusPill
            ok={report !== null && snapshot.approved === true}
            label={report ? "generado" : "pendiente"}
            muted={report === null}
          />
          <FileText size={18} />
        </div>
      </div>
      {report ? (
        <details className="compact-disclosure report-disclosure">
          <summary>Documento tecnico</summary>
          <ReportPreview report={report} />
        </details>
      ) : (
        <ReportPreview report={report} />
      )}
    </section>
  );
}

export function ExecutionAuditPanel({ auditReport }: { auditReport: string | null }) {
  return (
    <section className="registry-section audit-report-section">
      <div className="section-heading">
        <div>
          <h3>Auditoria de ejecucion</h3>
          <p>{auditReport ? "Resumen operativo de la run" : "Auditoria no disponible"}</p>
        </div>
        <div className="report-heading-actions audit-heading-actions">
          <StatusPill
            ok={auditReport !== null}
            label={auditReport ? "disponible" : "pendiente"}
            muted={auditReport === null}
          />
          <FileSearch size={18} />
        </div>
      </div>
      {auditReport ? (
        <details className="compact-disclosure report-disclosure">
          <summary>Auditoria completa</summary>
          <MarkdownDocumentPreview
            document={auditReport}
            emptyText="Sin auditoria de ejecucion disponible"
            kicker="Auditoria humana"
          />
        </details>
      ) : (
        <MarkdownDocumentPreview
          document={auditReport}
          emptyText="Sin auditoria de ejecucion disponible"
          kicker="Auditoria humana"
        />
      )}
    </section>
  );
}

export function ReportDebatePanel({ reportDebate }: { reportDebate: string | null }) {
  return (
    <section className="registry-section report-debate-section">
      <div className="section-heading">
        <div>
          <h3>Debate del informe</h3>
          <p>{reportDebate ? "Conversacion auditada entre agentes" : "Debate no disponible"}</p>
        </div>
        <div className="report-heading-actions debate-heading-actions">
          <StatusPill
            ok={reportDebate !== null}
            label={reportDebate ? "disponible" : "pendiente"}
            muted={reportDebate === null}
          />
          <MessageSquare size={18} />
        </div>
      </div>
      {reportDebate ? (
        <details className="compact-disclosure report-disclosure">
          <summary>Debate completo</summary>
          <MarkdownDocumentPreview
            document={reportDebate}
            emptyText="Sin debate controlado disponible"
            kicker="Debate agentico"
          />
        </details>
      ) : (
        <MarkdownDocumentPreview
          document={reportDebate}
          emptyText="Sin debate controlado disponible"
          kicker="Debate agentico"
        />
      )}
    </section>
  );
}

function ReportPreview({ report }: { report: string | null }) {
  return (
    <MarkdownDocumentPreview
      document={report}
      emptyText="Sin informe disponible"
      kicker="Documento de cierre"
    />
  );
}

function EvidenceHubHeading({
  readyCount,
  subtitle,
  title,
}: {
  readyCount: number;
  subtitle: string;
  title: string;
}) {
  return (
    <div className="section-heading evidence-hub-heading">
      <div>
        <p className="eyebrow">Evidencia</p>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      <StatusPill ok={readyCount > 0} muted={readyCount === 0} label={`${readyCount}/5 listos`} />
    </div>
  );
}

function EvidenceSignal({
  icon,
  label,
  ready,
  value,
}: {
  icon: ReactNode;
  label: string;
  ready: boolean;
  value: string;
}) {
  return (
    <div className={`evidence-signal ${ready ? "ready" : ""}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvidenceFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="evidence-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvidenceDocumentDisclosure({
  available,
  children,
  icon,
  statusLabel,
  title,
}: {
  available: boolean;
  children: ReactNode;
  icon: ReactNode;
  statusLabel: string;
  title: string;
}) {
  return (
    <details className="compact-disclosure evidence-document-card">
      <summary>
        <span className="evidence-document-title">
          {icon}
          <strong>{title}</strong>
        </span>
        <StatusPill ok={available} muted={!available} label={statusLabel} />
      </summary>
      {available ? children : <p className="empty-state compact-empty">No disponible</p>}
    </details>
  );
}

function ArtifactSummary({ artifacts }: { artifacts: ArtifactRef[] }) {
  if (artifacts.length === 0) {
    return null;
  }

  const grouped = artifacts.reduce<Map<string, number>>((accumulator, artifact) => {
    const label = artifactTypeLabel(artifact.artifact_type);
    accumulator.set(label, (accumulator.get(label) ?? 0) + 1);
    return accumulator;
  }, new Map());

  return (
    <div className="artifact-summary-grid" aria-label="Resumen de artefactos">
      {Array.from(grouped.entries())
        .slice(0, 6)
        .map(([label, count]) => (
          <div className="artifact-summary-item" key={label}>
            <span>{label}</span>
            <strong>{count}</strong>
          </div>
        ))}
    </div>
  );
}

function ArtifactList({ artifacts }: { artifacts: ArtifactRef[] }) {
  if (artifacts.length === 0) {
    return <p className="empty-state compact-empty">Sin artefactos</p>;
  }

  return (
    <div className="artifact-list">
      {artifacts.map((artifact, index) => (
        <div className="artifact-row" key={`${artifact.name}-${artifact.path}-${index}`}>
          <div>
            <strong>{artifact.name}</strong>
            <span>
              {artifactTypeLabel(artifact.artifact_type)} | {artifact.producer}
            </span>
            {artifact.description ? <small>{artifact.description}</small> : null}
          </div>
          <details className="artifact-path-disclosure">
            <summary>Ruta tecnica</summary>
            <code>{artifact.path}</code>
          </details>
        </div>
      ))}
    </div>
  );
}

function hasEvidencePack(snapshot: RunSnapshot | null, artifacts: ArtifactRef[]): boolean {
  if (snapshot === null) {
    return false;
  }
  return Boolean(
    snapshot.evidence_pack_path ||
      snapshot.evidence_pack_markdown_path ||
      artifacts.some((artifact) => artifact.name.toLowerCase().includes("evidence")),
  );
}

function artifactTypeLabel(value: string): string {
  return value.replace(/_/g, " ");
}
