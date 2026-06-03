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
  evidence_pack_path?: string | null;
  evidence_pack_markdown_path?: string | null;
  audit_report_path?: string | null;
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
  supervision_profile: string | null;
  label_source: string | null;
  label_granularity: string | null;
  model_name: string | null;
  metric_families: string[];
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  false_positive_rate: number | null;
  degradation_available: boolean | null;
  degradation_n_runs: number | null;
  degradation_detected_before_failure_rate: number | null;
  degradation_mean_lead_time_to_failure: number | null;
  degradation_mean_false_alarm_rate_nominal: number | null;
  degradation_mean_score_trend_spearman: number | null;
  degradation_missed_runs: number | null;
  degradation_mean_initial_final_separation: number | null;
  report_path: string | null;
  snapshot_path: string;
}

export interface MetricComparison {
  metric: string;
  metric_family: "binary_classification" | "run_to_failure_degradation";
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
  degradation_metrics: MetricComparison[];
}

export interface VisualizationMetric {
  name: string;
  label: string;
  value: number | null;
  higher_is_better: boolean;
  metric_family: "binary_classification" | "run_to_failure_degradation";
  value_kind: "ratio" | "seconds" | "count" | "score";
  note: string | null;
}

export interface ProjectionPoint {
  window_id: string;
  x: number;
  y: number;
  split: string | null;
  label: string | null;
  target: number | null;
  fault_type: string | null;
  anomaly_score: number | null;
  threshold: number | null;
  predicted_anomaly: number | null;
}

export interface ProjectionBoundary {
  kind: "ellipse_approximation";
  center_x: number;
  center_y: number;
  radius_x: number;
  radius_y: number;
  threshold: number | null;
  note: string;
}

export type TemporalXAxis = "relative_life" | "time_since_start_seconds" | "window_index";
export type HealthState = "nominal" | "watch" | "warning" | "critical";

export interface TemporalSeriesPoint {
  window_id: string;
  run_id: string;
  x: number;
  timestamp_start: string | null;
  timestamp_end: string | null;
  relative_life: number | null;
  time_since_start_seconds: number | null;
  time_to_failure_seconds: number | null;
  split: string | null;
  label: string | null;
  anomaly_score: number;
  threshold: number | null;
  predicted_anomaly: number | null;
  score_ratio: number | null;
  risk_index: number | null;
  health_index: number | null;
  health_state: HealthState;
  state_reason: string;
}

export interface TemporalRunSeries {
  run_id: string;
  x_axis: TemporalXAxis;
  points: TemporalSeriesPoint[];
  n_points_total: number;
  n_points_sampled: number;
  threshold: number | null;
  first_alert_x: number | null;
  first_alert_time: string | null;
  first_alert_time_to_failure_seconds: number | null;
  first_persistent_alert_x: number | null;
  first_persistent_alert_time: string | null;
  first_persistent_alert_time_to_failure_seconds: number | null;
  persistent_alert_min_windows: number;
  failure_x: number | null;
  failure_time: string | null;
  failure_reference: string;
  score_min: number | null;
  score_max: number | null;
  current_x: number | null;
  current_time: string | null;
  current_time_to_failure_seconds: number | null;
  current_risk_index: number | null;
  current_health_index: number | null;
  current_health_state: HealthState;
  current_state_reason: string;
  alert_points: number;
  warning_points: number;
  critical_points: number;
  isolated_alert_points: number;
  alert_episodes: number;
  longest_alert_streak: number;
}

export interface TemporalSeriesData {
  available: boolean;
  x_axis: TemporalXAxis | null;
  runs: TemporalRunSeries[];
  n_runs_total: number;
  n_points_total: number;
  warnings: string[];
}

export type AgentRecommendationStatus =
  | "approved"
  | "caution"
  | "needs_revision"
  | "blocked"
  | "unavailable";

export interface AgentOperationalRecommendation {
  available: boolean;
  source_agent: string | null;
  decision_id: string | null;
  status: AgentRecommendationStatus;
  title: string;
  summary: string;
  confidence: number | null;
  next_action: string | null;
  operational_assessment: string | null;
  evidence_refs: string[];
  tool_names: string[];
  limitations: string[];
  debate_points: string[];
  guardrail_checks: string[];
  modeler_summary: string | null;
}

export interface RunVisualizationData {
  run_id: string;
  dataset: string;
  supervision_profile: string | null;
  label_source: string | null;
  label_granularity: string | null;
  model_name: string | null;
  metric_families: string[];
  metrics: VisualizationMetric[];
  primary_metrics: VisualizationMetric[];
  auxiliary_metrics: VisualizationMetric[];
  binary_metric_context: Record<string, string>;
  projection_available: boolean;
  projection_points: ProjectionPoint[];
  projection_boundary: ProjectionBoundary | null;
  projection_role: "primary" | "diagnostic";
  projection_explanation: string;
  temporal_series: TemporalSeriesData | null;
  agent_recommendation: AgentOperationalRecommendation | null;
  n_points_total: number;
  n_points_sampled: number;
  source_paths: Record<string, string>;
  warnings: string[];
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

export type MemoryCurationAction = "exclude" | "restore" | "delete";

export interface MemoryCurationRequest {
  action: Exclude<MemoryCurationAction, "delete">;
  reason: string;
  reviewer: string | null;
}

export interface MemoryCurationResponse {
  memory_record_id: string;
  action: MemoryCurationAction;
  reason: string | null;
  record: ReasoningMemoryRecord | null;
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

export interface LLMStatusResponse {
  provider: string;
  model: string;
  host: string;
  timeout_seconds: number;
  think: boolean | null;
  available: boolean;
  model_available: boolean;
  models: string[];
  detail: string | null;
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
  supervision_profile: string;
  label_granularity: string;
  label_source: string;
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
