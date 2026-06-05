import {
  Activity,
  Brain,
  CheckCircle2,
  Database,
  ListChecks,
  Server,
} from "lucide-react";

import { StatusItem } from "../common/StatusItem";
import { llmStatusLabel } from "../../lib/labels";
import type { HealthResponse, LLMStatusResponse } from "../../types";

export function HealthSummary({
  adaptersCount,
  approvedRuns,
  completedRuns,
  health,
  llmStatus,
  runsCount,
}: {
  adaptersCount: number;
  approvedRuns: number;
  completedRuns: number;
  health: HealthResponse | null;
  llmStatus: LLMStatusResponse | null;
  runsCount: number;
}) {
  return (
    <section className="health-summary" aria-label="Estado global">
      <StatusItem icon={<Server size={18} />} label="API" value={health?.status ?? "-"} />
      <StatusItem icon={<Brain size={18} />} label="LLM" value={llmStatusLabel(llmStatus)} />
      <StatusItem icon={<Database size={18} />} label="Adaptadores" value={adaptersCount.toString()} />
      <StatusItem icon={<ListChecks size={18} />} label="Runs" value={runsCount.toString()} />
      <StatusItem icon={<CheckCircle2 size={18} />} label="Completadas" value={completedRuns.toString()} />
      <StatusItem icon={<Activity size={18} />} label="Aprobadas" value={approvedRuns.toString()} />
    </section>
  );
}
