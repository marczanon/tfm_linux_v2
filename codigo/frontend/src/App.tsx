import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

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
  getRunEvents,
  getRunJob,
  getRunReport,
  getRunReportDebate,
  getRunVisualization,
  getMemoryRecord,
  listDatasetAdapters,
  listMemoryCollections,
  getMemoryStatus,
  listMemoryRecords,
  listRuns,
} from "./api";
import { AgentObservabilityView } from "./components/agents/AgentObservabilityView";
import { CockpitView } from "./components/cockpit/CockpitView";
import { PipelineDashboard } from "./components/pipeline/PipelineDashboard";
import { MonitoringView } from "./components/monitoring/MonitoringView";
import { RunContextBand } from "./components/runs/RunContextBand";
import { AppShell } from "./components/shell/AppShell";
import { VisualizationView } from "./components/visualization/VisualizationView";
import { FALLBACK_ADAPTER } from "./constants/datasets";
import { DEFAULT_RUN_FILTERS } from "./constants/pipeline";
import { emptyToNull } from "./lib/forms";
import { isActiveJob } from "./lib/jobs";
import { memoryTargetForAgent } from "./lib/memoryRecords";
import {
  defaultRequest,
  mergeHumanApproval,
  normalizedRequest,
} from "./lib/runRequest";
import type {
  ArtifactRef,
  AgentRuntimeEvent,
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  DatasetAdapterInfo,
  DatasetDescribeResponse,
  HealthResponse,
  HumanApproval,
  HumanReviewMode,
  LLMStatusResponse,
  MemoryCollectionSummary,
  MemoryStatusResponse,
  MemoryRecordSummary,
  PipelineRunStage,
  ReasoningMemoryRecord,
  RunComparison,
  RunFilters,
  RunIndexEntry,
  RunVisualizationData,
  RunSnapshot,
} from "./types";
import type {
  AppView,
  MonitoringAgentBridgeContext,
} from "./types/ui";

export default function App() {
  const [activeView, setActiveView] = useState<AppView>("cockpit");
  const [pipelineContextMode, setPipelineContextMode] = useState<"request" | "selected">("request");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMStatusResponse | null>(null);
  const [adapters, setAdapters] = useState<DatasetAdapterInfo[]>([FALLBACK_ADAPTER]);
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [runFilters, setRunFilters] = useState<RunFilters>(DEFAULT_RUN_FILTERS);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<RunSnapshot | null>(null);
  const [selectedArtifacts, setSelectedArtifacts] = useState<ArtifactRef[]>([]);
  const [selectedRunEvents, setSelectedRunEvents] = useState<AgentRuntimeEvent[]>([]);
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
  const [jobRequest, setJobRequest] = useState<ApiRunRequest | null>(null);
  const [jobSnapshot, setJobSnapshot] = useState<RunSnapshot | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("supervisor");
  const [monitoringAgentContext, setMonitoringAgentContext] =
    useState<MonitoringAgentBridgeContext | null>(null);
  const [monitoringChildJob, setMonitoringChildJob] =
    useState<ApiRunJobStatus | null>(null);
  const [memoryCollections, setMemoryCollections] = useState<MemoryCollectionSummary[]>([]);
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatusResponse | null>(null);
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
  const cockpitFocusAttemptRef = useRef<string | null>(null);

  const visibleRuns = useMemo(() => runs.slice(0, 20), [runs]);
  const focusedJob = useMemo(
    () => (job !== null && job.run_id === selectedRunId ? job : null),
    [job, selectedRunId],
  );
  const focusedSnapshot =
    focusedJob !== null && isActiveJob(focusedJob) ? null : selectedSnapshot;
  const runtimeEvents = useMemo(() => {
    if (focusedJob !== null && (isActiveJob(focusedJob) || focusedJob.events.length > 0)) {
      return focusedJob.events;
    }
    return selectedRunEvents;
  }, [focusedJob, selectedRunEvents]);
  const monitoringChildSnapshot =
    monitoringAgentContext !== null &&
    selectedSnapshot?.run_id === monitoringAgentContext.childRunId
      ? selectedSnapshot
      : null;
  const monitoringChildEvents = useMemo(() => {
    if (monitoringAgentContext === null) {
      return [];
    }
    if (
      monitoringChildJob !== null &&
      (isActiveJob(monitoringChildJob) || selectedRunEvents.length === 0)
    ) {
      return monitoringChildJob.events;
    }
    return selectedRunEvents;
  }, [monitoringAgentContext, monitoringChildJob, selectedRunEvents]);
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
    if (activeView !== "cockpit" || loadingRunDetail) {
      return;
    }
    const latestRunId = runs[0]?.run_id;
    if (!latestRunId) {
      return;
    }
    const focusAlreadyLoaded =
      selectedRunId === latestRunId && selectedSnapshot?.run_id === latestRunId;
    if (focusAlreadyLoaded) {
      return;
    }
    if (cockpitFocusAttemptRef.current === latestRunId) {
      return;
    }
    cockpitFocusAttemptRef.current = latestRunId;
    void loadRunDetail(latestRunId);
  }, [
    activeView,
    loadingRunDetail,
    runs,
    selectedRunId,
    selectedSnapshot?.run_id,
  ]);

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
    if (
      activeView !== "agents" ||
      monitoringAgentContext === null ||
      monitoringChildJob === null ||
      !isActiveJob(monitoringChildJob)
    ) {
      return;
    }

    let cancelled = false;

    async function pollMonitoringChildJob() {
      try {
        const next = await getRunJob(monitoringAgentContext!.childRunId);
        if (cancelled) {
          return;
        }
        assertMonitoringChildRunIdentity(next, monitoringAgentContext!);
        setMonitoringChildJob(next);
        if (next.status === "completed") {
          await loadRunDetail(next.run_id);
        } else if (next.status === "failed") {
          setError(next.detail ?? "La run hija de monitorización ha fallado.");
        }
      } catch (caught) {
        if (!cancelled) {
          setError(errorText(caught));
        }
      }
    }

    const intervalId = window.setInterval(
      () => void pollMonitoringChildJob(),
      1500,
    );
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    activeView,
    monitoringAgentContext?.childRunId,
    monitoringChildJob?.job_id,
    monitoringChildJob?.status,
  ]);

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
    cockpitFocusAttemptRef.current = null;
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
    setJobRequest(null);
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
      setJobRequest(normalized);
      setJob(response.job);
      setSelectedRunId(response.job.run_id);
      setSelectedSnapshot(null);
      setSelectedArtifacts([]);
      setSelectedRunEvents([]);
      setSelectedReport(null);
      setSelectedAuditReport(null);
      setSelectedReportDebate(null);
      setSelectedVisualization(null);
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
      const [snapshot, artifacts, events, report, auditReport, reportDebate, visualization] = await Promise.all([
        getRun(runId),
        getRunArtifacts(runId),
        getRunEvents(runId).catch((caught) => {
          if (caught instanceof ApiClientError && caught.status === 404) {
            return [];
          }
          throw caught;
        }),
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
      setSelectedRunEvents(events);
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
      const [statusPayload, collectionsPayload, recordsPayload] = await Promise.all([
        getMemoryStatus(),
        listMemoryCollections(),
        listMemoryRecords({
          target_agent: targetAgent,
          search_text: emptyToNull(memorySearchText),
        }),
      ]);
      setMemoryStatus(statusPayload);
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
      "Excluir y borrar este recuerdo del indice configurado? Se conservara un tombstone auditable y no se eliminaran los artefactos fuente.",
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
    if (job !== null && isActiveJob(job)) {
      setError("La configuracion queda bloqueada mientras la ejecucion esta activa.");
      return;
    }
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
    setJobRequest(null);
    setJobSnapshot(null);
  }

  function updateRequest<Key extends keyof ApiRunRequest>(
    key: Key,
    value: ApiRunRequest[Key],
  ) {
    if (job !== null && isActiveJob(job)) {
      setError("La configuracion queda bloqueada mientras la ejecucion esta activa.");
      return;
    }
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

  function clearSelectedRunDetail(runId: string) {
    setSelectedRunId(runId);
    setSelectedSnapshot(null);
    setSelectedArtifacts([]);
    setSelectedRunEvents([]);
    setSelectedReport(null);
    setSelectedAuditReport(null);
    setSelectedReportDebate(null);
    setSelectedVisualization(null);
  }

  async function openMonitoringAgentRun(context: MonitoringAgentBridgeContext) {
    setMonitoringAgentContext(context);
    setMonitoringChildJob(null);
    setSelectedAgentId("supervisor");
    setSelectedMemoryRecord(null);
    clearSelectedRunDetail(context.childRunId);
    setError(null);
    setActiveView("agents");

    try {
      const childJob = await getRunJob(context.childRunId);
      assertMonitoringChildRunIdentity(childJob, context);
      setMonitoringChildJob(childJob);
      if (childJob.status === "completed") {
        await loadRunDetail(childJob.run_id);
      } else if (childJob.status === "failed") {
        setError(childJob.detail ?? "La run hija de monitorización ha fallado.");
      }
    } catch (caught) {
      if (caught instanceof ApiClientError && caught.status === 404) {
        try {
          await loadRunDetail(context.childRunId);
          return;
        } catch (persistedError) {
          setError(errorText(persistedError));
          return;
        }
      }
      setError(errorText(caught));
    }
  }

  function returnToMonitoringTrigger() {
    setActiveView("monitoring");
  }

  function finishMonitoringBridgeRestore() {
    setMonitoringAgentContext(null);
    setMonitoringChildJob(null);
  }

  function openRunInView(runId: string, view: AppView) {
    if (view === "pipeline") {
      setPipelineContextMode("selected");
    }
    setActiveView(view);
    void loadRunDetail(runId);
  }

  function changeView(view: AppView) {
    if (view === "pipeline") {
      setPipelineContextMode("request");
    }
    setActiveView(view);
  }

  function openSelectedRunEvidence() {
    setPipelineContextMode("selected");
    setActiveView("pipeline");
  }

  function selectPipelineRun(runId: string) {
    setPipelineContextMode("selected");
    void loadRunDetail(runId);
  }

  const showingSelectedRunContext =
    activeView === "agents" ||
    activeView === "visualization" ||
    (activeView === "pipeline" && pipelineContextMode === "selected");

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
      showHealthSummary={false}
      onRefresh={() => void refreshDashboard()}
      onViewChange={changeView}
    >
      {activeView !== "cockpit" &&
      activeView !== "monitoring" &&
      !(activeView === "agents" && monitoringAgentContext !== null) ? (
        <RunContextBand
          request={request}
          adapter={selectedAdapter}
          response={planResponse}
          job={showingSelectedRunContext ? focusedJob : job}
          jobRequest={
            showingSelectedRunContext
              ? focusedJob !== null
                ? jobRequest
                : null
              : jobRequest
          }
          selectedSnapshot={showingSelectedRunContext ? focusedSnapshot : null}
        />
      ) : null}

      {activeView === "cockpit" ? (
        <CockpitView
          activeJob={activeJob}
          approvedRuns={approvedRuns}
          canExecutePlan={canExecutePlan}
          completedRuns={completedRuns}
          executing={executing}
          health={health}
          job={job}
          llmStatus={llmStatus}
          planning={planning}
          request={request}
          runs={runs}
          selectedAdapter={selectedAdapter}
          selectedArtifacts={selectedArtifacts}
          selectedAuditReport={selectedAuditReport}
          selectedReport={selectedReport}
          selectedReportDebate={selectedReportDebate}
          selectedRunEntry={selectedRunEntry}
          selectedSnapshot={selectedSnapshot}
          selectedVisualization={selectedVisualization}
          loadingFocusRun={loadingRunDetail}
          onExecute={() => void executeBackgroundRun()}
          onNavigate={changeView}
          onOpenRun={openRunInView}
          onRefreshLlm={() => void refreshLLMStatus()}
        />
      ) : activeView === "pipeline" ? (
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
          onSelectRun={selectPipelineRun}
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
      ) : activeView === "monitoring" ? (
        <MonitoringView
          bridgeContext={monitoringAgentContext}
          onBridgeRestored={finishMonitoringBridgeRestore}
          onOpenAgentRun={(context) => void openMonitoringAgentRun(context)}
        />
      ) : activeView === "agents" ? (
        <AgentObservabilityView
          job={monitoringAgentContext ? monitoringChildJob : focusedJob}
          events={monitoringAgentContext ? monitoringChildEvents : runtimeEvents}
          selectedSnapshot={monitoringAgentContext ? monitoringChildSnapshot : focusedSnapshot}
          selectedAgentId={selectedAgentId}
          onSelectAgent={selectAgent}
          onOpenEvidence={openSelectedRunEvidence}
          monitoringContext={monitoringAgentContext}
          onReturnToMonitoring={returnToMonitoringTrigger}
          memoryCollections={memoryCollections}
          memoryStatus={memoryStatus}
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
          comparingRuns={comparingRuns}
          comparison={runComparison}
          runs={visibleRuns}
          selectedCompareRunIds={selectedCompareRunIds}
          selectedRunId={selectedRunId}
          data={selectedVisualization}
          loading={loadingVisualization}
          onCompare={() => void submitRunComparison()}
          onSelectRun={(runId) => void loadRunDetail(runId)}
          onToggleCompare={toggleCompareRun}
        />
      )}
    </AppShell>
  );
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

function assertMonitoringChildRunIdentity(
  job: ApiRunJobStatus,
  context: MonitoringAgentBridgeContext,
) {
  if (job.job_id !== context.childRunId || job.run_id !== context.childRunId) {
    throw new Error(
      "El backend no conserva el invariante child_run_id = child_job_id = run_id.",
    );
  }
}
