import { Activity } from "lucide-react";
import type { ReactNode } from "react";

import { ErrorState } from "../common/ErrorState";
import { StatusPill } from "../common/StatusPill";
import { llmStatusLabel } from "../../lib/labels";
import type { HealthResponse, LLMStatusResponse } from "../../types";
import type { AppView } from "../../types/ui";
import { HealthSummary } from "./HealthSummary";
import { StatusHeader } from "./StatusHeader";
import { ViewTabs } from "./ViewTabs";

export function AppShell({
  activeView,
  adaptersCount,
  approvedRuns,
  children,
  completedRuns,
  error,
  health,
  llmStatus,
  loading,
  runsCount,
  onRefresh,
  onViewChange,
}: {
  activeView: AppView;
  adaptersCount: number;
  approvedRuns: number;
  children: ReactNode;
  completedRuns: number;
  error: string | null;
  health: HealthResponse | null;
  llmStatus: LLMStatusResponse | null;
  loading: boolean;
  runsCount: number;
  onRefresh: () => void;
  onViewChange: (view: AppView) => void;
}) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <Activity size={19} />
          </div>
          <div>
            <p className="eyebrow">Fase 5</p>
            <h1>TFM Pipeline</h1>
          </div>
        </div>
        <ViewTabs activeView={activeView} onChange={onViewChange} />
        <div className="sidebar-status">
          <StatusPill ok={health?.status === "ok"} label={health?.status ?? "offline"} />
          <span>{llmStatusLabel(llmStatus)}</span>
        </div>
      </aside>

      <main className="app-main">
        <StatusHeader loading={loading} onRefresh={onRefresh} />
        {error ? <ErrorState message={error} /> : null}
        <HealthSummary
          adaptersCount={adaptersCount}
          approvedRuns={approvedRuns}
          completedRuns={completedRuns}
          health={health}
          llmStatus={llmStatus}
          runsCount={runsCount}
        />
        <div className="view-content">{children}</div>
      </main>
    </div>
  );
}
