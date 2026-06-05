import { Activity, FileSearch } from "lucide-react";
import type { FormEvent } from "react";

import type {
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  ArtifactRef,
  DatasetAdapterInfo,
  DatasetDescribeResponse,
  HumanApproval,
  HumanReviewMode,
  LLMStatusResponse,
  PipelineRunStage,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunSnapshot,
} from "../../types";
import { PanelTitle } from "../common/PanelTitle";
import { JobView } from "../jobs/JobView";
import { PlanView } from "../plans/PlanView";
import { RunHistoryPanel } from "../runs/RunHistoryPanel";
import { PipelineConfig } from "./PipelineConfig";

export function PipelineDashboard({
  activeJob,
  adapters,
  approvalRequired,
  canExecutePlan,
  comparingRuns,
  customStages,
  datasetDescription,
  executing,
  humanReviewReasons,
  job,
  jobSnapshot,
  llmStatus,
  loadingRunDetail,
  planResponse,
  planning,
  request,
  runComparison,
  runFilters,
  selectedAdapter,
  selectedAdapterId,
  selectedArtifacts,
  selectedAuditReport,
  selectedCompareRunIds,
  selectedReport,
  selectedReportDebate,
  selectedRunEntry,
  selectedRunId,
  selectedSnapshot,
  visibleRuns,
  onApplyAdapter,
  onCompare,
  onExecute,
  onRefreshLlm,
  onResetRunFilters,
  onRunFilterChange,
  onSelectRun,
  onSubmitDryRun,
  onToggleCompareRun,
  onToggleCustomStages,
  onToggleHumanReviewPoint,
  onToggleStage,
  onUpdateHumanApproval,
  onUpdateHumanReviewMode,
  onUpdateHumanReviewer,
  onUpdateRequest,
}: {
  activeJob: boolean;
  adapters: DatasetAdapterInfo[];
  approvalRequired: boolean;
  canExecutePlan: boolean;
  comparingRuns: boolean;
  customStages: boolean;
  datasetDescription: DatasetDescribeResponse | null;
  executing: boolean;
  humanReviewReasons: string[];
  job: ApiRunJobStatus | null;
  jobSnapshot: RunSnapshot | null;
  llmStatus: LLMStatusResponse | null;
  loadingRunDetail: boolean;
  planResponse: ApiRunResponse | null;
  planning: boolean;
  request: ApiRunRequest;
  runComparison: RunComparison | null;
  runFilters: RunFilters;
  selectedAdapter: DatasetAdapterInfo;
  selectedAdapterId: string;
  selectedArtifacts: ArtifactRef[];
  selectedAuditReport: string | null;
  selectedCompareRunIds: string[];
  selectedReport: string | null;
  selectedReportDebate: string | null;
  selectedRunEntry: RunIndexEntry | null;
  selectedRunId: string | null;
  selectedSnapshot: RunSnapshot | null;
  visibleRuns: RunIndexEntry[];
  onApplyAdapter: (adapterId: string) => void;
  onCompare: () => void;
  onExecute: () => void;
  onRefreshLlm: () => void;
  onResetRunFilters: () => void;
  onRunFilterChange: (key: keyof RunFilters, value: string | boolean | null) => void;
  onSelectRun: (runId: string) => void;
  onSubmitDryRun: (event: FormEvent<HTMLFormElement>) => void;
  onToggleCompareRun: (runId: string) => void;
  onToggleCustomStages: (enabled: boolean) => void;
  onToggleHumanReviewPoint: (stage: PipelineRunStage) => void;
  onToggleStage: (stage: PipelineRunStage) => void;
  onUpdateHumanApproval: (update: Partial<HumanApproval>) => void;
  onUpdateHumanReviewMode: (mode: HumanReviewMode) => void;
  onUpdateHumanReviewer: (reviewer: string) => void;
  onUpdateRequest: <Key extends keyof ApiRunRequest>(
    key: Key,
    value: ApiRunRequest[Key],
  ) => void;
}) {
  return (
    <section className="pipeline-layout">
      <PipelineConfig
        activeJob={activeJob}
        adapters={adapters}
        approvalRequired={approvalRequired}
        canExecutePlan={canExecutePlan}
        customStages={customStages}
        executing={executing}
        humanReviewReasons={humanReviewReasons}
        llmStatus={llmStatus}
        planning={planning}
        request={request}
        selectedAdapter={selectedAdapter}
        selectedAdapterId={selectedAdapterId}
        onApplyAdapter={onApplyAdapter}
        onExecute={onExecute}
        onRefreshLlm={onRefreshLlm}
        onSubmitDryRun={onSubmitDryRun}
        onToggleCustomStages={onToggleCustomStages}
        onToggleHumanReviewPoint={onToggleHumanReviewPoint}
        onToggleStage={onToggleStage}
        onUpdateHumanApproval={onUpdateHumanApproval}
        onUpdateHumanReviewMode={onUpdateHumanReviewMode}
        onUpdateHumanReviewer={onUpdateHumanReviewer}
        onUpdateRequest={onUpdateRequest}
      />

      <div className="operation-column">
        <PreflightPanel response={planResponse} description={datasetDescription} />
        <ExecutionStatus job={job} snapshot={jobSnapshot} />
      </div>

      <RunHistoryPanel
        adapters={adapters}
        comparison={runComparison}
        filters={runFilters}
        loading={loadingRunDetail}
        comparingRuns={comparingRuns}
        selectedArtifacts={selectedArtifacts}
        selectedAuditReport={selectedAuditReport}
        selectedCompareRunIds={selectedCompareRunIds}
        selectedReport={selectedReport}
        selectedReportDebate={selectedReportDebate}
        selectedRunEntry={selectedRunEntry}
        selectedRunId={selectedRunId}
        selectedSnapshot={selectedSnapshot}
        runs={visibleRuns}
        onCompare={onCompare}
        onFilterChange={onRunFilterChange}
        onResetFilters={onResetRunFilters}
        onSelectRun={onSelectRun}
        onToggleCompare={onToggleCompareRun}
      />
    </section>
  );
}

function PreflightPanel({
  response,
  description,
}: {
  response: ApiRunResponse | null;
  description: DatasetDescribeResponse | null;
}) {
  return (
    <section className="panel preflight-panel">
      <PanelTitle
        eyebrow="Preflight"
        title="Plan de ejecucion"
        icon={<FileSearch size={19} />}
      />
      <PlanView response={response} description={description} />
    </section>
  );
}

function ExecutionStatus({
  job,
  snapshot,
}: {
  job: ApiRunJobStatus | null;
  snapshot: RunSnapshot | null;
}) {
  return (
    <section className="panel execution-panel">
      <PanelTitle eyebrow="Ejecucion" title="Job activo" icon={<Activity size={19} />} />
      <JobView job={job} snapshot={snapshot} />
    </section>
  );
}
