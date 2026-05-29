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
  getRun,
  getRunArtifacts,
  getRunJob,
  getRunReport,
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
  MemoryCollectionSummary,
  MemoryRecordSummary,
  PipelineRunExecutionMode,
  PipelineRunStage,
  ReasoningMemoryRecord,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunSnapshot,
} from "./types";

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

type AppView = "pipeline" | "agents";

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
  const [adapters, setAdapters] = useState<DatasetAdapterInfo[]>([FALLBACK_ADAPTER]);
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [runFilters, setRunFilters] = useState<RunFilters>(DEFAULT_RUN_FILTERS);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<RunSnapshot | null>(null);
  const [selectedArtifacts, setSelectedArtifacts] = useState<ArtifactRef[]>([]);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
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
  const canExecutePlan =
    planResponse?.plan.can_execute_requested_stages === true &&
    approvalReady &&
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
      const [healthPayload, runsPayload, adaptersPayload] = await Promise.all([
        getHealth(),
        listRuns(runFilters),
        listDatasetAdapters(),
      ]);
      setHealth(healthPayload);
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
    setError(null);
    try {
      const [snapshot, artifacts, report] = await Promise.all([
        getRun(runId),
        getRunArtifacts(runId),
        getRunReport(runId).catch((caught) => {
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
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingRunDetail(false);
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

  function selectAgent(agentId: string) {
    setSelectedAgentId(agentId);
    setSelectedMemoryRecord(null);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Fase 5</p>
          <h1>TFM Pipeline</h1>
        </div>
        <div className="topbar-actions">
          <StatusPill ok={health?.status === "ok"} label={health?.status ?? "offline"} />
          <button
            className="icon-button"
            type="button"
            onClick={() => void refreshDashboard()}
            disabled={loadingDashboard}
            title="Actualizar panel"
            aria-label="Actualizar panel"
          >
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      {error ? (
        <section className="alert" role="alert">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </section>
      ) : null}

      <section className="status-band" aria-label="Estado operativo">
        <StatusItem icon={<Server size={18} />} label="API" value={health?.status ?? "-"} />
        <StatusItem icon={<Database size={18} />} label="Adaptadores" value={adapters.length.toString()} />
        <StatusItem icon={<Database size={18} />} label="Runs" value={runs.length.toString()} />
        <StatusItem icon={<CheckCircle2 size={18} />} label="Completadas" value={completedRuns.toString()} />
        <StatusItem icon={<Activity size={18} />} label="Aprobadas" value={approvedRuns.toString()} />
      </section>

      <ViewTabs activeView={activeView} onChange={setActiveView} />

      {activeView === "pipeline" ? (
      <section className="workspace">
        <form className="panel run-form" onSubmit={(event) => void submitDryRun(event)}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Preflight</p>
              <h2>Nueva run</h2>
            </div>
            <div className="panel-actions">
              <button className="secondary-button" type="submit" disabled={planning || executing}>
                <FileSearch size={17} />
                {planning ? "Planificando" : "Planificar"}
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={!canExecutePlan}
                onClick={() => void executeBackgroundRun()}
              >
                <Play size={17} />
                {executing || activeJob ? "Ejecutando" : "Ejecutar"}
              </button>
            </div>
          </div>

          <label className="field">
            <span>Adaptador</span>
            <select
              value={selectedAdapterId}
              onChange={(event) => applyAdapter(event.target.value)}
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

          <label className="field">
            <span>Run ID</span>
            <input
              value={request.run_id}
              onChange={(event) => updateRequest("run_id", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Ruta raw</span>
            <input
              value={request.raw_path}
              onChange={(event) => updateRequest("raw_path", event.target.value)}
            />
          </label>

          <div className="form-row">
            <label className="field">
              <span>Modo</span>
              <select
                value={request.execution_mode}
                onChange={(event) =>
                  updateRequest("execution_mode", event.target.value as ApiRunRequest["execution_mode"])
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
                  updateHumanReviewMode(event.target.value as HumanReviewMode)
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
            onReviewerChange={updateHumanReviewer}
            onTogglePoint={toggleHumanReviewPoint}
            onApprovalChange={updateHumanApproval}
          />

          <div className="form-row">
            <label className="field">
              <span>Adapter ID</span>
              <input
                value={request.adapter_id ?? ""}
                onChange={(event) => updateRequest("adapter_id", emptyToNull(event.target.value))}
              />
            </label>

            <label className="field">
              <span>Policy ID</span>
              <input
                value={request.dataset_policy_id ?? ""}
                onChange={(event) =>
                  updateRequest("dataset_policy_id", emptyToNull(event.target.value))
                }
              />
            </label>
          </div>

          <div className="toggle-stack">
            <label className="switch-row">
              <input
                type="checkbox"
                checked={request.use_memory}
                onChange={(event) => updateRequest("use_memory", event.target.checked)}
              />
              <span>Memoria local</span>
            </label>
            <label className="switch-row">
              <input
                type="checkbox"
                checked={request.use_llm}
                onChange={(event) => updateRequest("use_llm", event.target.checked)}
              />
              <span>Agentes LLM</span>
            </label>
            <label className="switch-row">
              <input
                type="checkbox"
                checked={request.allow_synthetic_labels}
                onChange={(event) =>
                  updateRequest("allow_synthetic_labels", event.target.checked)
                }
              />
              <span>Etiquetas sinteticas</span>
            </label>
          </div>

          <section className="stage-section">
            <label className="switch-row">
              <input
                type="checkbox"
                checked={customStages}
                onChange={(event) => {
                  setCustomStages(event.target.checked);
                  updateRequest("requested_stages", event.target.checked ? [] : null);
                }}
              />
              <span>Fases manuales</span>
            </label>
            <div className="stage-grid" aria-disabled={!customStages}>
              {PIPELINE_STAGES.map((stage) => (
                <label className="stage-toggle" key={stage}>
                  <input
                    type="checkbox"
                    checked={(request.requested_stages ?? []).includes(stage)}
                    onChange={() => toggleStage(stage)}
                    disabled={!customStages}
                  />
                  <span>{STAGE_LABELS[stage]}</span>
                </label>
              ))}
            </div>
          </section>
        </form>

        <section className="panel plan-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Plan</p>
              <h2>Dry run</h2>
            </div>
            <FileSearch size={20} />
          </div>
          <PlanView response={planResponse} description={datasetDescription} />
          <JobView job={job} snapshot={jobSnapshot} />
        </section>

        <section className="panel runs-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Registro</p>
              <h2>Runs locales</h2>
            </div>
            <div className="panel-actions">
              <button
                className="icon-button"
                type="button"
                onClick={resetRunFilters}
                title="Limpiar filtros"
                aria-label="Limpiar filtros"
              >
                <RefreshCcw size={17} />
              </button>
              <ListChecks size={20} />
            </div>
          </div>
          <RunFiltersView
            filters={runFilters}
            adapters={adapters}
            onChange={updateRunFilter}
          />
          <RunsTable
            runs={visibleRuns}
            selectedRunId={selectedRunId}
            selectedCompareRunIds={selectedCompareRunIds}
            onSelectRun={(runId) => void loadRunDetail(runId)}
            onToggleCompare={toggleCompareRun}
          />
          <ComparisonView
            selectedCount={selectedCompareRunIds.length}
            comparison={runComparison}
            loading={comparingRuns}
            onCompare={() => void submitRunComparison()}
          />
          <RunDetailView
            entry={selectedRunEntry}
            snapshot={selectedSnapshot}
            artifacts={selectedArtifacts}
            report={selectedReport}
            loading={loadingRunDetail}
          />
        </section>
      </section>
      ) : (
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
      )}
    </main>
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
        <div>
          <dt>source</dt>
          <dd>{record.source_path ?? "-"}</dd>
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

          <section className="plan-section">
            <h3>Rutas</h3>
            <dl className="path-list">
              {Object.entries(plan.paths).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </section>
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
    return null;
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
            <dt>snapshot</dt>
            <dd>{snapshot.snapshot_dir}</dd>
          </div>
          <div>
            <dt>informe</dt>
            <dd>{snapshot.report_path ?? "-"}</dd>
          </div>
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
          <dt>snapshot</dt>
          <dd>{snapshot.snapshot_dir}</dd>
        </div>
        <div>
          <dt>informe</dt>
          <dd>{snapshot.report_path ?? "-"}</dd>
        </div>
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
            <p>{snapshot.report_path ?? "sin informe"}</p>
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
          <code>{artifact.path}</code>
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
