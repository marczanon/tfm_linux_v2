import { DATASET_REQUEST_DEFAULTS } from "../constants/datasets";
import type { ApiRunRequest, DatasetAdapterInfo, HumanApproval } from "../types";
import { emptyToNull } from "./forms";

export function defaultRequest(adapter: DatasetAdapterInfo): ApiRunRequest {
  const defaults = DATASET_REQUEST_DEFAULTS[adapter.dataset_id] ?? {
    rawPath: "codigo/data/raw/uploads",
    executionMode: "diagnostic" as const,
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

export function normalizedRequest(
  request: ApiRunRequest,
  customStages: boolean,
): ApiRunRequest {
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

export function mergeHumanApproval(
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
