export type PipelineRunExecutionMode = "full" | "diagnostic";

export type PipelineRunStage =
  | "manifest"
  | "profiling"
  | "cleaning"
  | "structuring"
  | "modeling"
  | "evaluation"
  | "reporting"
  | "memory";

export type HumanReviewMode = "off" | "passive" | "required";

export interface HealthResponse {
  status: string;
  runs_dir: string;
  allowed_raw_roots: string[];
  dataset_uploads_dir: string;
  memory_dir: string;
}

export interface RunIndexEntry {
  run_id: string;
  thread_id: string;
  dataset: string;
  current_stage: string;
  approved: boolean | null;
  report_path: string | null;
  snapshot_path: string;
  created_at: string;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  false_positive_rate: number | null;
  n_artifacts: number;
  n_decisions: number;
  n_errors: number;
}

export interface RunSnapshot {
  run_id: string;
  thread_id: string;
  dataset: string;
  current_stage: string;
  approved: boolean | null;
  report_path: string | null;
  snapshot_dir: string;
  state_path: string;
  decisions_path: string;
  artifacts_path: string;
  metrics_path: string;
  evaluation_path: string;
  summary_path: string;
  metadata_path: string;
  created_at: string;
  n_artifacts: number;
  n_decisions: number;
  n_errors: number;
}

export interface RunFilters {
  dataset: string | null;
  current_stage: string | null;
  approved: boolean | null;
}

export interface ArtifactRef {
  name: string;
  artifact_type: string;
  path: string;
  producer: string;
  description: string | null;
  metadata: Record<string, string | number | boolean | null>;
}

export interface RunComparisonRow {
  run_id: string;
  dataset: string;
  current_stage: string;
  approved: boolean | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  false_positive_rate: number | null;
  report_path: string | null;
  snapshot_path: string;
}

export interface MetricComparison {
  metric: "precision" | "recall" | "f1_score" | "false_positive_rate";
  higher_is_better: boolean;
  best_run_id: string | null;
  best_value: number | null;
  worst_run_id: string | null;
  worst_value: number | null;
  spread: number | null;
}

export interface RunComparison {
  generated_at: string;
  run_ids: string[];
  rows: RunComparisonRow[];
  metrics: MetricComparison[];
}

export type AgentRuntimeEventKind =
  | "job_status"
  | "supervisor_decision"
  | "agent_decision"
  | "memory_retrieval"
  | "executor_result"
  | "error";

export type AgentRuntimeEventSource =
  | "job"
  | "supervisor"
  | "agent"
  | "memory"
  | "executor";

export interface AgentRuntimeEvent {
  event_id: string;
  run_id: string;
  sequence: number;
  kind: AgentRuntimeEventKind;
  source: AgentRuntimeEventSource;
  title: string;
  summary: string;
  created_at: string;
  stage: string | null;
  node: string | null;
  agent_name: string | null;
  decision_id: string | null;
  rationale: string | null;
  confidence: number | null;
  next_stage: string | null;
  next_node: string | null;
  memory_context_id: string | null;
  memory_record_ids: string[];
  payload: Record<string, unknown>;
}

export type AgentMemoryTarget =
  | "cleaner"
  | "structurer"
  | "modeler"
  | "evaluator"
  | "report_writer"
  | "researcher"
  | "shared_methodology";

export type AgentMemoryCollection =
  | "cleaner_memory"
  | "structurer_memory"
  | "modeler_memory"
  | "evaluator_memory"
  | "report_writer_memory"
  | "researcher_memory"
  | "shared_methodology_memory";

export type MemoryRole =
  | "positive_example"
  | "negative_example"
  | "boundary_case"
  | "warning"
  | "methodology"
  | "evidence"
  | "excluded";

export interface MemoryCollectionSummary {
  collection_name: AgentMemoryCollection;
  target_agent: AgentMemoryTarget;
  n_records: number;
  n_reusable: number;
  n_excluded: number;
  datasets: string[];
  memory_roles: Record<string, number>;
  source_types: Record<string, number>;
  human_verdicts: Record<string, number>;
  latest_created_at: string | null;
}

export interface MemoryRecordSummary {
  memory_record_id: string;
  collection_name: AgentMemoryCollection;
  target_agent: AgentMemoryTarget;
  source_type: string;
  run_id: string | null;
  decision_id: string | null;
  dataset: string | null;
  source_agent_name: string | null;
  outcome: string | null;
  human_verdict: string | null;
  memory_role: MemoryRole;
  reusable_as_context: boolean;
  exclude_from_context: boolean;
  summary: string;
  source_path: string | null;
  tags: string[];
  created_at: string;
}

export interface ReasoningMemoryRecord extends MemoryRecordSummary {
  source_hash: string | null;
  postmortem_id: string | null;
  content: string;
  metrics: Record<string, number | null>;
  embedding_model: string | null;
  embedding_version: string | null;
  embedding_dimension: number | null;
  vector_id: string | null;
}

export interface HumanReviewSettings {
  mode: HumanReviewMode;
  reviewer: string | null;
  required_decision_points: string[];
  passive_artifacts_enabled: boolean;
}

export interface HumanApproval {
  required: boolean;
  approved: boolean | null;
  reviewer: string | null;
  reason: string | null;
  reviewed_at: string | null;
}

export interface PipelineRunRequest {
  run_id: string;
  dataset_id: string;
  raw_path: string;
  adapter_id: string | null;
  dataset_policy_id: string | null;
  execution_mode: PipelineRunExecutionMode;
  requested_stages: PipelineRunStage[] | null;
  use_memory: boolean;
  use_llm: boolean;
  allow_synthetic_labels: boolean;
}

export interface ApiRunRequest extends PipelineRunRequest {
  dry_run: boolean;
  background: boolean;
  human_review: HumanReviewSettings;
  human_approval: HumanApproval | null;
}

export interface DatasetAdapterInfo {
  adapter_id: string;
  dataset_id: string;
  display_name: string;
  supported_source_formats: string[];
  supports_descriptor: boolean;
  supports_manifest: boolean;
  is_experimental: boolean;
  notes: string;
}

export interface DatasetDescriptor {
  dataset_id: string;
  dataset_name: string;
  domain: string;
  asset_type: string;
  raw_path: string;
  source_format: string;
  adapter_id: string;
  label_availability: string;
  task_type: string;
  sampling_rate_hz: number | null;
  channel_names: string[];
  has_multiple_conditions: boolean;
  has_run_to_failure: boolean;
  metadata: Record<string, string | number | boolean | null>;
  notes: string[];
}

export interface DatasetDescribeRequest {
  raw_path: string;
  adapter_id: string | null;
}

export interface DatasetDescribeResponse {
  adapter_info: DatasetAdapterInfo;
  descriptor: DatasetDescriptor;
  allowed_raw_roots: string[];
  uploads_dir: string;
}

export interface DatasetCapabilityRule {
  stage: PipelineRunStage;
  status: "allowed" | "blocked" | "not_supported";
  reason: string | null;
  requires_human_review: boolean;
}

export interface DatasetRunPolicy {
  dataset_id: string;
  adapter_id: string;
  display_name: string;
  capabilities: DatasetCapabilityRule[];
  notes: string[];
}

export interface DatasetPipelinePaths {
  raw_path: string;
  interim_dir: string;
  clean_dir: string;
  tensor_dir: string;
  model_dir: string;
  evaluation_dir: string;
  memory_output_root: string;
}

export interface DatasetPipelinePlan {
  request: PipelineRunRequest;
  adapter_info: DatasetAdapterInfo;
  descriptor: DatasetDescriptor;
  policy: DatasetRunPolicy;
  paths: DatasetPipelinePaths;
  effective_stages: PipelineRunStage[];
  can_execute_requested_stages: boolean;
  blocking_reasons: string[];
}

export interface ApiRunJobStatus {
  job_id: string;
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  detail: string | null;
  snapshot: RunSnapshot | null;
  events: AgentRuntimeEvent[];
}

export interface ApiRunResponse extends ApiRunRequest {
  executed: boolean;
  plan: DatasetPipelinePlan;
  snapshot: RunSnapshot | null;
  final_stage: string | null;
  approved: boolean | null;
  report_path: string | null;
  metrics: Record<string, unknown> | null;
  errors: string[];
  human_review_reasons: string[];
  job: ApiRunJobStatus | null;
}
