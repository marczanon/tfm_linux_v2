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
  describeDataset,
  getHealth,
  getLLMStatus,
  getRun,
  getRunArtifacts,
  getRunJob,
  getRunReport,
  getRunVisualization,
  getMemoryRecord,
  listDatasetAdapters,
  listMemoryCollections,
  listMemoryRecords,
  listRuns,
} from "./api";
import type {
  AgentRuntimeEvent,
  AgentMemoryTarget,
  ArtifactRef,
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  DatasetCapabilityRule,
  DatasetAdapterInfo,
  DatasetDescribeResponse,
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
    rawPath: "codigo/data/raw/nasa_ims_bearing",
    executionMode: "diagnostic",
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
      const [snapshot, artifacts, report, visualization] = await Promise.all([
        getRun(runId),
        getRunArtifacts(runId),
        getRunReport(runId).catch((caught) => {
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
          reusable_only: true,
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
          selectedCompareRunIds={selectedCompareRunIds}
          selectedReport={selectedReport}
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
          onMemorySearchChange={setMemorySearchText}
          onSelectMemoryRecord={(memoryRecordId) => void loadMemoryRecord(memoryRecordId)}
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
  selectedCompareRunIds,
  selectedReport,
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
  selectedCompareRunIds: string[];
  selectedReport: string | null;
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
        selectedCompareRunIds={selectedCompareRunIds}
        selectedReport={selectedReport}
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
  selectedCompareRunIds,
  selectedReport,
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
  selectedCompareRunIds: string[];
  selectedReport: string | null;
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
  onMemorySearchChange,
  onSelectMemoryRecord,
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
  onMemorySearchChange: (value: string) => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
}) {
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const selectedEvents = eventsForAgent(events, selectedAgentId);
  const selectedEvent =
    selectedEvents.length > 0 ? selectedEvents[selectedEvents.length - 1] : null;

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
        <AgentRuntimeDetail event={selectedEvent} eventCount={selectedEvents.length} />
        <AgentMemoryPanel
          agentId={selectedAgentId}
          collections={memoryCollections}
          records={memoryRecords}
          selectedRecord={selectedMemoryRecord}
          searchText={memorySearchText}
          loading={loadingMemory}
          onSearchChange={onMemorySearchChange}
          onSelectRecord={onSelectMemoryRecord}
        />
      </section>

      <section className="panel timeline-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Comunicacion</p>
            <h2>Timeline</h2>
          </div>
          <MessageSquare size={20} />
        </div>
        <RuntimeTimeline events={events} onSelectAgent={onSelectAgent} />
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
}: {
  event: AgentRuntimeEvent | null;
  eventCount: number;
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
              <span className="memory-chip" key={memoryId}>
                {memoryId}
              </span>
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

function AgentMemoryPanel({
  agentId,
  collections,
  records,
  selectedRecord,
  searchText,
  loading,
  onSearchChange,
  onSelectRecord,
}: {
  agentId: string;
  collections: MemoryCollectionSummary[];
  records: MemoryRecordSummary[];
  selectedRecord: ReasoningMemoryRecord | null;
  searchText: string;
  loading: boolean;
  onSearchChange: (value: string) => void;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  const target = memoryTargetForAgent(agentId);
  const collection = collections.find((item) => item.target_agent === target) ?? null;

  return (
    <section className="runtime-block memory-panel">
      <div className="section-heading">
        <div>
          <h3>Memoria persistida</h3>
          <p>{collection?.collection_name ?? target}</p>
        </div>
        <StatusPill
          ok={(collection?.n_records ?? 0) > 0}
          label={`${collection?.n_records ?? 0} recuerdos`}
          muted={(collection?.n_records ?? 0) === 0}
        />
      </div>

      <div className="memory-summary-grid">
        <MiniStat label="Reutilizables" value={collection?.n_reusable ?? 0} />
        <MiniStat label="Datasets" value={collection?.datasets.length ?? 0} />
        <MiniStat label="Excluidos" value={collection?.n_excluded ?? 0} />
      </div>

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
          onSelectRecord={onSelectRecord}
        />
      )}

      <MemoryRecordDetail record={selectedRecord} />
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="mini-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MemoryRecordList({
  records,
  selectedRecordId,
  onSelectRecord,
}: {
  records: MemoryRecordSummary[];
  selectedRecordId: string | null;
  onSelectRecord: (memoryRecordId: string) => void;
}) {
  if (records.length === 0) {
    return <p className="empty-state compact-empty">Sin recuerdos recuperados</p>;
  }

  return (
    <div className="memory-record-list">
      {records.slice(0, 8).map((record) => (
        <button
          className={`memory-record-row ${
            record.memory_record_id === selectedRecordId ? "selected" : ""
          }`}
          key={record.memory_record_id}
          type="button"
          onClick={() => onSelectRecord(record.memory_record_id)}
        >
          <div>
            <strong>{record.memory_record_id}</strong>
            <span>{record.dataset ?? "-"} | {roleLabel(record.memory_role)}</span>
          </div>
          <p>{record.summary}</p>
        </button>
      ))}
    </div>
  );
}

function MemoryRecordDetail({ record }: { record: ReasoningMemoryRecord | null }) {
  if (record === null) {
    return null;
  }

  return (
    <section className="memory-record-detail">
      <div className="event-head">
        <StatusPill ok={record.reusable_as_context} label={roleLabel(record.memory_role)} />
        <span>{record.human_verdict ?? "sin_veredicto"}</span>
      </div>
      <dl className="meta-list detail-meta">
        <div>
          <dt>run_id</dt>
          <dd>{record.run_id ?? "-"}</dd>
        </div>
        <div>
          <dt>decision_id</dt>
          <dd>{record.decision_id ?? "-"}</dd>
        </div>
      </dl>
      <pre className="memory-content">{record.content}</pre>
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
                  label={run.current_stage}
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
        <div className="comparison-grid">
          {comparison.metrics.map((metric) => (
            <div className="comparison-card" key={metric.metric}>
              <span>{metricLabel(metric.metric)}</span>
              <strong>{metric.best_run_id ?? "-"}</strong>
              <small>
                mejor {formatMetric(metric.best_value)} | peor{" "}
                {formatMetric(metric.worst_value)} | dif. {formatMetric(metric.spread)}
              </small>
            </div>
          ))}
        </div>
      ) : null}
    </section>
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
            <p className="eyebrow">Metricas</p>
            <h2>Rendimiento</h2>
          </div>
          <BarChart3 size={20} />
        </div>
        {loading ? (
          <p className="empty-state compact-empty">Cargando visualizacion</p>
        ) : data ? (
          <MetricBars metrics={data.metrics} />
        ) : (
          <p className="empty-state compact-empty">Sin run seleccionada</p>
        )}
      </section>

      <section className="panel projection-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Espacio 2D</p>
            <h2>Agrupacion y anomalias</h2>
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
        {data?.projection_boundary ? (
          <p className="projection-note">{data.projection_boundary.note}</p>
        ) : null}
      </section>
    </section>
  );
}

function MetricBars({ metrics }: { metrics: VisualizationMetric[] }) {
  const visible = metrics.filter((metric) => metric.value !== null);
  if (visible.length === 0) {
    return <p className="empty-state compact-empty">Sin metricas numericas</p>;
  }

  return (
    <div className="metric-bars">
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
        <span><i className="legend-normal" /> normal/prediccion 0</span>
        <span><i className="legend-anomaly" /> anomalia detectada</span>
        <span><i className="legend-boundary" /> frontera aproximada</span>
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
  loading,
}: {
  entry: RunIndexEntry | null;
  snapshot: RunSnapshot | null;
  artifacts: ArtifactRef[];
  report: string | null;
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
          label={snapshot.current_stage}
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

      <section className="registry-section">
        <div className="section-heading">
          <div>
            <h3>Artefactos</h3>
            <p>{artifacts.length} generados</p>
          </div>
          <Package size={18} />
        </div>
        <ArtifactList artifacts={artifacts} />
      </section>

      <section className="registry-section">
        <div className="section-heading">
          <div>
            <h3>Informe</h3>
            <p>{report ? "Informe generado" : "Sin informe disponible"}</p>
          </div>
          <FileText size={18} />
        </div>
        <ReportPreview report={report} />
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

function ReportPreview({ report }: { report: string | null }) {
  if (report === null) {
    return <p className="empty-state compact-empty">Sin informe disponible</p>;
  }
  return <pre className="report-preview">{report}</pre>;
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
  };
  return labels[metric] ?? metric;
}

function eventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
): AgentRuntimeEvent[] {
  return events.filter((event) => eventOwnerId(event) === agentId);
}

function eventOwnerId(event: AgentRuntimeEvent): string {
  if (event.agent_name) {
    return event.agent_name;
  }
  if (event.source === "supervisor") {
    return "supervisor";
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
    ["message", "mensaje"],
    ["n_records", "recuerdos"],
    ["n_artifacts", "artefactos"],
    ["threshold", "umbral"],
  ];
  const fragments = candidates
    .map(([key, label]) =>
      payload[key] === undefined ? null : `${label}: ${String(payload[key])}`,
    )
    .filter((item): item is string => item !== null);
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
