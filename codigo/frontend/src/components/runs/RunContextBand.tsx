import { PIPELINE_STAGES } from "../../constants/pipeline";
import type {
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  DatasetAdapterInfo,
  RunSnapshot,
} from "../../types";
import { StatusPill } from "../common/StatusPill";

export function RunContextBand({
  request,
  adapter,
  response,
  job,
  jobRequest,
  selectedSnapshot,
}: {
  request: ApiRunRequest;
  adapter: DatasetAdapterInfo;
  response: ApiRunResponse | null;
  job: ApiRunJobStatus | null;
  jobRequest?: ApiRunRequest | null;
  selectedSnapshot?: RunSnapshot | null;
}) {
  const showingJobContext =
    job !== null && job.status !== "completed" && selectedSnapshot == null;
  const persistedRun = showingJobContext ? null : selectedSnapshot ?? null;
  const frozenJobRequest =
    showingJobContext && jobRequest?.run_id === job?.run_id ? jobRequest : null;
  const contextRequest = frozenJobRequest ?? request;
  const contextRunId =
    (showingJobContext ? job?.run_id : persistedRun?.run_id) ??
    response?.run_id ??
    request.run_id ??
    "-";
  const contextDataset =
    (showingJobContext ? contextRequest.dataset_id : persistedRun?.dataset) ||
    contextRequest.dataset_id ||
    adapter.dataset_id;
  const matchingResponse = response?.run_id === contextRunId ? response : null;
  const matchingJob = job?.run_id === contextRunId ? job : null;
  const planOk = matchingResponse?.plan.can_execute_requested_stages;
  const stageCount =
    matchingResponse?.plan.effective_stages.length ??
    contextRequest.requested_stages?.length ??
    PIPELINE_STAGES.length;
  const executionStatus =
    matchingJob?.status ?? persistedRun?.current_stage ?? "sin ejecucion";
  const executionComplete = executionStatus === "completed";
  const executionPending =
    executionStatus === "sin ejecucion" ||
    executionStatus === "queued" ||
    executionStatus === "running";

  return (
    <details className="compact-disclosure run-context-disclosure">
      <summary>
        <span>Contexto</span>
        <strong>{contextDataset} · {contextRunId}</strong>
        <StatusPill
          ok={persistedRun !== null || showingJobContext || planOk === true}
          muted={persistedRun === null && !showingJobContext && planOk === undefined}
          label={
            persistedRun !== null
              ? "traza persistida"
              : showingJobContext
                ? "runtime del job"
              : planOk === undefined
              ? "sin plan"
              : planOk
                ? "plan ok"
                : "bloqueado"
          }
        />
        <StatusPill
          ok={executionComplete}
          muted={executionPending}
          label={executionStatus}
        />
      </summary>
      <section className="context-band context-band-detail" aria-label="Contexto de ejecucion">
        <ContextItem
          label="Dataset"
          value={contextDataset}
          detail={
            persistedRun === null
              ? contextRequest.adapter_id === adapter.adapter_id
                ? adapter.display_name
                : contextRequest.adapter_id ?? undefined
              : undefined
          }
        />
        <ContextItem label="Run" value={contextRunId} />
        <ContextItem
          label={persistedRun ? "Fuente" : "Modo"}
          value={persistedRun ? "runtime persistido" : contextRequest.execution_mode}
        />
        <ContextItem
          label={persistedRun ? "Decisiones" : "Politica"}
          value={persistedRun ? persistedRun.n_decisions.toString() : contextRequest.dataset_policy_id ?? "default"}
        />
        <ContextItem
          label={persistedRun ? "Errores" : "Fases"}
          value={persistedRun ? persistedRun.n_errors.toString() : stageCount.toString()}
        />
        <div className="context-item context-status">
          <span>{persistedRun ? "Evidencia" : "Plan"}</span>
          <StatusPill
            ok={persistedRun !== null || planOk === true}
            muted={persistedRun === null && planOk === undefined}
            label={
              persistedRun !== null
                ? "persistida"
                : planOk === undefined
                ? "sin plan"
                : planOk
                  ? "ejecutable"
                  : "bloqueado"
            }
          />
        </div>
        <div className="context-item context-status">
          <span>Estado</span>
          <StatusPill
            ok={executionComplete}
            muted={executionPending}
            label={executionStatus}
          />
        </div>
      </section>
    </details>
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
