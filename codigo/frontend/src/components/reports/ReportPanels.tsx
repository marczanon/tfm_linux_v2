import { FileSearch, FileText, MessageSquare } from "lucide-react";

import { StatusPill } from "../common/StatusPill";
import type { RunSnapshot } from "../../types";
import { MarkdownDocumentPreview } from "./ReportDocument";

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
      <ReportPreview report={report} />
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
      <MarkdownDocumentPreview
        document={auditReport}
        emptyText="Sin auditoria de ejecucion disponible"
        kicker="Auditoria humana"
      />
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
      <MarkdownDocumentPreview
        document={reportDebate}
        emptyText="Sin debate controlado disponible"
        kicker="Debate agentico"
      />
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
