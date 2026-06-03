import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  CheckCircle2,
  Database,
  FileSearch,
  FileText,
  GitCompare,
  ListChecks,
  MessageSquare,
  Network,
  Package,
  Play,
  RefreshCcw,
  Server,
  Users,
  XCircle,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  ApiClientError,
  compareRuns,
  createBackgroundRun,
  createDryRun,
  curateMemoryRecord,
  deleteMemoryRecord,
  describeDataset,
  getHealth,
  getLLMStatus,
  getRun,
  getRunAuditReport,
  getRunArtifacts,
  getRunJob,
  getRunReport,
  getRunReportDebate,
  getRunVisualization,
  getMemoryRecord,
  listDatasetAdapters,
  listMemoryCollections,
  listMemoryRecords,
  listRuns,
} from "./api";
import type {
  AgentOperationalRecommendation,
  AgentRuntimeEvent,
  AgentMemoryTarget,
  ArtifactRef,
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  DatasetCapabilityRule,
  DatasetAdapterInfo,
  DatasetDescribeResponse,
  HealthState,
  HealthResponse,
  HumanApproval,
  HumanReviewMode,
  LLMStatusResponse,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  PipelineRunExecutionMode,
  PipelineRunStage,
  ProjectionBoundary,
  ProjectionPoint,
  ReasoningMemoryRecord,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunVisualizationData,
  RunSnapshot,
  TemporalRunSeries,
  VisualizationMetric,
} from "./types";
import type { ReactNode } from "react";

const FALLBACK_ADAPTER: DatasetAdapterInfo = {
  adapter_id: "cwru_bearing",
  dataset_id: "cwru_bearing",
  display_name: "CWRU Bearing Dataset",
  supported_source_formats: ["mat", "directory"],
  supports_descriptor: true,
  supports_manifest: true,
  is_experimental: false,
  notes: "Fallback local hasta cargar el catalogo del backend.",
};

const DATASET_REQUEST_DEFAULTS: Record<
  string,
  {
    rawPath: string;
    executionMode: PipelineRunExecutionMode;
    datasetPolicyId: string | null;
    allowSyntheticLabels: boolean;
  }
> = {
  cwru_bearing: {
    rawPath: "codigo/data/raw/cwru_bearing/mat",
    executionMode: "full",
    datasetPolicyId: null,
    allowSyntheticLabels: false,
  },
  nasa_ims_bearing: {
    rawPath: "codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen",
    executionMode: "full",
    datasetPolicyId: "nasa_ims_temporal_v1",
    allowSyntheticLabels: false,
  },
  generic_tabular_signal: {
    rawPath: "codigo/data/raw/uploads",
    executionMode: "diagnostic",
    datasetPolicyId: null,
    allowSyntheticLabels: false,
  },
};

const PIPELINE_STAGES: PipelineRunStage[] = [
  "manifest",
  "profiling",
  "cleaning",
  "structuring",
  "modeling",
  "evaluation",
  "reporting",
  "memory",
];

const HUMAN_REVIEW_POINTS: PipelineRunStage[] = [
  "modeling",
  "evaluation",
  "memory",
];

const STAGE_LABELS: Record<PipelineRunStage, string> = {
  manifest: "Manifest",
  profiling: "Perfilado",
  cleaning: "Limpieza",
  structuring: "Estructura",
  modeling: "Modelado",
  evaluation: "Evaluacion",
  reporting: "Informe",
  memory: "Memoria",
};

const RUN_STAGE_FILTERS = ["completed", "failed", "reporting", "evaluation", "modeling"];

const DEFAULT_RUN_FILTERS: RunFilters = {
  dataset: null,
  current_stage: null,
  approved: null,
};

type AppView = "pipeline" | "agents" | "visualization";

const AGENT_PROFILES = [
  {
    id: "supervisor",
    label: "Supervisor",
    role: "Jefe",
    node: "supervisor",
  },
  {
    id: "cleaner",
    label: "Limpiador",
    role: "Calidad",
    node: "cleaner_agent",
  },
  {
    id: "structurer",
    label: "Estructurador",
    role: "Datos",
    node: "structuring_agent",
  },
  {
    id: "modeler",
    label: "Modelador",
    role: "Modelos",
    node: "modeling_agent",
  },
  {
    id: "evaluator",
    label: "Evaluador",
    role: "Metricas",
    node: "evaluation_agent",
  },
  {
    id: "report_writer",
    label: "Redactor",
    role: "Informe",
    node: "report_writer",
  },
  {
    id: "report_verifier",
    label: "Verificador",
    role: "Auditoria",
    node: "report_verifier",
  },
] as const;

export default function App() {
  const [activeView, setActiveView] = useState<AppView>("pipeline");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatusResponse | null>(null);
  const [adapters, setAdapters] = useState<DatasetAdapterInfo[]>([FALLBACK_ADAPTER]);
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [runFilters, setRunFilters] = useState<RunFilters>(DEFAULT_RUN_FILTERS);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<RunSnapshot | null>(null);
  const [selectedArtifacts, setSelectedArtifacts] = useState<ArtifactRef[]>([]);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const [selectedAuditReport, setSelectedAuditReport] = useState<string | null>(null);
  const [selectedReportDebate, setSelectedReportDebate] = useState<string | null>(null);
  const [selectedVisualization, setSelectedVisualization] =
    useState<RunVisualizationData | null>(null);
  const [selectedCompareRunIds, setSelectedCompareRunIds] = useState<string[]>([]);
  const [runComparison, setRunComparison] = useState<RunComparison | null>(null);
  const [request, setRequest] = useState<ApiRunRequest>(() => defaultRequest(FALLBACK_ADAPTER));
  const [customStages, setCustomStages] = useState(false);
  const [selectedAdapterId, setSelectedAdapterId] = useState(FALLBACK_ADAPTER.adapter_id);
  const [datasetDescription, setDatasetDescription] =
    useState<DatasetDescribeResponse | null>(null);
  const [planResponse, setPlanResponse] = useState<ApiRunResponse | null>(null);
  const [job, setJob] = useState<ApiRunJobStatus | null>(null);
  const [jobSnapshot, setJobSnapshot] = useState<RunSnapshot | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("supervisor");
  const [memoryCollections, setMemoryCollections] = useState<MemoryCollectionSummary[]>([]);
  const [memoryRecords, setMemoryRecords] = useState<MemoryRecordSummary[]>([]);
  const [selectedMemoryRecord, setSelectedMemoryRecord] =
    useState<ReasoningMemoryRecord | null>(null);
  const [memorySearchText, setMemorySearchText] = useState("");
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [loadingRunDetail, setLoadingRunDetail] = useState(false);
  const [loadingVisualization, setLoadingVisualization] = useState(false);
  const [loadingMemory, setLoadingMemory] = useState(false);
  const [curatingMemory, setCuratingMemory] = useState(false);
  const [comparingRuns, setComparingRuns] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibleRuns = useMemo(() => runs.slice(0, 20), [runs]);
  const runtimeEvents = useMemo(() => job?.events ?? [], [job?.events]);
  const completedRuns = useMemo(
    () => runs.filter((run) => run.current_stage === "completed").length,
    [runs],
  );
  const approvedRuns = useMemo(
    () => runs.filter((run) => run.approved === true).length,
    [runs],
  );
  const selectedAdapter = useMemo(
    () =>
      adapters.find((adapter) => adapter.adapter_id === selectedAdapterId) ??
      adapters[0] ??
      FALLBACK_ADAPTER,
    [adapters, selectedAdapterId],
  );
  const selectedRunEntry = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  );
  const activeJob = job !== null && isActiveJob(job);
  const humanReviewReasons = planResponse?.human_review_reasons ?? [];
  const approvalRequired =
    request.human_review.mode === "required" && humanReviewReasons.length > 0;
  const approvalReady =
    !approvalRequired || request.human_approval?.approved === true;
  const llmReady =
    !request.use_llm ||
    (llmStatus?.available === true && llmStatus.model_available === true);
  const canExecutePlan =
    planResponse?.plan.can_execute_requested_stages === true &&
    approvalReady &&
    llmReady &&
    !planning &&
    !executing &&
    !activeJob &&
    !(job?.run_id === request.run_id.trim() && job.status === "completed");

  useEffect(() => {
    void refreshDashboard();
  }, [runFilters.dataset, runFilters.current_stage, runFilters.approved]);

  useEffect(() => {
    if (job === null || !isActiveJob(job)) {
      return;
    }

    let cancelled = false;

    async function pollJob() {
      try {
        const next = await getRunJob(job!.job_id);
        if (cancelled) {
          return;
        }
        setJob(next);
        if (next.status === "completed") {
          const snapshot = next.snapshot ?? (await getRun(next.run_id));
          if (!cancelled) {
            setJobSnapshot(snapshot);
            setSelectedRunId(next.run_id);
            await loadRunDetail(next.run_id);
            await refreshDashboard();
          }
        }
        if (next.status === "failed") {
          setError(next.detail ?? "La ejecucion en segundo plano fallo.");
        }
      } catch (caught) {
        if (!cancelled) {
          setError(errorText(caught));
        }
      }
    }

    void pollJob();
    const intervalId = window.setInterval(() => void pollJob(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (activeView !== "agents") {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      void refreshMemoryView();
    }, 180);
    return () => window.clearTimeout(timeoutId);
  }, [activeView, selectedAgentId, memorySearchText]);

  async function refreshDashboard() {
    setLoadingDashboard(true);
    setError(null);
    try {
      const [healthPayload, llmPayload, runsPayload, adaptersPayload] = await Promise.all([
        getHealth(),
        getLLMStatus(),
        listRuns(runFilters),
        listDatasetAdapters(),
      ]);
      setHealth(healthPayload);
      setLlmStatus(llmPayload);
      setRuns(runsPayload);
      if (adaptersPayload.length > 0) {
        setAdapters(adaptersPayload);
        setSelectedAdapterId((current) =>
          adaptersPayload.some((adapter) => adapter.adapter_id === current)
            ? current
            : adaptersPayload[0].adapter_id,
        );
        setRequest((current) =>
          adaptersPayload.some((adapter) => adapter.adapter_id === current.adapter_id)
            ? current
            : defaultRequest(adaptersPayload[0]),
        );
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingDashboard(false);
    }
  }

  async function refreshLLMStatus() {
    try {
      setLlmStatus(await getLLMStatus());
    } catch (caught) {
      setError(errorText(caught));
    }
  }

  async function submitDryRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPlanning(true);
    setError(null);
    setPlanResponse(null);
    setDatasetDescription(null);
    try {
      const normalized = normalizedRequest(request, customStages);
      const description = await describeDataset({
        raw_path: normalized.raw_path,
        adapter_id: normalized.adapter_id,
      });
      setDatasetDescription(description);
      const response = await createDryRun(normalized);
      setPlanResponse(response);
      const responseApproval = response.human_approval;
      if (responseApproval !== null) {
        setRequest((current) => ({
          ...current,
          human_approval: mergeHumanApproval(
            current.human_approval,
            responseApproval,
          ),
        }));
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setPlanning(false);
    }
  }

  async function executeBackgroundRun() {
    setExecuting(true);
    setError(null);
    setJob(null);
    setJobSnapshot(null);
    try {
      const normalized = normalizedRequest(request, customStages);
      if (normalized.use_llm) {
        const currentLlmStatus = await getLLMStatus();
        setLlmStatus(currentLlmStatus);
        if (!currentLlmStatus.available || !currentLlmStatus.model_available) {
          setError(
            currentLlmStatus.detail ??
              `Ollama no tiene disponible el modelo ${currentLlmStatus.model}.`,
          );
          return;
        }
      }
      const description = await describeDataset({
        raw_path: normalized.raw_path,
        adapter_id: normalized.adapter_id,
      });
      setDatasetDescription(description);
      const plan =
        planResponse?.run_id === normalized.run_id
          ? planResponse
          : await createDryRun(normalized);
      setPlanResponse(plan);
      if (!plan.plan.can_execute_requested_stages) {
        setError("La politica del dataset bloquea las fases solicitadas.");
        return;
      }
      if (
        normalized.human_review.mode === "required" &&
        plan.human_review_reasons.length > 0 &&
        normalized.human_approval?.approved !== true
      ) {
        setError("La revision humana requerida necesita aprobacion explicita.");
        return;
      }
      const response = await createBackgroundRun(normalized);
      setPlanResponse(response);
      if (response.job === null) {
        throw new Error("La API no devolvio job para la ejecucion background.");
      }
      setJob(response.job);
      setActiveView("agents");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setExecuting(false);
    }
  }

  async function loadRunDetail(runId: string) {
    setLoadingRunDetail(true);
    setLoadingVisualization(true);
    setError(null);
    try {
      const [snapshot, artifacts, report, auditReport, reportDebate, visualization] = await Promise.all([
        getRun(runId),
        getRunArtifacts(runId),
        getRunReport(runId).catch((caught) => {
          if (caught instanceof ApiClientError && caught.status === 404) {
            return null;
          }
          throw caught;
        }),
        getRunAuditReport(runId).catch((caught) => {
          if (caught instanceof ApiClientError && caught.status === 404) {
            return null;
          }
          throw caught;
        }),
        getRunReportDebate(runId).catch((caught) => {
          if (caught instanceof ApiClientError && caught.status === 404) {
            return null;
          }
          throw caught;
        }),
        getRunVisualization(runId).catch((caught) => {
          if (caught instanceof ApiClientError && caught.status === 404) {
            return null;
          }
          throw caught;
        }),
      ]);
      setSelectedRunId(runId);
      setSelectedSnapshot(snapshot);
      setSelectedArtifacts(artifacts);
      setSelectedReport(report);
      setSelectedAuditReport(auditReport);
      setSelectedReportDebate(reportDebate);
      setSelectedVisualization(visualization);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingRunDetail(false);
      setLoadingVisualization(false);
    }
  }

  async function refreshMemoryView() {
    setLoadingMemory(true);
    setError(null);
    try {
      const targetAgent = memoryTargetForAgent(selectedAgentId);
      const [collectionsPayload, recordsPayload] = await Promise.all([
        listMemoryCollections(),
        listMemoryRecords({
          target_agent: targetAgent,
          search_text: emptyToNull(memorySearchText),
        }),
      ]);
      setMemoryCollections(collectionsPayload);
      setMemoryRecords(recordsPayload);
      if (
        selectedMemoryRecord === null ||
        !recordsPayload.some(
          (record) => record.memory_record_id === selectedMemoryRecord.memory_record_id,
        )
      ) {
        setSelectedMemoryRecord(null);
      }
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingMemory(false);
    }
  }

  async function loadMemoryRecord(memoryRecordId: string) {
    setLoadingMemory(true);
    setError(null);
    try {
      const record = await getMemoryRecord(memoryRecordId);
      setSelectedMemoryRecord(record);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingMemory(false);
    }
  }

  async function handleCurateMemoryRecord(
    memoryRecordId: string,
    action: "exclude" | "restore",
  ) {
    const reason =
      action === "exclude"
        ? "Manual exclusion from cockpit"
        : "Manual restore from cockpit";
    setCuratingMemory(true);
    setError(null);
    try {
      const response = await curateMemoryRecord(memoryRecordId, {
        action,
        reason,
        reviewer: "frontend_user",
      });
      if (response.record) {
        setSelectedMemoryRecord(response.record);
      } else {
        setSelectedMemoryRecord(null);
      }
      await refreshMemoryView();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setCuratingMemory(false);
    }
  }

  async function handleDeleteMemoryRecord(memoryRecordId: string) {
    const confirmed = window.confirm(
      "Borrar este recuerdo del indice local de memoria? Esta accion no elimina los artefactos fuente.",
    );
    if (!confirmed) {
      return;
    }
    setCuratingMemory(true);
    setError(null);
    try {
      await deleteMemoryRecord(memoryRecordId, "Manual delete from cockpit");
      setSelectedMemoryRecord(null);
      await refreshMemoryView();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setCuratingMemory(false);
    }
  }

  async function submitRunComparison() {
    if (selectedCompareRunIds.length < 2) {
      return;
    }
    setComparingRuns(true);
    setError(null);
    try {
      const comparison = await compareRuns(selectedCompareRunIds);
      setRunComparison(comparison);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setComparingRuns(false);
    }
  }

  function updateRunFilter(key: keyof RunFilters, value: string | boolean | null) {
    setRunFilters((current) => ({ ...current, [key]: value }));
  }

  function resetRunFilters() {
    setRunFilters(DEFAULT_RUN_FILTERS);
  }

  function toggleCompareRun(runId: string) {
    setRunComparison(null);
    setSelectedCompareRunIds((current) =>
      current.includes(runId)
        ? current.filter((candidate) => candidate !== runId)
        : [...current, runId],
    );
  }

  function applyAdapter(adapterId: string) {
    const adapter =
      adapters.find((candidate) => candidate.adapter_id === adapterId) ??
      adapters[0] ??
      FALLBACK_ADAPTER;
    setSelectedAdapterId(adapter.adapter_id);
    setRequest(defaultRequest(adapter));
    setCustomStages(false);
    setDatasetDescription(null);
    setPlanResponse(null);
    setJob(null);
    setJobSnapshot(null);
  }

  function updateRequest<Key extends keyof ApiRunRequest>(
    key: Key,
    value: ApiRunRequest[Key],
  ) {
    setRequest((current) => ({ ...current, [key]: value }));
    setDatasetDescription(null);
    setPlanResponse(null);
  }

  function updateHumanReviewMode(mode: HumanReviewMode) {
    setRequest((current) => ({
      ...current,
      human_review: {
        ...current.human_review,
        mode,
      },
      human_approval: mode === "off" ? null : current.human_approval,
    }));
    setDatasetDescription(null);
    setPlanResponse(null);
  }

  function updateHumanReviewer(reviewer: string) {
    const normalized = emptyToNull(reviewer);
    setRequest((current) => ({
      ...current,
      human_review: {
        ...current.human_review,
        reviewer: normalized,
      },
      human_approval: current.human_approval
        ? {
            ...current.human_approval,
            reviewer: normalized,
          }
        : current.human_approval,
    }));
    setDatasetDescription(null);
    setPlanResponse(null);
  }

  function toggleHumanReviewPoint(stage: PipelineRunStage) {
    setRequest((current) => {
      const selected = current.human_review.required_decision_points;
      const next = selected.includes(stage)
        ? selected.filter((candidate) => candidate !== stage)
        : [...selected, stage];
      return {
        ...current,
        human_review: {
          ...current.human_review,
          required_decision_points: next,
        },
      };
    });
    setDatasetDescription(null);
    setPlanResponse(null);
  }

  function updateHumanApproval(update: Partial<HumanApproval>) {
    setRequest((current) => ({
      ...current,
      human_approval: {
        required: current.human_review.mode === "required",
        approved: null,
        reviewer: current.human_review.reviewer,
        reason: humanReviewReasons.join("; ") || null,
        reviewed_at: null,
        ...current.human_approval,
        ...update,
      },
    }));
  }

  function toggleStage(stage: PipelineRunStage) {
    const selected = request.requested_stages ?? [];
    const next = selected.includes(stage)
      ? selected.filter((candidate) => candidate !== stage)
      : [...selected, stage];
    updateRequest("requested_stages", next);
  }

  function updateCustomStages(enabled: boolean) {
    setCustomStages(enabled);
    updateRequest("requested_stages", enabled ? [] : null);
  }

  function selectAgent(agentId: string) {
    setSelectedAgentId(agentId);
    setSelectedMemoryRecord(null);
  }

  return (
    <AppShell
      activeView={activeView}
      adaptersCount={adapters.length}
      approvedRuns={approvedRuns}
      completedRuns={completedRuns}
      error={error}
      health={health}
      llmStatus={llmStatus}
      loading={loadingDashboard}
      runsCount={runs.length}
      onRefresh={() => void refreshDashboard()}
      onViewChange={setActiveView}
    >
      <RunContextBand
        request={request}
        adapter={selectedAdapter}
        response={planResponse}
        job={job}
      />

      {activeView === "pipeline" ? (
        <PipelineDashboard
          activeJob={activeJob}
          adapters={adapters}
          canExecutePlan={canExecutePlan}
          comparingRuns={comparingRuns}
          customStages={customStages}
          datasetDescription={datasetDescription}
          executing={executing}
          humanReviewReasons={humanReviewReasons}
          job={job}
          jobSnapshot={jobSnapshot}
          llmStatus={llmStatus}
          loadingRunDetail={loadingRunDetail}
          planResponse={planResponse}
          planning={planning}
          request={request}
          runComparison={runComparison}
          runFilters={runFilters}
          selectedAdapter={selectedAdapter}
          selectedAdapterId={selectedAdapterId}
          selectedArtifacts={selectedArtifacts}
          selectedAuditReport={selectedAuditReport}
          selectedCompareRunIds={selectedCompareRunIds}
          selectedReport={selectedReport}
          selectedReportDebate={selectedReportDebate}
          selectedRunEntry={selectedRunEntry}
          selectedRunId={selectedRunId}
          selectedSnapshot={selectedSnapshot}
          visibleRuns={visibleRuns}
          approvalRequired={approvalRequired}
          onApplyAdapter={applyAdapter}
          onCompare={() => void submitRunComparison()}
          onExecute={() => void executeBackgroundRun()}
          onRefreshLlm={() => void refreshLLMStatus()}
          onResetRunFilters={resetRunFilters}
          onRunFilterChange={updateRunFilter}
          onSelectRun={(runId) => void loadRunDetail(runId)}
          onSubmitDryRun={(event) => void submitDryRun(event)}
          onToggleCompareRun={toggleCompareRun}
          onToggleCustomStages={updateCustomStages}
          onToggleHumanReviewPoint={toggleHumanReviewPoint}
          onToggleStage={toggleStage}
          onUpdateHumanApproval={updateHumanApproval}
          onUpdateHumanReviewMode={updateHumanReviewMode}
          onUpdateHumanReviewer={updateHumanReviewer}
          onUpdateRequest={updateRequest}
        />
      ) : activeView === "agents" ? (
        <AgentObservabilityView
          job={job}
          events={runtimeEvents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={selectAgent}
          memoryCollections={memoryCollections}
          memoryRecords={memoryRecords}
          selectedMemoryRecord={selectedMemoryRecord}
          memorySearchText={memorySearchText}
          loadingMemory={loadingMemory}
          curatingMemory={curatingMemory}
          onMemorySearchChange={setMemorySearchText}
          onSelectMemoryRecord={(memoryRecordId) => void loadMemoryRecord(memoryRecordId)}
          onCurateMemoryRecord={(memoryRecordId, action) =>
            void handleCurateMemoryRecord(memoryRecordId, action)
          }
          onDeleteMemoryRecord={(memoryRecordId) =>
            void handleDeleteMemoryRecord(memoryRecordId)
          }
        />
      ) : (
        <VisualizationView
          runs={visibleRuns}
          selectedRunId={selectedRunId}
          data={selectedVisualization}
          loading={loadingVisualization}
          onSelectRun={(runId) => void loadRunDetail(runId)}
        />
      )}
    </AppShell>
  );
}

function AppShell({
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

function StatusHeader({
  loading,
  onRefresh,
}: {
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="status-header">
      <div>
        <p className="eyebrow">Operacion local</p>
        <h2>Dashboard de ejecucion multiagente</h2>
      </div>
      <button
        className="secondary-button"
        type="button"
        onClick={onRefresh}
        disabled={loading}
      >
        <RefreshCcw size={17} />
        Actualizar
      </button>
    </header>
  );
}

function HealthSummary({
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

function ErrorState({ message }: { message: string }) {
  return (
    <section className="alert" role="alert">
      <AlertTriangle size={18} />
      <span>{message}</span>
    </section>
  );
}

function PipelineDashboard({
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

function PipelineConfig({
  activeJob,
  adapters,
  approvalRequired,
  canExecutePlan,
  customStages,
  executing,
  humanReviewReasons,
  llmStatus,
  planning,
  request,
  selectedAdapter,
  selectedAdapterId,
  onApplyAdapter,
  onExecute,
  onRefreshLlm,
  onSubmitDryRun,
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
  customStages: boolean;
  executing: boolean;
  humanReviewReasons: string[];
  llmStatus: LLMStatusResponse | null;
  planning: boolean;
  request: ApiRunRequest;
  selectedAdapter: DatasetAdapterInfo;
  selectedAdapterId: string;
  onApplyAdapter: (adapterId: string) => void;
  onExecute: () => void;
  onRefreshLlm: () => void;
  onSubmitDryRun: (event: FormEvent<HTMLFormElement>) => void;
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
    <form className="panel config-panel" onSubmit={onSubmitDryRun}>
      <PanelTitle
        eyebrow="Configuracion"
        title="Nueva run"
        icon={<FileSearch size={19} />}
      />

      <div className="form-section">
        <label className="field">
          <span>Adaptador</span>
          <select
            value={selectedAdapterId}
            onChange={(event) => onApplyAdapter(event.target.value)}
          >
            {adapters.map((adapter) => (
              <option key={adapter.adapter_id} value={adapter.adapter_id}>
                {adapter.display_name}
              </option>
            ))}
          </select>
        </label>

        <div className="adapter-summary">
          <div>
            <span>Dataset</span>
            <strong>{selectedAdapter.dataset_id}</strong>
          </div>
          <div>
            <span>Formatos</span>
            <strong>{selectedAdapter.supported_source_formats.join(", ")}</strong>
          </div>
          <StatusPill
            ok={!selectedAdapter.is_experimental}
            label={selectedAdapter.is_experimental ? "experimental" : "estable"}
            muted={selectedAdapter.is_experimental}
          />
        </div>
      </div>

      <div className="form-section">
        <label className="field">
          <span>Run ID</span>
          <input
            value={request.run_id}
            onChange={(event) => onUpdateRequest("run_id", event.target.value)}
          />
        </label>
      </div>

      <div className="form-section form-grid">
        <label className="field">
          <span>Modo</span>
          <select
            value={request.execution_mode}
            onChange={(event) =>
              onUpdateRequest(
                "execution_mode",
                event.target.value as ApiRunRequest["execution_mode"],
              )
            }
          >
            <option value="full">Full</option>
            <option value="diagnostic">Diagnostic</option>
          </select>
        </label>

        <label className="field">
          <span>Human Review</span>
          <select
            value={request.human_review.mode}
            onChange={(event) =>
              onUpdateHumanReviewMode(event.target.value as HumanReviewMode)
            }
          >
            <option value="off">Off</option>
            <option value="passive">Passive</option>
            <option value="required">Required</option>
          </select>
        </label>
      </div>

      <HumanReviewControls
        request={request}
        reasons={humanReviewReasons}
        approvalRequired={approvalRequired}
        onReviewerChange={onUpdateHumanReviewer}
        onTogglePoint={onToggleHumanReviewPoint}
        onApprovalChange={onUpdateHumanApproval}
      />

      <div className="toggle-grid">
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.use_memory}
            onChange={(event) => onUpdateRequest("use_memory", event.target.checked)}
          />
          <span>Memoria local</span>
        </label>
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.use_llm}
            onChange={(event) => onUpdateRequest("use_llm", event.target.checked)}
          />
          <span>Agentes LLM</span>
        </label>
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.allow_synthetic_labels}
            onChange={(event) =>
              onUpdateRequest("allow_synthetic_labels", event.target.checked)
            }
          />
          <span>Etiquetas sinteticas</span>
        </label>
      </div>

      <LLMStatusPanel
        active={request.use_llm}
        status={llmStatus}
        onRefresh={onRefreshLlm}
      />

      <details className="advanced-options">
        <summary>Opciones avanzadas</summary>
        <div className="form-section form-grid">
          <label className="field">
            <span>Adapter ID</span>
            <input
              value={request.adapter_id ?? ""}
              onChange={(event) =>
                onUpdateRequest("adapter_id", emptyToNull(event.target.value))
              }
            />
          </label>
          <label className="field">
            <span>Policy ID</span>
            <input
              value={request.dataset_policy_id ?? ""}
              onChange={(event) =>
                onUpdateRequest("dataset_policy_id", emptyToNull(event.target.value))
              }
            />
          </label>
        </div>

        <section className="stage-section">
          <label className="switch-row">
            <input
              type="checkbox"
              checked={customStages}
              onChange={(event) => onToggleCustomStages(event.target.checked)}
            />
            <span>Fases manuales</span>
          </label>
          <div className="stage-grid" aria-disabled={!customStages}>
            {PIPELINE_STAGES.map((stage) => (
              <label className="stage-toggle" key={stage}>
                <input
                  type="checkbox"
                  checked={(request.requested_stages ?? []).includes(stage)}
                  onChange={() => onToggleStage(stage)}
                  disabled={!customStages}
                />
                <span>{STAGE_LABELS[stage]}</span>
              </label>
            ))}
          </div>
        </section>
      </details>

      <div className="action-bar">
        <button className="secondary-button" type="submit" disabled={planning || executing}>
          <FileSearch size={17} />
          {planning ? "Planificando" : "Planificar"}
        </button>
        <button
          className="primary-button"
          type="button"
          disabled={!canExecutePlan}
          onClick={onExecute}
        >
          <Play size={17} />
          {executing || activeJob ? "Ejecutando" : "Ejecutar"}
        </button>
      </div>
    </form>
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
      <PanelTitle eyebrow="Preflight" title="Plan de ejecucion" icon={<FileSearch size={19} />} />
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

function RunHistoryPanel({
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
    <section className="panel run-history-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Registro</p>
          <h2>Runs locales</h2>
        </div>
        <div className="panel-actions">
          <button
            className="icon-button"
            type="button"
            onClick={onResetFilters}
            title="Limpiar filtros"
            aria-label="Limpiar filtros"
          >
            <RefreshCcw size={17} />
          </button>
          <ListChecks size={20} />
        </div>
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
    </section>
  );
}

function PanelTitle({
  eyebrow,
  icon,
  title,
}: {
  eyebrow: string;
  icon?: ReactNode;
  title: string;
}) {
  return (
    <div className="panel-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {icon}
    </div>
  );
}

function RunContextBand({
  request,
  adapter,
  response,
  job,
}: {
  request: ApiRunRequest;
  adapter: DatasetAdapterInfo;
  response: ApiRunResponse | null;
  job: ApiRunJobStatus | null;
}) {
  const planOk = response?.plan.can_execute_requested_stages;
  const stageCount =
    response?.plan.effective_stages.length ??
    request.requested_stages?.length ??
    PIPELINE_STAGES.length;
  const jobStatus = job?.status ?? "sin job";

  return (
    <section className="context-band" aria-label="Contexto de ejecucion">
      <ContextItem
        label="Dataset"
        value={request.dataset_id || adapter.dataset_id}
        detail={adapter.display_name}
      />
      <ContextItem label="Run" value={request.run_id || "-"} />
      <ContextItem label="Modo" value={request.execution_mode} />
      <ContextItem label="Politica" value={request.dataset_policy_id ?? "default"} />
      <ContextItem label="Fases" value={stageCount.toString()} />
      <div className="context-item context-status">
        <span>Plan</span>
        <StatusPill
          ok={planOk === true}
          muted={planOk === undefined}
          label={
            planOk === undefined
              ? "sin plan"
              : planOk
                ? "ejecutable"
                : "bloqueado"
          }
        />
      </div>
      <div className="context-item context-status">
        <span>Job</span>
        <StatusPill
          ok={job?.status === "completed"}
          muted={job === null || job.status === "queued" || job.status === "running"}
          label={jobStatus}
        />
      </div>
    </section>
  );
}

function ContextItem({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="context-item">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function ViewTabs({
  activeView,
  onChange,
}: {
  activeView: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-tabs" aria-label="Vistas principales">
      <button
        className={activeView === "pipeline" ? "active" : ""}
        type="button"
        onClick={() => onChange("pipeline")}
      >
        <Activity size={16} />
        Pipeline
      </button>
      <button
        className={activeView === "agents" ? "active" : ""}
        type="button"
        onClick={() => onChange("agents")}
      >
        <Users size={16} />
        Agentes
      </button>
      <button
        className={activeView === "visualization" ? "active" : ""}
        type="button"
        onClick={() => onChange("visualization")}
      >
        <BarChart3 size={16} />
        Visualizacion
      </button>
    </nav>
  );
}

function HumanReviewControls({
  request,
  reasons,
  approvalRequired,
  onReviewerChange,
  onTogglePoint,
  onApprovalChange,
}: {
  request: ApiRunRequest;
  reasons: string[];
  approvalRequired: boolean;
  onReviewerChange: (reviewer: string) => void;
  onTogglePoint: (stage: PipelineRunStage) => void;
  onApprovalChange: (update: Partial<HumanApproval>) => void;
}) {
  if (request.human_review.mode === "off") {
    return null;
  }

  return (
    <section className="human-review-box">
      <div className="section-heading">
        <div>
          <h3>Revision humana</h3>
          <p>{request.human_review.mode}</p>
        </div>
        <StatusPill
          ok={!approvalRequired || request.human_approval?.approved === true}
          label={
            approvalRequired && request.human_approval?.approved !== true
              ? "pendiente"
              : "lista"
          }
          muted={!approvalRequired}
        />
      </div>

      <label className="field compact-field">
        <span>Revisor</span>
        <input
          value={request.human_review.reviewer ?? ""}
          onChange={(event) => onReviewerChange(event.target.value)}
        />
      </label>

      <div className="review-point-grid">
        {HUMAN_REVIEW_POINTS.map((stage) => (
          <label className="stage-toggle" key={stage}>
            <input
              type="checkbox"
              checked={request.human_review.required_decision_points.includes(stage)}
              onChange={() => onTogglePoint(stage)}
            />
            <span>{STAGE_LABELS[stage]}</span>
          </label>
        ))}
      </div>

      {reasons.length > 0 ? (
        <ul className="plain-list review-reasons">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {request.human_review.mode === "required" && reasons.length > 0 ? (
        <div className="approval-form">
          <label className="switch-row">
            <input
              type="checkbox"
              checked={request.human_approval?.approved === true}
              onChange={(event) =>
                onApprovalChange({
                  approved: event.target.checked ? true : null,
                  reviewed_at: event.target.checked ? new Date().toISOString() : null,
                })
              }
            />
            <span>Aprobada</span>
          </label>
          <label className="field compact-field">
            <span>Motivo</span>
            <textarea
              value={request.human_approval?.reason ?? reasons.join("; ")}
              onChange={(event) => onApprovalChange({ reason: event.target.value })}
            />
          </label>
        </div>
      ) : null}
    </section>
  );
}

function AgentObservabilityView({
  job,
  events,
  selectedAgentId,
  onSelectAgent,
  memoryCollections,
  memoryRecords,
  selectedMemoryRecord,
  memorySearchText,
  loadingMemory,
  curatingMemory,
  onMemorySearchChange,
  onSelectMemoryRecord,
  onCurateMemoryRecord,
  onDeleteMemoryRecord,
}: {
  job: ApiRunJobStatus | null;
  events: AgentRuntimeEvent[];
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
  memoryCollections: MemoryCollectionSummary[];
  memoryRecords: MemoryRecordSummary[];
  selectedMemoryRecord: ReasoningMemoryRecord | null;
  memorySearchText: string;
  loadingMemory: boolean;
  curatingMemory: boolean;
  onMemorySearchChange: (value: string) => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
  onCurateMemoryRecord: (
    memoryRecordId: string,
    action: "exclude" | "restore",
  ) => void;
  onDeleteMemoryRecord: (memoryRecordId: string) => void;
}) {
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const selectedEvents = eventsForAgent(events, selectedAgentId);
  const selectedEvent =
    selectedEvents.length > 0 ? selectedEvents[selectedEvents.length - 1] : null;
  const conversationMessages = agentConversationMessages(events);

  return (
    <section className="agent-workspace">
      <section className="panel agent-map-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Runtime</p>
            <h2>Oficina agentica</h2>
          </div>
          <Network size={20} />
        </div>

        <div className="agent-live-band">
          <StatusItem icon={<Activity size={18} />} label="Job" value={job?.status ?? "-"} />
          <StatusItem icon={<MessageSquare size={18} />} label="Eventos" value={events.length.toString()} />
          <StatusItem icon={<Brain size={18} />} label="Ultimo" value={latestEvent?.source ?? "-"} />
        </div>

        <div className="agent-office">
          <AgentNodeCard
            agentId="supervisor"
            selectedAgentId={selectedAgentId}
            events={events}
            onSelectAgent={onSelectAgent}
          />
          <div className="agent-branch" aria-hidden="true" />
          <div className="agent-grid">
            {AGENT_PROFILES.filter((agent) => agent.id !== "supervisor").map((agent) => (
              <AgentNodeCard
                key={agent.id}
                agentId={agent.id}
                selectedAgentId={selectedAgentId}
                events={events}
                onSelectAgent={onSelectAgent}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="panel agent-detail-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Decision</p>
            <h2>{agentLabel(selectedAgentId)}</h2>
          </div>
          <Brain size={20} />
        </div>
        <AgentRuntimeDetail
          event={selectedEvent}
          eventCount={selectedEvents.length}
          onSelectMemoryRecord={onSelectMemoryRecord}
        />
        <AgentMemoryPanel
          agentId={selectedAgentId}
          events={selectedEvents}
          collections={memoryCollections}
          records={memoryRecords}
          selectedRecord={selectedMemoryRecord}
          searchText={memorySearchText}
          loading={loadingMemory}
          curating={curatingMemory}
          onSearchChange={onMemorySearchChange}
          onSelectRecord={onSelectMemoryRecord}
          onCurateRecord={onCurateMemoryRecord}
          onDeleteRecord={onDeleteMemoryRecord}
        />
      </section>

      <section className="panel conversation-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Comunicacion</p>
            <h2>Conversacion</h2>
          </div>
          <MessageSquare size={20} />
        </div>
        <AgentConversation
          messages={conversationMessages}
          onSelectAgent={onSelectAgent}
        />
      </section>
    </section>
  );
}

function AgentNodeCard({
  agentId,
  selectedAgentId,
  events,
  onSelectAgent,
}: {
  agentId: string;
  selectedAgentId: string;
  events: AgentRuntimeEvent[];
  onSelectAgent: (agentId: string) => void;
}) {
  const profile = AGENT_PROFILES.find((agent) => agent.id === agentId);
  const agentEvents = eventsForAgent(events, agentId);
  const latestEvent =
    agentEvents.length > 0 ? agentEvents[agentEvents.length - 1] : null;
  const isSelected = selectedAgentId === agentId;
  const isActive = events.length > 0 && latestEvent?.sequence === events[events.length - 1].sequence;

  return (
    <button
      className={`agent-node ${isSelected ? "selected" : ""} ${isActive ? "active" : ""}`}
      type="button"
      onClick={() => onSelectAgent(agentId)}
    >
      <span className="agent-avatar">
        {agentId === "supervisor" ? <Network size={18} /> : <Brain size={18} />}
      </span>
      <span>
        <strong>{profile?.label ?? agentId}</strong>
        <small>{profile?.role ?? "Agente"}</small>
      </span>
      <em>{agentEvents.length}</em>
    </button>
  );
}

function AgentRuntimeDetail({
  event,
  eventCount,
  onSelectMemoryRecord,
}: {
  event: AgentRuntimeEvent | null;
  eventCount: number;
  onSelectMemoryRecord?: (memoryRecordId: string) => void;
}) {
  if (event === null) {
    return <p className="empty-state compact-empty">Sin eventos del agente</p>;
  }

  return (
    <div className="agent-detail">
      <div className="event-head">
        <StatusPill ok={event.kind !== "error"} label={kindLabel(event.kind)} />
        <span>{eventCount} eventos</span>
      </div>
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <AgentEventTranslation event={event} />
      <dl className="meta-list detail-meta">
        <div>
          <dt>decision_id</dt>
          <dd>{event.decision_id ?? "-"}</dd>
        </div>
        <div>
          <dt>confianza</dt>
          <dd>{confidenceText(event.confidence)}</dd>
        </div>
        <div>
          <dt>fase</dt>
          <dd>{event.stage ?? "-"}</dd>
        </div>
        <div>
          <dt>siguiente</dt>
          <dd>{event.next_node ?? event.next_stage ?? "-"}</dd>
        </div>
      </dl>
      {event.rationale ? (
        <section className="runtime-block">
          <h4>Rationale</h4>
          <p>{event.rationale}</p>
        </section>
      ) : null}
      {event.memory_record_ids.length > 0 ? (
        <section className="runtime-block">
          <h4>Memoria citada</h4>
          <div className="memory-chip-row">
            {event.memory_record_ids.map((memoryId) => (
              onSelectMemoryRecord ? (
                <button
                  className="memory-chip memory-chip-button"
                  key={memoryId}
                  type="button"
                  onClick={() => onSelectMemoryRecord(memoryId)}
                >
                  {memoryId}
                </button>
              ) : (
                <span className="memory-chip" key={memoryId}>
                  {memoryId}
                </span>
              )
            ))}
          </div>
        </section>
      ) : null}
      <section className="runtime-block">
        <h4>Payload</h4>
        <pre className="runtime-json">{JSON.stringify(event.payload, null, 2)}</pre>
      </section>
    </div>
  );
}

function AgentEventTranslation({ event }: { event: AgentRuntimeEvent }) {
  return (
    <section className="agent-translation" aria-label="Traduccion del evento JSON">
      <div>
        <span>Lectura humana</span>
        <strong>{agentEventPlainText(event)}</strong>
      </div>
    </section>
  );
}

interface AgentConversationMessage {
  id: string;
  sequence: number;
  agentId: string;
  agentLabel: string;
  role: string;
  title: string;
  text: string;
  createdAt: string;
  stage: string | null;
  status: "normal" | "success" | "warning" | "error";
  badges: string[];
}

function AgentConversation({
  messages,
  onSelectAgent,
}: {
  messages: AgentConversationMessage[];
  onSelectAgent: (agentId: string) => void;
}) {
  if (messages.length === 0) {
    return (
      <p className="empty-state">
        Sin conversacion agentica todavia
      </p>
    );
  }

  return (
    <div className="agent-chat" aria-label="Conversacion agentica">
      {messages.map((message) => (
        <button
          className={`chat-message ${message.status}`}
          key={message.id}
          type="button"
          onClick={() => onSelectAgent(message.agentId)}
        >
          <span className="chat-avatar">{agentInitials(message.agentLabel)}</span>
          <span className="chat-bubble">
            <span className="chat-meta">
              <strong>{message.agentLabel}</strong>
              <em>{formatEventTime(message.createdAt)}</em>
            </span>
            <span className="chat-role">{message.role}</span>
            <span className="chat-title">{message.title}</span>
            <span className="chat-text">{message.text}</span>
            {message.badges.length > 0 ? (
              <span className="chat-chip-row">
                {message.badges.map((badge) => (
                  <span className="chat-chip" key={`${message.id}-${badge}`}>
                    {badge}
                  </span>
                ))}
              </span>
            ) : null}
          </span>
        </button>
      ))}
    </div>
  );
}

function AgentMemoryPanel({
  agentId,
  events,
  collections,
  records,
  selectedRecord,
  searchText,
  loading,
  curating,
  onSearchChange,
  onSelectRecord,
  onCurateRecord,
  onDeleteRecord,
}: {
  agentId: string;
  events: AgentRuntimeEvent[];
  collections: MemoryCollectionSummary[];
  records: MemoryRecordSummary[];
  selectedRecord: ReasoningMemoryRecord | null;
  searchText: string;
  loading: boolean;
  curating: boolean;
  onSearchChange: (value: string) => void;
  onSelectRecord: (memoryRecordId: string) => void;
  onCurateRecord: (memoryRecordId: string, action: "exclude" | "restore") => void;
  onDeleteRecord: (memoryRecordId: string) => void;
}) {
  const target = memoryTargetForAgent(agentId);
  const collection = collections.find((item) => item.target_agent === target) ?? null;
  const sourceTypes = collection?.source_types ?? {};
  const retrievedMemoryIds = useMemo(
    () =>
      new Set(
        events
          .filter((event) => event.kind === "memory_retrieval" || event.memory_context_id !== null)
          .flatMap((event) => event.memory_record_ids),
      ),
    [events],
  );
  const citedMemoryIds = useMemo(
    () => new Set(events.flatMap((event) => event.memory_record_ids)),
    [events],
  );
  const lifecycleStages = [
    {
      label: "candidatos",
      value: sourceTypes.memory_candidate ?? 0,
      detail: "destilados",
      tone: "candidate",
    },
    {
      label: "indexados",
      value: collection?.n_records ?? 0,
      detail: collection?.collection_name ?? target,
      tone: "indexed",
    },
    {
      label: "recuperados",
      value: retrievedMemoryIds.size,
      detail: "runtime actual",
      tone: "reusable",
    },
    {
      label: "usados",
      value: citedMemoryIds.size,
      detail: "citados por agente",
      tone: "used",
    },
    {
      label: "auditorias",
      value: sourceTypes.memory_usage_audit ?? 0,
      detail: "uso posterior",
      tone: "audited",
    },
  ];

  return (
    <section className="runtime-block memory-panel">
      <div className="section-heading">
        <div>
          <h3>Cockpit de memoria</h3>
          <p>{collection?.collection_name ?? target}</p>
        </div>
        <StatusPill
          ok={(collection?.n_records ?? 0) > 0}
          label={`${collection?.n_records ?? 0} recuerdos`}
          muted={(collection?.n_records ?? 0) === 0}
        />
      </div>

      <div className="memory-cockpit-grid">
        <MemoryStat label="Total" value={collection?.n_records ?? 0} />
        <MemoryStat label="Reutilizables" value={collection?.n_reusable ?? 0} />
        <MemoryStat label="Datasets" value={collection?.datasets.length ?? 0} />
        <MemoryStat label="Excluidos" value={collection?.n_excluded ?? 0} tone="warning" />
      </div>

      <MemoryLifecycleStrip stages={lifecycleStages} />

      <div className="memory-distribution-grid">
        <MemoryDistribution
          title="Roles"
          entries={collection?.memory_roles ?? {}}
          labelFor={roleLabel}
        />
        <MemoryDistribution
          title="Origen"
          entries={collection?.source_types ?? {}}
          labelFor={sourceTypeLabel}
        />
      </div>

      <MemoryRuntimeFlow
        events={events}
        onSelectRecord={onSelectRecord}
      />

      <label className="field compact-field">
        <span>Buscar</span>
        <input
          value={searchText}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      {loading ? (
        <p className="empty-state compact-empty">Cargando memoria</p>
      ) : (
        <MemoryRecordList
          records={records}
          selectedRecordId={selectedRecord?.memory_record_id ?? null}
          usedRecordIds={citedMemoryIds}
          onSelectRecord={onSelectRecord}
        />
      )}

      <MemoryRecordDetail
        record={selectedRecord}
        curating={curating}
        onCurateRecord={onCurateRecord}
        onDeleteRecord={onDeleteRecord}
      />
    </section>
  );
}

function MemoryStat({
  label,
  value,
  tone = "normal",
}: {
  label: string;
  value: number;
  tone?: "normal" | "warning";
}) {
  return (
    <div className={`memory-stat ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MemoryLifecycleStrip({
  stages,
}: {
  stages: { label: string; value: number; detail: string; tone: string }[];
}) {
  return (
    <div className="memory-lifecycle" aria-label="Ciclo de vida de memoria">
      {stages.map((stage) => (
        <div className={`memory-lifecycle-step ${stage.tone}`} key={stage.label}>
          <span>{stage.label}</span>
          <strong>{stage.value}</strong>
          <small>{stage.detail}</small>
        </div>
      ))}
    </div>
  );
}

function MemoryDistribution({
  title,
  entries,
  labelFor,
}: {
  title: string;
  entries: Record<string, number>;
  labelFor: (value: string) => string;
}) {
  const sortedEntries = Object.entries(entries).sort((left, right) => right[1] - left[1]);
  return (
    <section className="memory-distribution">
      <h4>{title}</h4>
      {sortedEntries.length === 0 ? (
        <p>sin datos</p>
      ) : (
        <div className="memory-chip-row">
          {sortedEntries.slice(0, 6).map(([key, value]) => (
            <span className="memory-chip subtle" key={key}>
              {labelFor(key)} · {value}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function MemoryRuntimeFlow({
  events,
  onSelectRecord,
}: {
  events: AgentRuntimeEvent[];
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  const memoryEvents = events.filter(
    (event) =>
      event.kind === "memory_retrieval" ||
      event.memory_context_id !== null ||
      event.memory_record_ids.length > 0,
  );
  const visibleEvents = memoryEvents.slice(-6).reverse();

  return (
    <section className="memory-runtime-flow">
      <div>
        <h4>Runtime</h4>
        <span>{memoryEvents.length} eventos con memoria</span>
      </div>
      {visibleEvents.length === 0 ? (
        <p className="empty-state compact-empty">Sin recuperaciones en el agente seleccionado</p>
      ) : (
        <div className="memory-flow-list">
          {visibleEvents.map((event) => {
            const retrievalEvent = stringFromPayload(event.payload, "retrieval_event");
            const flowItems = memoryFlowItems(event);
            const meta = memoryFlowMeta(event);
            const query = recordFromPayload(event.payload, "query");
            const queryText = stringValue(query?.query_text);
            const citedIds = stringArrayFromPayload(event.payload, "cited_memory_record_ids");
            const ignoredIds = stringArrayFromPayload(event.payload, "ignored_memory_record_ids");
            const fallbackIds = event.memory_record_ids;
            return (
              <article className="memory-flow-event" key={event.event_id}>
                <div>
                  <strong>{retrievalEventLabel(retrievalEvent, event.kind)}</strong>
                  <span>{formatEventTime(event.created_at)} · {event.memory_context_id ?? "sin contexto"}</span>
                </div>
                {meta.length > 0 ? (
                  <div className="memory-flow-meta">
                    {meta.map((item) => (
                      <span key={`${event.event_id}-${item.label}`}>
                        {item.label}: <strong>{item.value}</strong>
                      </span>
                    ))}
                  </div>
                ) : null}
                <p>{event.summary}</p>
                {queryText ? (
                  <p className="memory-query-excerpt">{shortText(queryText, 220)}</p>
                ) : null}
                {flowItems.length > 0 ? (
                  <div className="memory-flow-items">
                    {flowItems.map((item) => (
                      <button
                        className="memory-flow-item"
                        key={`${event.event_id}-${item.memoryRecordId}`}
                        type="button"
                        onClick={() => onSelectRecord(item.memoryRecordId)}
                      >
                        <strong>
                          #{item.rank ?? "-"} · sim {formatSimilarity(item.similarity)}
                        </strong>
                        <span>{item.memoryRecordId}</span>
                        <em>
                          {roleLabel(item.memoryRole ?? "")} · {sourceTypeLabel(item.sourceType ?? "")} · {item.dataset ?? "-"}
                        </em>
                      </button>
                    ))}
                  </div>
                ) : null}
                {citedIds.length > 0 || ignoredIds.length > 0 || fallbackIds.length > 0 ? (
                  <div className="memory-chip-row">
                    {(citedIds.length > 0 ? citedIds : fallbackIds).slice(0, 4).map((memoryId) => (
                      <button
                        className="memory-chip memory-chip-button"
                        key={`${event.event_id}-cited-${memoryId}`}
                        type="button"
                        onClick={() => onSelectRecord(memoryId)}
                      >
                        usado · {memoryId}
                      </button>
                    ))}
                    {ignoredIds.slice(0, 4).map((memoryId) => (
                      <button
                        className="memory-chip subtle memory-chip-button"
                        key={`${event.event_id}-ignored-${memoryId}`}
                        type="button"
                        onClick={() => onSelectRecord(memoryId)}
                      >
                        ignorado · {memoryId}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

interface MemoryFlowItem {
  memoryRecordId: string;
  rank: number | null;
  similarity: number | null;
  memoryRole: string | null;
  sourceType: string | null;
  dataset: string | null;
}

function retrievalEventLabel(
  retrievalEvent: string | null,
  fallbackKind: AgentRuntimeEvent["kind"],
): string {
  const labels: Record<string, string> = {
    retrieval_unavailable: "RAG no disponible",
    retrieval_requested: "Consulta solicitada",
    retrieval_returned: "Contexto recuperado",
    retrieval_used: "Memoria usada",
    retrieval_rejected_by_agent: "Memoria ignorada",
  };
  return retrievalEvent === null ? kindLabel(fallbackKind) : labels[retrievalEvent] ?? retrievalEvent;
}

function memoryFlowMeta(event: AgentRuntimeEvent): { label: string; value: string }[] {
  const query = recordFromPayload(event.payload, "query");
  const items = [
    {
      label: "backend",
      value: stringFromPayload(event.payload, "retrieval_backend"),
    },
    {
      label: "embedding",
      value: stringFromPayload(event.payload, "embedding_model"),
    },
    {
      label: "top_k",
      value: stringValue(query?.top_k),
    },
    {
      label: "min_sim",
      value: stringValue(query?.min_similarity),
    },
    {
      label: "dataset",
      value: stringValue(query?.dataset),
    },
  ];
  return items.filter((item): item is { label: string; value: string } => item.value !== null);
}

function memoryFlowItems(event: AgentRuntimeEvent): MemoryFlowItem[] {
  const value = event.payload.items;
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isRecord)
    .map((item) => {
      const memoryRecordId = stringValue(item.memory_record_id);
      if (memoryRecordId === null) {
        return null;
      }
      return {
        memoryRecordId,
        rank: numberValue(item.rank),
        similarity: numberValue(item.similarity),
        memoryRole: stringValue(item.memory_role),
        sourceType: stringValue(item.source_type),
        dataset: stringValue(item.dataset),
      };
    })
    .filter((item): item is MemoryFlowItem => item !== null);
}

function formatSimilarity(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 3,
  }).format(value);
}

function shortText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}

function MemoryRecordList({
  records,
  selectedRecordId,
  usedRecordIds,
  onSelectRecord,
}: {
  records: MemoryRecordSummary[];
  selectedRecordId: string | null;
  usedRecordIds: Set<string>;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  if (records.length === 0) {
    return <p className="empty-state compact-empty">Sin recuerdos para el filtro actual</p>;
  }

  return (
    <div className="memory-record-list">
      {records.slice(0, 10).map((record) => (
        <button
          className={`memory-record-row ${record.exclude_from_context ? "excluded" : ""} ${
            usedRecordIds.has(record.memory_record_id) ? "used" : ""
          } ${
            record.memory_record_id === selectedRecordId ? "selected" : ""
          }`}
          key={record.memory_record_id}
          type="button"
          onClick={() => onSelectRecord(record.memory_record_id)}
        >
          <div>
            <strong>{record.memory_record_id}</strong>
            <span>
              {record.dataset ?? "-"} | {roleLabel(record.memory_role)} | {sourceTypeLabel(record.source_type)}
            </span>
          </div>
          <p>{record.summary}</p>
          <span className="memory-record-badges">
            {record.reusable_as_context ? <em>reutilizable</em> : null}
            {record.exclude_from_context ? <em>excluido</em> : null}
            {usedRecordIds.has(record.memory_record_id) ? <em>citado</em> : null}
          </span>
        </button>
      ))}
    </div>
  );
}

function MemoryRecordDetail({
  record,
  curating,
  onCurateRecord,
  onDeleteRecord,
}: {
  record: ReasoningMemoryRecord | null;
  curating: boolean;
  onCurateRecord: (memoryRecordId: string, action: "exclude" | "restore") => void;
  onDeleteRecord: (memoryRecordId: string) => void;
}) {
  if (record === null) {
    return null;
  }
  const metricEntries = Object.entries(record.metrics ?? {});
  const embeddingText =
    record.embedding_model === null
      ? "sin embedding"
      : `${record.embedding_model}${record.embedding_dimension ? ` · ${record.embedding_dimension} dim` : ""}`;

  return (
    <section className="memory-record-detail">
      <div className="event-head">
        <StatusPill
          ok={record.reusable_as_context && !record.exclude_from_context}
          label={recordStateLabel(record)}
          muted={!record.exclude_from_context}
        />
        <span>{verdictLabel(record.human_verdict)}</span>
      </div>
      <div className="memory-curation-actions">
        {record.exclude_from_context ? (
          <button
            type="button"
            disabled={curating}
            onClick={() => onCurateRecord(record.memory_record_id, "restore")}
          >
            Restaurar
          </button>
        ) : (
          <button
            type="button"
            disabled={curating}
            onClick={() => onCurateRecord(record.memory_record_id, "exclude")}
          >
            Excluir de RAG
          </button>
        )}
        <button
          className="danger-button"
          type="button"
          disabled={curating}
          onClick={() => onDeleteRecord(record.memory_record_id)}
        >
          Borrar
        </button>
      </div>
      <h4>{record.summary}</h4>
      <dl className="meta-list detail-meta">
        <div>
          <dt>run_id</dt>
          <dd>{record.run_id ?? "-"}</dd>
        </div>
        <div>
          <dt>decision_id</dt>
          <dd>{record.decision_id ?? "-"}</dd>
        </div>
        <div>
          <dt>origen</dt>
          <dd>{sourceTypeLabel(record.source_type)}</dd>
        </div>
        <div>
          <dt>resultado</dt>
          <dd>{outcomeLabel(record.outcome)}</dd>
        </div>
        <div>
          <dt>embedding</dt>
          <dd>{embeddingText}</dd>
        </div>
        <div>
          <dt>vector_id</dt>
          <dd>{record.vector_id ?? "-"}</dd>
        </div>
      </dl>
      {record.tags.length > 0 ? (
        <div className="memory-chip-row">
          {record.tags.slice(0, 10).map((tag) => (
            <span className="memory-chip subtle" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      {metricEntries.length > 0 ? (
        <div className="memory-metric-grid">
          {metricEntries.slice(0, 8).map(([metric, value]) => (
            <div className="memory-metric" key={metric}>
              <span>{metric}</span>
              <strong>{formatMetric(value)}</strong>
            </div>
          ))}
        </div>
      ) : null}
      <pre className="memory-content">{record.content}</pre>
      {record.source_path ? (
        <p className="memory-source-path">{record.source_path}</p>
      ) : null}
    </section>
  );
}

function RuntimeTimeline({
  events,
  onSelectAgent,
}: {
  events: AgentRuntimeEvent[];
  onSelectAgent: (agentId: string) => void;
}) {
  if (events.length === 0) {
    return <p className="empty-state">Sin eventos runtime</p>;
  }

  return (
    <div className="runtime-timeline">
      {events.slice(-40).map((event) => (
        <button
          className={`timeline-event ${event.kind === "error" ? "error" : ""}`}
          key={event.event_id}
          type="button"
          onClick={() => onSelectAgent(eventOwnerId(event))}
        >
          <span>{event.sequence}</span>
          <div>
            <strong>{event.title}</strong>
            <small>
              {formatEventTime(event.created_at)} | {sourceLabel(event)} |{" "}
              {event.stage ?? "-"}
            </small>
          </div>
        </button>
      ))}
    </div>
  );
}

function PlanView({
  response,
  description,
}: {
  response: ApiRunResponse | null;
  description: DatasetDescribeResponse | null;
}) {
  if (response === null && description === null) {
    return <p className="empty-state">Sin plan activo</p>;
  }

  const plan = response?.plan ?? null;
  const descriptor = plan?.descriptor ?? description?.descriptor ?? null;
  const adapterInfo = plan?.adapter_info ?? description?.adapter_info ?? null;
  const reviewReasons = response?.human_review_reasons ?? [];
  const responseApproval = response?.human_approval ?? null;

  return (
    <div className="plan-content">
      <div className="plan-status-row">
        {plan ? (
          <StatusPill
            ok={plan.can_execute_requested_stages}
            label={plan.can_execute_requested_stages ? "ejecutable" : "bloqueado"}
          />
        ) : (
          <StatusPill ok label="descrito" />
        )}
        <span>{adapterInfo?.display_name ?? "-"}</span>
      </div>

      {descriptor ? (
        <section className="plan-section">
          <h3>Descriptor</h3>
          <dl className="meta-list">
            <div>
              <dt>dataset_id</dt>
              <dd>{descriptor.dataset_id}</dd>
            </div>
            <div>
              <dt>formato</dt>
              <dd>{descriptor.source_format}</dd>
            </div>
            <div>
              <dt>tarea</dt>
              <dd>{descriptor.task_type}</dd>
            </div>
            <div>
              <dt>perfil</dt>
              <dd>{descriptor.supervision_profile}</dd>
            </div>
            <div>
              <dt>labels</dt>
              <dd>{descriptor.label_source}/{descriptor.label_granularity}</dd>
            </div>
            <div>
              <dt>canales</dt>
              <dd>{descriptor.channel_names.length || "-"}</dd>
            </div>
          </dl>
          {descriptor.notes.length > 0 ? (
            <ul className="plain-list note-list">
              {descriptor.notes.slice(0, 3).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {plan ? (
        <>
          <section className="plan-section">
            <h3>Fases efectivas</h3>
            <div className="stage-list">
              {plan.effective_stages.map((stage) => (
                <span className="stage-token" key={stage}>
                  {STAGE_LABELS[stage]}
                </span>
              ))}
            </div>
          </section>

          <section className="plan-section">
            <h3>Politica</h3>
            <CapabilityList capabilities={plan.policy.capabilities} />
          </section>

          {plan.blocking_reasons.length > 0 ? (
            <section className="plan-section">
              <h3>Bloqueos</h3>
              <ul className="plain-list warning-list">
                {plan.blocking_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {reviewReasons.length > 0 ? (
            <section className="plan-section">
              <h3>Revision humana</h3>
              <ul className="plain-list review-reasons">
                {reviewReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              {responseApproval ? (
                <dl className="meta-list snapshot-list">
                  <div>
                    <dt>required</dt>
                    <dd>{String(responseApproval.required)}</dd>
                  </div>
                  <div>
                    <dt>approved</dt>
                    <dd>
                      {responseApproval.approved === null
                        ? "-"
                        : String(responseApproval.approved)}
                    </dd>
                  </div>
                </dl>
              ) : null}
            </section>
          ) : null}

        </>
      ) : null}
    </div>
  );
}

function JobView({
  job,
  snapshot,
}: {
  job: ApiRunJobStatus | null;
  snapshot: RunSnapshot | null;
}) {
  if (job === null) {
    return <p className="empty-state compact-empty">Sin job en curso</p>;
  }

  return (
    <section className="plan-section job-section">
      <div className="job-heading">
        <h3>Job</h3>
        <StatusPill
          ok={job.status === "completed"}
          label={job.status}
          muted={job.status === "queued" || job.status === "running"}
        />
      </div>
      <dl className="meta-list">
        <div>
          <dt>job_id</dt>
          <dd>{job.job_id}</dd>
        </div>
        <div>
          <dt>run_id</dt>
          <dd>{job.run_id}</dd>
        </div>
        <div>
          <dt>detalle</dt>
          <dd>{job.detail ?? "-"}</dd>
        </div>
      </dl>
      {job.status === "failed" && job.detail ? (
        <p className="job-error">{job.detail}</p>
      ) : null}
      {snapshot ? (
        <dl className="meta-list snapshot-list">
          <div>
            <dt>artefactos</dt>
            <dd>{snapshot.n_artifacts}</dd>
          </div>
          <div>
            <dt>aprobada</dt>
            <dd>{snapshot.approved === null ? "-" : String(snapshot.approved)}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}

function CapabilityList({ capabilities }: { capabilities: DatasetCapabilityRule[] }) {
  return (
    <div className="capability-list">
      {capabilities.map((capability) => (
        <div className="capability-row" key={capability.stage}>
          <span>{STAGE_LABELS[capability.stage]}</span>
          <StatusPill
            ok={capability.status === "allowed"}
            label={capability.status}
            muted={capability.status === "not_supported"}
          />
        </div>
      ))}
    </div>
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

function ComparisonMetricCard({ metric }: { metric: RunComparison["metrics"][number] }) {
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

function VisualizationView({
  runs,
  selectedRunId,
  data,
  loading,
  onSelectRun,
}: {
  runs: RunIndexEntry[];
  selectedRunId: string | null;
  data: RunVisualizationData | null;
  loading: boolean;
  onSelectRun: (runId: string) => void;
}) {
  const temporalRun =
    data?.temporal_series?.available && data.temporal_series.runs.length
      ? data.temporal_series.runs[0]
      : null;
  const isRunToFailure = isRunToFailureVisualization(data);
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

      {isRunToFailure ? (
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

      {isRunToFailure ? (
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

      <section className="panel temporal-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">
              {isRunToFailure ? "Curva tecnica" : "Degradacion"}
            </p>
            <h2>{isRunToFailure ? "Ventanas y score" : "Serie temporal"}</h2>
          </div>
          <Activity size={20} />
        </div>
        {loading ? (
          <p className="empty-state compact-empty">Preparando serie temporal</p>
        ) : temporalRun ? (
          <TemporalSeriesChart run={temporalRun} />
        ) : (
          <p className="empty-state compact-empty">
            {data?.temporal_series?.warnings[0] ??
              "Sin metadatos temporales en predicciones"}
          </p>
        )}
        {data?.temporal_series?.available && data.temporal_series.n_runs_total > 1 ? (
          <p className="projection-note">
            Mostrando la primera trayectoria de {data.temporal_series.n_runs_total} runs.
          </p>
        ) : null}
      </section>

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
        {data?.projection_explanation ? (
          <p className="projection-note">{data.projection_explanation}</p>
        ) : null}
        {data?.projection_boundary ? (
          <p className="projection-note">{data.projection_boundary.note}</p>
        ) : null}
        {data?.warnings.length ? (
          <ul className="projection-warnings">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : null}
      </section>
    </section>
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
      <div className="motor-context-note">
        <p>{alertContext}</p>
        <p>{failureContext}</p>
        <p>{sourceWarning}</p>
      </div>
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
      <p className="temporal-state-note">{run.current_state_reason}</p>
      <svg
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
    </div>
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

function formatSeconds(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${formatMetric(value)} s`;
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

function LLMStatusPanel({
  active,
  status,
  onRefresh,
}: {
  active: boolean;
  status: LLMStatusResponse | null;
  onRefresh: () => void;
}) {
  const ready = status?.available === true && status.model_available === true;
  return (
    <section className={`llm-box ${active ? "active" : ""}`}>
      <div>
        <div className="llm-box-title">
          <Brain size={16} />
          <strong>{status?.model ?? "qwen3.5:4b"}</strong>
          <StatusPill
            ok={ready}
            muted={!active}
            label={active ? (ready ? "listo" : "no disponible") : "inactivo"}
          />
        </div>
        <p>{status?.host ?? "http://127.0.0.1:11434"}</p>
        {status?.detail ? <small>{status.detail}</small> : null}
      </div>
      <button
        className="icon-button"
        type="button"
        onClick={onRefresh}
        title="Actualizar estado LLM"
        aria-label="Actualizar estado LLM"
      >
        <RefreshCcw size={16} />
      </button>
    </section>
  );
}

function RunDetailView({
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

      <dl className="meta-list detail-meta">
        <div>
          <dt>errores</dt>
          <dd>{snapshot.n_errors}</dd>
        </div>
      </dl>

      <FinalReportPanel report={report} snapshot={snapshot} />

      <ExecutionAuditPanel auditReport={auditReport} />

      <ReportDebatePanel reportDebate={reportDebate} />

      <section className="registry-section evidence-section">
        <div className="section-heading">
          <div>
            <h3>Evidencia tecnica</h3>
            <p>{artifacts.length} artefactos</p>
          </div>
          <Package size={18} />
        </div>
        <ArtifactList artifacts={artifacts} />
      </section>
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
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

function ArtifactList({ artifacts }: { artifacts: ArtifactRef[] }) {
  if (artifacts.length === 0) {
    return <p className="empty-state compact-empty">Sin artefactos</p>;
  }

  return (
    <div className="artifact-list">
      {artifacts.map((artifact) => (
        <div className="artifact-row" key={`${artifact.name}-${artifact.path}`}>
          <div>
            <strong>{artifact.name}</strong>
            <span>{artifact.artifact_type} | {artifact.producer}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function FinalReportPanel({
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

function ExecutionAuditPanel({ auditReport }: { auditReport: string | null }) {
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

function ReportDebatePanel({ reportDebate }: { reportDebate: string | null }) {
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

function MarkdownDocumentPreview({
  document,
  emptyText,
  kicker,
}: {
  document: string | null;
  emptyText: string;
  kicker: string;
}) {
  if (document === null) {
    return (
      <div className="report-document empty-report-document">
        <p className="empty-state compact-empty">{emptyText}</p>
      </div>
    );
  }
  return <ReportDocument report={document} kicker={kicker} />;
}

function ReportDocument({ report, kicker }: { report: string; kicker: string }) {
  const document = useMemo(() => parseReportDocument(report, kicker), [report, kicker]);

  return (
    <article className="report-document">
      <header className="report-document-header">
        <p>{document.kicker}</p>
        <h4>{document.title}</h4>
        {document.meta.length > 0 ? (
          <dl className="report-meta-grid">
            {document.meta.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </header>

      <div className="report-section-stack">
        {document.sections.map((section) => (
          <section className="report-document-section" key={section.title}>
            <h5>{section.title}</h5>
            <ReportBlocks lines={section.lines} />
          </section>
        ))}
      </div>
    </article>
  );
}

function ReportBlocks({ lines }: { lines: string[] }) {
  const blocks = reportBlocks(lines);
  if (blocks.length === 0) {
    return <p className="empty-state compact-empty">Sin contenido visible</p>;
  }

  return (
    <>
      {blocks.map((block, index) => {
        if (block.kind === "list") {
          return (
            <ul className="report-list" key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{inlineReportText(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "subheading") {
          return <h6 key={`heading-${index}`}>{block.text}</h6>;
        }
        return <p key={`paragraph-${index}`}>{inlineReportText(block.text)}</p>;
      })}
    </>
  );
}

interface ParsedReportDocument {
  kicker: string;
  title: string;
  meta: Array<{ label: string; value: string }>;
  sections: Array<{ title: string; lines: string[] }>;
}

type ReportBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "subheading"; text: string }
  | { kind: "list"; items: string[] };

function parseReportDocument(report: string, fallbackKicker: string): ParsedReportDocument {
  const rawLines = report.split(/\r?\n/);
  const titleLine = rawLines.find((line) => line.trim().startsWith("# "));
  const title = titleLine
    ? stripMarkdown(titleLine.replace(/^#\s+/, ""))
    : "Informe tecnico de deteccion de anomalias";
  const sections: Array<{ title: string; lines: string[] }> = [];
  const introLines: string[] = [];
  let currentSection: { title: string; lines: string[] } | null = null;

  for (const rawLine of sanitizedReportLines(rawLines)) {
    const line = rawLine.trimEnd();
    if (line.startsWith("# ")) {
      continue;
    }
    if (line.startsWith("## ")) {
      currentSection = {
        title: stripMarkdown(line.replace(/^##\s+/, "")),
        lines: [],
      };
      sections.push(currentSection);
      continue;
    }
    if (currentSection) {
      currentSection.lines.push(line);
    } else {
      introLines.push(line);
    }
  }

  return {
    kicker: fallbackKicker,
    title,
    meta: reportMeta(introLines),
    sections,
  };
}

function sanitizedReportLines(lines: string[]): string[] {
  const visible: string[] = [];
  let skippingTechnicalSources = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const normalized = stripMarkdown(line).replace(/:$/, "").toLowerCase();
    if (normalized === "fuentes" || normalized === "referencias de evidencia") {
      skippingTechnicalSources = true;
      continue;
    }
    if (skippingTechnicalSources) {
      if (line === "") {
        skippingTechnicalSources = false;
      }
      continue;
    }
    if (containsLocalPath(line)) {
      continue;
    }
    visible.push(rawLine);
  }

  return visible;
}

function reportMeta(lines: string[]): Array<{ label: string; value: string }> {
  const allowedLabels = new Map([
    ["Run ID", "Run"],
    ["Dataset", "Dataset"],
    ["Objetivo", "Objetivo"],
  ]);

  return lines
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.replace(/^-\s+/, ""))
    .map((line) => {
      const separator = line.indexOf(":");
      if (separator < 0) {
        return null;
      }
      const rawLabel = stripMarkdown(line.slice(0, separator));
      const label = allowedLabels.get(rawLabel);
      if (!label) {
        return null;
      }
      const value = stripMarkdown(line.slice(separator + 1));
      return value ? { label, value } : null;
    })
    .filter((item): item is { label: string; value: string } => item !== null);
}

function reportBlocks(lines: string[]): ReportBlock[] {
  const blocks: ReportBlock[] = [];
  let pendingList: string[] = [];

  function flushList() {
    if (pendingList.length > 0) {
      blocks.push({ kind: "list", items: pendingList });
      pendingList = [];
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }
    if (line.startsWith("- ")) {
      pendingList.push(line.replace(/^-\s+/, ""));
      continue;
    }
    flushList();
    if (line.endsWith(":") && line.length < 72) {
      blocks.push({ kind: "subheading", text: stripMarkdown(line.replace(/:$/, "")) });
    } else {
      blocks.push({ kind: "paragraph", text: stripMarkdown(line) });
    }
  }
  flushList();
  return blocks;
}

function inlineReportText(value: string): string {
  return stripMarkdown(value);
}

function stripMarkdown(value: string): string {
  return value
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .trim();
}

function containsLocalPath(value: string): boolean {
  return /(^|[\s`("'[])(codigo\/|\/home\/|\.{1,2}\/|[A-Za-z]:\\)/.test(value);
}

function StatusItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="status-item">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({
  ok,
  label,
  muted = false,
}: {
  ok: boolean;
  label: string;
  muted?: boolean;
}) {
  const Icon = ok ? CheckCircle2 : muted ? AlertTriangle : XCircle;
  return (
    <span className={`status-pill ${ok ? "ok" : ""} ${muted ? "muted" : ""}`}>
      <Icon size={14} />
      {label}
    </span>
  );
}

function runStatusLabel(currentStage: string, approved: boolean | null): string {
  if (currentStage === "completed" && approved === null) {
    return "diagnostico";
  }
  return currentStage;
}

function isActiveJob(job: ApiRunJobStatus): boolean {
  return job.status === "queued" || job.status === "running";
}

function defaultRequest(adapter: DatasetAdapterInfo): ApiRunRequest {
  const defaults = DATASET_REQUEST_DEFAULTS[adapter.dataset_id] ?? {
    rawPath: "codigo/data/raw/uploads",
    executionMode: "diagnostic" as PipelineRunExecutionMode,
    datasetPolicyId: null,
    allowSyntheticLabels: false,
  };
  return {
    run_id: makeRunId(adapter.dataset_id),
    dataset_id: adapter.dataset_id,
    raw_path: defaults.rawPath,
    adapter_id: adapter.adapter_id,
    dataset_policy_id: defaults.datasetPolicyId,
    execution_mode: defaults.executionMode,
    requested_stages: null,
    use_memory: false,
    use_llm: false,
    allow_synthetic_labels: defaults.allowSyntheticLabels,
    dry_run: true,
    background: false,
    human_review: {
      mode: "off",
      reviewer: null,
      required_decision_points: [],
      passive_artifacts_enabled: true,
    },
    human_approval: null,
  };
}

function normalizedRequest(request: ApiRunRequest, customStages: boolean): ApiRunRequest {
  return {
    ...request,
    run_id: request.run_id.trim(),
    raw_path: request.raw_path.trim(),
    adapter_id: emptyToNull(request.adapter_id ?? ""),
    dataset_policy_id: emptyToNull(request.dataset_policy_id ?? ""),
    requested_stages: customStages ? request.requested_stages ?? [] : null,
    human_review: {
      ...request.human_review,
      reviewer: emptyToNull(request.human_review.reviewer ?? ""),
      required_decision_points: request.human_review.required_decision_points,
    },
    human_approval:
      request.human_approval === null
        ? null
        : {
            ...request.human_approval,
            reviewer: emptyToNull(request.human_approval.reviewer ?? ""),
            reason: emptyToNull(request.human_approval.reason ?? ""),
          },
    dry_run: true,
    background: false,
  };
}

function mergeHumanApproval(
  current: HumanApproval | null,
  next: HumanApproval,
): HumanApproval {
  return {
    ...next,
    approved: current?.approved ?? next.approved,
    reviewer: current?.reviewer ?? next.reviewer,
    reason: current?.reason ?? next.reason,
    reviewed_at: current?.reviewed_at ?? next.reviewed_at,
  };
}

function makeRunId(datasetId: string): string {
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
  return `ui-${datasetId.replace(/_/g, "-")}-${stamp}`;
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function approvalValue(value: string): boolean | null {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return null;
}

function llmStatusLabel(status: LLMStatusResponse | null): string {
  if (status === null) {
    return "-";
  }
  if (!status.available) {
    return "offline";
  }
  return status.model_available ? status.model : "sin modelo";
}

function metricLabel(metric: string): string {
  const labels: Record<string, string> = {
    precision: "Precision",
    recall: "Recall",
    f1_score: "F1",
    false_positive_rate: "FPR",
    degradation_detected_before_failure_rate: "Deteccion antes de fallo",
    degradation_mean_lead_time_to_failure: "Lead time medio",
    degradation_mean_false_alarm_rate_nominal: "FAR nominal medio",
    degradation_mean_score_trend_spearman: "Tendencia score",
    degradation_missed_runs: "Fallos perdidos",
    degradation_mean_initial_final_separation: "Separacion inicio-final",
  };
  return labels[metric] ?? metric;
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

function formatComparisonMetric(metric: string, value: number | null): string {
  if (metric.includes("lead_time")) {
    return formatSeconds(value);
  }
  return formatMetric(value);
}

function eventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
): AgentRuntimeEvent[] {
  return events.filter((event) => eventOwnerId(event) === agentId);
}

function agentConversationMessages(events: AgentRuntimeEvent[]): AgentConversationMessage[] {
  return events
    .filter(isConversationEvent)
    .map((event) => {
      const agentId = eventOwnerId(event);
      const status = conversationStatus(event);
      return {
        id: event.event_id,
        sequence: event.sequence,
        agentId,
        agentLabel: agentLabel(agentId),
        role: conversationRole(agentId),
        title: event.title,
        text: conversationText(event),
        createdAt: event.created_at,
        stage: event.stage,
        status,
        badges: conversationBadges(event),
      };
    });
}

function isConversationEvent(event: AgentRuntimeEvent): boolean {
  if (!["supervisor_decision", "agent_decision", "error"].includes(event.kind)) {
    return false;
  }
  const owner = eventOwnerId(event);
  return AGENT_PROFILES.some((agent) => agent.id === owner);
}

function eventOwnerId(event: AgentRuntimeEvent): string {
  if (event.agent_name) {
    return event.agent_name;
  }
  if (event.source === "supervisor") {
    return "supervisor";
  }
  if (event.node === "report_verifier") {
    return "report_verifier";
  }
  if (event.node?.includes("modeling")) {
    return "modeler";
  }
  if (event.node?.includes("structuring")) {
    return "structurer";
  }
  if (event.node?.includes("clean")) {
    return "cleaner";
  }
  if (event.node?.includes("evaluation") || event.node === "evaluator") {
    return "evaluator";
  }
  if (event.node?.includes("report")) {
    return "report_writer";
  }
  return "supervisor";
}

function conversationRole(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.role ?? "Agente";
}

function conversationStatus(event: AgentRuntimeEvent): AgentConversationMessage["status"] {
  if (event.kind === "error") {
    return "error";
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus === "approved") {
    return "success";
  }
  if (verificationStatus === "needs_revision" || verificationStatus === "blocked") {
    return "warning";
  }
  const evaluation = recordFromPayload(event.payload, "evaluation");
  const approved = evaluation?.approved;
  if (approved === true) {
    return "success";
  }
  if (approved === false) {
    return "warning";
  }
  return "normal";
}

function conversationText(event: AgentRuntimeEvent): string {
  if (event.kind === "error") {
    return event.summary;
  }
  const agentId = eventOwnerId(event);
  if (agentId === "supervisor") {
    return supervisorConversationText(event);
  }
  if (agentId === "cleaner") {
    const config = recordFromPayload(event.payload, "cleaning_config");
    const strategy = stringValue(config?.strategy_id);
    return strategy
      ? `Propone la estrategia de limpieza ${strategy}.`
      : conciseEventSummary(event);
  }
  if (agentId === "structurer") {
    const config = recordFromPayload(event.payload, "structuring_config");
    const windowSize = stringValue(config?.window_size);
    const featureSet = stringValue(config?.feature_set) ?? stringValue(config?.feature_mode);
    const parts = [
      windowSize ? `ventanas de ${windowSize}` : null,
      featureSet ? `features ${featureSet}` : null,
    ].filter((item): item is string => item !== null);
    return parts.length > 0
      ? `Organiza la serie temporal con ${parts.join(" y ")}.`
      : conciseEventSummary(event);
  }
  if (agentId === "modeler") {
    const config = recordFromPayload(event.payload, "modeling_config");
    const modelName = stringValue(config?.model_name);
    const threshold = stringValue(config?.threshold_quantile);
    if (modelName && threshold) {
      return `Selecciona ${modelName} con umbral cuantilico ${threshold}.`;
    }
    return modelName ? `Selecciona ${modelName} para el modelado.` : conciseEventSummary(event);
  }
  if (agentId === "evaluator") {
    const evaluation = recordFromPayload(event.payload, "evaluation");
    const summary = stringValue(evaluation?.summary);
    const approved = evaluation?.approved;
    if (summary) {
      return approved === false ? `No aprueba la run: ${summary}` : summary;
    }
    return conciseEventSummary(event);
  }
  if (agentId === "report_writer") {
    const revisionRound = stringValue(event.payload.revision_round);
    const changes = stringArrayFromPayload(event.payload, "changes_summary");
    if (revisionRound) {
      return changes.length > 0
        ? `Revisa el informe en la ronda ${revisionRound}: ${joinShortList(changes)}.`
        : `Revisa el informe en la ronda ${revisionRound}.`;
    }
    return "Prepara el informe final con las secciones y evidencias seleccionadas.";
  }
  if (agentId === "report_verifier") {
    const status = stringFromPayload(event.payload, "verification_status");
    const summary = stringFromPayload(event.payload, "human_summary") ?? event.summary;
    const corrections = stringArrayFromPayload(event.payload, "required_corrections");
    const statusText = status ? `Veredicto: ${verificationStatusLabel(status)}.` : "";
    const correctionText =
      corrections.length > 0 ? ` Pide corregir: ${joinShortList(corrections)}.` : "";
    return `${statusText} ${summary}${correctionText}`.trim();
  }
  return conciseEventSummary(event);
}

function supervisorConversationText(event: AgentRuntimeEvent): string {
  const stopReason = stringFromNestedPayload(event.payload, "decision", "stop_reason");
  if (stopReason) {
    return `Cierra la ejecucion: ${stopReason}.`;
  }
  const next = event.next_node ?? event.next_stage;
  if (next) {
    return `Decide continuar hacia ${readableFlowLabel(next)}.`;
  }
  return conciseEventSummary(event);
}

function conversationBadges(event: AgentRuntimeEvent): string[] {
  const badges: string[] = [];
  if (event.stage) {
    badges.push(STAGE_LABELS[event.stage as PipelineRunStage] ?? readableFlowLabel(event.stage));
  }
  if (event.confidence !== null) {
    badges.push(confidenceText(event.confidence));
  }
  if (event.memory_record_ids.length > 0) {
    badges.push(`${event.memory_record_ids.length} memoria`);
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus) {
    badges.push(verificationStatusLabel(verificationStatus));
  }
  const next = event.next_node ?? event.next_stage;
  if (eventOwnerId(event) === "supervisor" && next) {
    badges.push(`sigue: ${readableFlowLabel(next)}`);
  }
  return badges.slice(0, 4);
}

function conciseEventSummary(event: AgentRuntimeEvent): string {
  return event.summary.length > 220 ? `${event.summary.slice(0, 217)}...` : event.summary;
}

function readableFlowLabel(value: string): string {
  const labels: Record<string, string> = {
    manifest_executor: "manifest",
    profiler_executor: "perfilado",
    cleaner_agent: "limpiador",
    cleaning_executor: "ejecutor de limpieza",
    structuring_agent: "estructurador",
    structuring_executor: "ejecutor de estructuracion",
    modeling_agent: "modelador",
    modeling_executor: "ejecutor de modelado",
    evaluation_executor: "ejecutor de evaluacion",
    evaluation_agent: "evaluador",
    report_writer: "redactor",
    report_verifier: "verificador",
  };
  return labels[value] ?? value.replace(/_/g, " ");
}

function verificationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    approved: "aprobado",
    needs_revision: "requiere revision",
    blocked: "bloqueado",
  };
  return labels[status] ?? status;
}

function agentInitials(label: string): string {
  return label
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function recordFromPayload(
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = payload[key];
  return isRecord(value) ? value : null;
}

function stringFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return stringValue(payload[key]);
}

function stringFromNestedPayload(
  payload: Record<string, unknown>,
  key: string,
  nestedKey: string,
): string | null {
  return stringValue(recordFromPayload(payload, key)?.[nestedKey]);
}

function stringArrayFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string[] {
  const value = payload[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => stringValue(item))
    .filter((item): item is string => item !== null);
}

function stringValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function joinShortList(values: string[]): string {
  const visible = values.slice(0, 2);
  const suffix = values.length > visible.length ? ` y ${values.length - visible.length} mas` : "";
  return `${visible.join("; ")}${suffix}`;
}

function memoryTargetForAgent(agentId: string): AgentMemoryTarget {
  if (
    agentId === "cleaner" ||
    agentId === "structurer" ||
    agentId === "modeler" ||
    agentId === "evaluator" ||
    agentId === "report_writer"
  ) {
    return agentId;
  }
  return "shared_methodology";
}

function agentLabel(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.label ?? agentId;
}

function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    positive_example: "positivo",
    negative_example: "negativo",
    boundary_case: "frontera",
    warning: "advertencia",
    methodology: "metodologia",
    evidence: "evidencia",
    excluded: "excluido",
  };
  return labels[role] ?? role;
}

function sourceTypeLabel(sourceType: string): string {
  const labels: Record<string, string> = {
    decision_episode: "episodio",
    memory_candidate: "candidato",
    reasoning_postmortem: "post-mortem",
    human_review: "revision humana",
    memory_usage_audit: "auditoria",
    experiment_summary: "experimento",
    technical_documentation: "documentacion",
    methodology_note: "metodologia",
  };
  return labels[sourceType] ?? sourceType;
}

function outcomeLabel(outcome: string | null): string {
  const labels: Record<string, string> = {
    validated: "validado",
    supported: "soportado",
    partially_supported: "parcial",
    overcorrected: "sobrecorregido",
    contradicted: "contradicho",
    inconclusive: "inconcluso",
  };
  return outcome === null ? "-" : labels[outcome] ?? outcome;
}

function verdictLabel(verdict: string | null): string {
  const labels: Record<string, string> = {
    correct: "correcto",
    partially_correct: "parcial",
    incorrect: "incorrecto",
    unsafe: "inseguro",
    needs_more_evidence: "mas evidencia",
  };
  return verdict === null ? "sin veredicto" : labels[verdict] ?? verdict;
}

function recordStateLabel(record: MemoryRecordSummary): string {
  if (record.exclude_from_context || record.memory_role === "excluded") {
    return "excluido";
  }
  if (record.reusable_as_context) {
    return "recuperable";
  }
  return "indexado";
}

function kindLabel(kind: AgentRuntimeEvent["kind"]): string {
  const labels: Record<AgentRuntimeEvent["kind"], string> = {
    job_status: "Job",
    supervisor_decision: "Supervisor",
    agent_decision: "Decision",
    memory_retrieval: "Memoria",
    executor_result: "Ejecutor",
    error: "Error",
  };
  return labels[kind];
}

function agentEventPlainText(event: AgentRuntimeEvent): string {
  const actor = event.agent_name ? agentLabel(event.agent_name) : sourceLabel(event);
  const stage = event.stage ? ` durante ${STAGE_LABELS[event.stage as PipelineRunStage] ?? event.stage}` : "";
  const confidence =
    event.confidence === null ? "" : ` con confianza ${confidenceText(event.confidence)}`;
  const next = event.next_node ?? event.next_stage;
  const nextText = next ? ` y propone continuar hacia ${next}` : "";
  const memoryText =
    event.memory_record_ids.length > 0
      ? ` usando ${event.memory_record_ids.length} recuerdo(s) como contexto`
      : "";
  const payloadText = payloadPlainText(event.payload);

  if (event.kind === "memory_retrieval") {
    return `${actor} recupera memoria${stage}${memoryText}. ${payloadText}`;
  }
  if (event.kind === "executor_result") {
    return `${actor} registra el resultado del ejecutor${stage}. ${payloadText}`;
  }
  if (event.kind === "supervisor_decision" || event.kind === "agent_decision") {
    return `${actor} toma una decision${stage}${confidence}${nextText}${memoryText}. ${payloadText}`;
  }
  if (event.kind === "error") {
    return `${actor} informa de un error${stage}. ${event.summary}`;
  }
  return `${actor} actualiza el estado del job. ${event.summary}`;
}

function payloadPlainText(payload: Record<string, unknown>): string {
  const candidates = [
    ["model_name", "modelo"],
    ["strategy_id", "estrategia"],
    ["decision_id", "decision"],
    ["status", "estado"],
    ["verification_status", "verificacion"],
    ["debate_round", "ronda"],
    ["human_summary", "resumen"],
    ["message", "mensaje"],
    ["n_records", "recuerdos"],
    ["n_artifacts", "artefactos"],
    ["n_unsupported_claims", "claims sin soporte"],
    ["n_misleading_claims", "claims confusos"],
    ["n_missing_limitations", "limitaciones ausentes"],
    ["threshold", "umbral"],
  ];
  const fragments = candidates
    .map(([key, label]) =>
      payload[key] === undefined ? null : `${label}: ${String(payload[key])}`,
    )
    .filter((item): item is string => item !== null);
  for (const key of ["required_corrections", "changes_summary"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "required_corrections" ? "correcciones" : "cambios"}: ${value.length}`);
    }
  }
  for (const key of ["accepted_issue_ids", "rejected_issue_ids"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "accepted_issue_ids" ? "incidencias aceptadas" : "incidencias rechazadas"}: ${value.length}`);
    }
  }
  return fragments.length > 0
    ? `Campos clave: ${fragments.join(", ")}.`
    : "El JSON adjunto contiene el detalle tecnico completo.";
}

function sourceLabel(event: AgentRuntimeEvent): string {
  if (event.agent_name) {
    return agentLabel(event.agent_name);
  }
  return kindLabel(event.kind);
}

function confidenceText(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function errorText(caught: unknown): string {
  if (caught instanceof ApiClientError) {
    return caught.message;
  }
  if (caught instanceof Error) {
    return caught.message;
  }
  return "Error desconocido";
}

function formatMetric(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 3,
  }).format(value);
}

function scaleFor(values: number[], outputMin: number, outputMax: number) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return (value: number) => outputMin + ((value - min) / span) * (outputMax - outputMin);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatEventTime(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
