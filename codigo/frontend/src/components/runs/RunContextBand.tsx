import { PIPELINE_STAGES } from "../../constants/pipeline";
import type {
  ApiRunJobStatus,
  ApiRunRequest,
  ApiRunResponse,
  DatasetAdapterInfo,
} from "../../types";
import { StatusPill } from "../common/StatusPill";

export function RunContextBand({
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
    <details className="compact-disclosure run-context-disclosure">
      <summary>
        <span>Contexto</span>
        <strong>{request.dataset_id || adapter.dataset_id} · {request.run_id || "-"}</strong>
        <StatusPill
          ok={planOk === true}
          muted={planOk === undefined}
          label={
            planOk === undefined
              ? "sin plan"
              : planOk
                ? "plan ok"
                : "bloqueado"
          }
        />
        <StatusPill
          ok={job?.status === "completed"}
          muted={job === null || job.status === "queued" || job.status === "running"}
          label={jobStatus}
        />
      </summary>
      <section className="context-band context-band-detail" aria-label="Contexto de ejecucion">
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
