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
  runtime_events_path?: string | null;
  summary_path: string;
  metadata_path: string;
  created_at: string;
  n_artifacts: number;
  n_decisions: number;
  n_errors: number;
}

export type ReplayMode = "manual" | "accelerated";
export type ReplayExperimentMode =
  | "frozen_benchmark"
  | "adaptive_replay_exploratory";
export type ReplaySessionStatus =
  | "ready"
  | "running"
  | "paused"
  | "completed"
  | "failed";
export type MonitoringAnalysisStatus =
  | "modeled"
  | "telemetry_only"
  | "unavailable";
export type AgentActivationPolicyKind = "P0" | "P1" | "P2" | "P3";
export type MonitoringAgentRole =
  | "supervisor"
  | "cleaner"
  | "structurer"
  | "modeler"
  | "evaluator"
  | "report_writer"
  | "report_verifier";
export type MonitoringTriggerType =
  | "preflight"
  | "periodic_review"
  | "persistent_alert"
  | "state_transition"
  | "continuity_gap"
  | "session_close"
  | "manual";
export type MonitoringTriggerLifecycle =
  | "emitted"
  | "suppressed"
  | "coalesced"
  | "dispatched"
  | "running"
  | "resolved"
  | "failed";
export type MonitoringChildRunStatus =
  | "dispatched"
  | "running"
  | "resolved"
  | "failed"
  | "interrupted";
export type MonitoringReviewDispatchOutcome =
  | "dispatched"
  | "idempotent_replay"
  | "revision_conflict"
  | "rejected";
export type MonitoringTriggerSuppressionReason =
  | "cooldown"
  | "budget"
  | "not_rearmed"
  | "episode_already_covered";
export type MonitoringTriggerReasonCode =
  | "preflight_review"
  | "periodic_schedule"
  | "persistent_confirmation"
  | "health_state_escalation"
  | "continuity_gap"
  | "session_completed"
  | "manual_request";
export type TriggerRearmPolicy =
  | "after_cooldown"
  | "after_recovery"
  | "once_per_session"
  | "manual";
export type ReplayStepOutcome =
  | "applied"
  | "idempotent_replay"
  | "revision_conflict"
  | "rejected";

export interface MonitoringReplaySourceSummary {
  scenario_id: string;
  title: string;
  dataset_id: string;
  trajectory_id: string;
  source_label: string;
  available: boolean;
  unavailable_reason: string | null;
  total_monitoring_ticks: number;
  modeled_channel_id: string;
  channel_ids: string[];
  available_activation_policy_kinds: AgentActivationPolicyKind[];
}

export interface ActivePolicyRefs {
  scoring_version: string;
  activation_version: string;
}

export interface ReplayAssetSpec {
  asset_id: string;
  channel_id: string;
  analysis_status: MonitoringAnalysisStatus;
}

export interface ReplaySessionConfig {
  schema_version: "monitoring_replay_session_config_v1";
  session_id: string;
  pilot_id: string;
  dataset_id: string;
  trajectory_id: string;
  manifest_ref: string;
  manifest_sha256: string;
  source_fingerprint_sha256: string;
  bootstrap_checkpoints_sha256: string;
  partition_policy_id: string;
  asset_ids: string[];
  asset_specs: ReplayAssetSpec[];
  activation_policy_kind: AgentActivationPolicyKind;
  experiment_mode: ReplayExperimentMode;
  initial_mode: ReplayMode;
  initial_speed_multiplier: number;
  initial_policy_refs: ActivePolicyRefs;
  source_timezone: string | null;
  created_at: string;
}

export interface ReplayAssetCheckpoint {
  asset_id: string;
  analysis_status: MonitoringAnalysisStatus;
  segment_id: number;
  alert_persistence_count: number;
  recovery_persistence_count: number;
  raw_health_history: number[];
  smoothed_health_history: number[];
  last_source_time: string | null;
  last_frame_id: string | null;
  last_health_state: HealthState | null;
  scoring_version: string | null;
}

export interface ReplayActivationRuleCheckpoint {
  trigger_type: MonitoringTriggerType;
  last_effective_trigger_id: string;
  last_effective_source_time: string;
}

export interface ReplayActivationCheckpoint {
  activation_version: string;
  next_event_sequence: number;
  variable_run_slots_reserved: number;
  persistent_alert_armed: boolean;
  alert_episode_start_cursor: number | null;
  alert_episode_start_snapshot_id: string | null;
  alert_episode_id: string | null;
  alert_episode_handled_trigger_id: string | null;
  last_evaluated_cursor: number | null;
  last_evaluated_tick_id: string | null;
  rule_checkpoints: ReplayActivationRuleCheckpoint[];
}

export interface ReplaySessionState {
  schema_version: "monitoring_replay_session_state_v1";
  session_id: string;
  config_sha256: string;
  status: ReplaySessionStatus;
  execution_cursor: number | null;
  sequence: number;
  revision: number;
  mode: ReplayMode;
  speed_multiplier: number;
  active_policy_refs: ActivePolicyRefs;
  activation_checkpoint: ReplayActivationCheckpoint | null;
  asset_checkpoints: ReplayAssetCheckpoint[];
  last_committed_tick_id: string | null;
  last_trigger_id: string | null;
  child_run_ids: string[];
  active_child_run_id: string | null;
  last_command_id: string | null;
  failure_reason: string | null;
  updated_at: string;
}

export interface MonitoringTelemetrySummary {
  signal_rms: number;
  signal_peak_abs: number;
  n_samples: number;
}

interface MonitoringFrameBase {
  schema_version: "monitoring_frame_v1";
  frame_id: string;
  tick_id: string;
  asset_id: string;
  channel_id: string;
  interval_seconds: number | null;
  gap_detected: boolean;
  evidence_refs: string[];
}

export interface ModeledMonitoringFrame extends MonitoringFrameBase {
  analysis_status: "modeled";
  segment_id: number;
  telemetry: MonitoringTelemetrySummary | null;
  score: number;
  threshold: number;
  predicted_anomaly: boolean;
  score_ratio: number;
  health_index: number;
  risk_index: number;
  health_state: HealthState;
  scoring_version: string;
  unavailable_reason: null;
}

export interface TelemetryOnlyMonitoringFrame extends MonitoringFrameBase {
  analysis_status: "telemetry_only";
  segment_id: number | null;
  telemetry: MonitoringTelemetrySummary;
  score: null;
  threshold: null;
  predicted_anomaly: null;
  score_ratio: null;
  health_index: null;
  risk_index: null;
  health_state: null;
  scoring_version: null;
  unavailable_reason: null;
}

export interface UnavailableMonitoringFrame extends MonitoringFrameBase {
  analysis_status: "unavailable";
  segment_id: number | null;
  telemetry: null;
  score: null;
  threshold: null;
  predicted_anomaly: null;
  score_ratio: null;
  health_index: null;
  risk_index: null;
  health_state: null;
  scoring_version: null;
  unavailable_reason: string;
}

export type MonitoringFrame =
  | ModeledMonitoringFrame
  | TelemetryOnlyMonitoringFrame
  | UnavailableMonitoringFrame;

export interface ReplayTick {
  schema_version: "monitoring_replay_tick_v1";
  commit_status: "committed";
  tick_id: string;
  session_id: string;
  cursor: number;
  sequence: number;
  snapshot_id: string;
  source_time: string;
  input_record_hash: string;
  active_policy_refs: ActivePolicyRefs;
  frames: MonitoringFrame[];
  committed_at: string;
}

export interface MonitoringTriggerEvent {
  schema_version: "monitoring_trigger_event_v1";
  event_id: string;
  trigger_id: string;
  session_id: string;
  sequence: number;
  lifecycle_revision: number;
  previous_event_id: string | null;
  trigger_type: MonitoringTriggerType;
  lifecycle_status: MonitoringTriggerLifecycle;
  priority: number;
  reason_code: MonitoringTriggerReasonCode;
  reason: string;
  episode_id: string | null;
  asset_id: string | null;
  snapshot_start_id: string | null;
  snapshot_end_id: string | null;
  condition_start_cursor: number | null;
  cutoff_cursor: number | null;
  cutoff_source_time: string | null;
  previous_state: HealthState | null;
  new_state: HealthState | null;
  cooldown_source_seconds: number;
  coalescing_group: string | null;
  rearm_policy: TriggerRearmPolicy;
  requested_roles: MonitoringAgentRole[];
  counts_toward_variable_budget: boolean;
  budget_reservation_index: number | null;
  dedupe_key: string;
  activation_version: string;
  activation_policy_sha256: string;
  origin_tick_id: string | null;
  frame_ids: string[];
  evidence_refs: string[];
  suppressed_by_trigger_id: string | null;
  suppression_reason: MonitoringTriggerSuppressionReason | null;
  coalesced_into_trigger_id: string | null;
  child_run_id: string | null;
  recorded_at: string;
}

export interface MonitoringChildRunAttempt {
  schema_version: "monitoring_child_run_attempt_v1";
  session_id: string;
  trigger_id: string;
  trigger_event_id: string;
  child_run_id: string;
  job_id: string;
  run_id: string;
  attempt_no: number;
  child_revision: number;
  lifecycle_status: MonitoringChildRunStatus;
  request_ref: string;
  request_sha256: string;
  causal_view_ref: string;
  causal_view_sha256: string;
  result_ref: string | null;
  result_sha256: string | null;
  dispatched_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
  error: string | null;
}

export interface MonitoringReviewDispatchReceipt {
  schema_version: "monitoring_review_dispatch_receipt_v1";
  receipt_id: string;
  receipt_sha256: string;
  command_id: string;
  command_sha256: string;
  session_id: string;
  trigger_id: string;
  trigger_event_id: string;
  child_run_id: string;
  job_id: string;
  run_id: string;
  attempt_no: number;
  expected_child_revision: number;
  child_revision: number;
  request_ref: string;
  request_sha256: string;
  causal_view_ref: string;
  causal_view_sha256: string;
  outcome: MonitoringReviewDispatchOutcome;
  attempt: MonitoringChildRunAttempt | null;
  error: string | null;
  recorded_at: string;
}

export interface ReplayStepReceipt {
  schema_version: "monitoring_replay_step_receipt_v1";
  command_id: string;
  session_id: string;
  expected_revision: number;
  outcome: ReplayStepOutcome;
  accepted_revision: number;
  tick_id: string | null;
  reason: string | null;
  recorded_at: string;
}

export interface MonitoringSessionCreateRequest {
  scenario_id: string;
  session_id?: string;
  activation_policy_kind?: AgentActivationPolicyKind;
  experiment_mode?: ReplayExperimentMode;
}

export interface MonitoringStepRequest {
  command_id: string;
  expected_revision: number;
}

export interface MonitoringReviewDispatchRequest {
  command_id: string;
  expected_child_revision: number;
}

export interface MonitoringSessionView {
  source: MonitoringReplaySourceSummary;
  config: ReplaySessionConfig;
  state: ReplaySessionState;
  total_monitoring_ticks: number;
  ticks: ReplayTick[];
  triggers: MonitoringTriggerEvent[];
  child_revision: number;
  child_runs: MonitoringChildRunAttempt[];
  active_child_run_id: string | null;
}

export interface MonitoringStepResponse {
  receipt: ReplayStepReceipt;
  state: ReplaySessionState;
  tick: ReplayTick | null;
  triggers: MonitoringTriggerEvent[];
}

export interface MonitoringReviewDispatchResponse {
  session: MonitoringSessionView;
  attempt: MonitoringChildRunAttempt | null;
  receipt: MonitoringReviewDispatchReceipt;
}

export type MonitoringReviewGateOutcome =
  | "first_pass"
  | "llm_repaired"
  | "fallback"
  | "non_agentic"
  | "error"
  | "missing";
export type MonitoringReviewRecommendedAction =
  | "maintain_policy"
  | "intensify_observation"
  | "request_human_review"
  | "pause_replay"
  | "insufficient_evidence";
export type MonitoringReviewGateCoverageKind =
  | "hypothesis_structure"
  | "causal_grounding"
  | "trigger_decision_result_binding";

export interface MonitoringReviewGateOutcomeCounts {
  expected_count: number;
  observed_count: number;
  first_pass_count: number;
  repaired_count: number;
  fallback_count: number;
  non_agentic_count: number;
  error_count: number;
  missing_count: number;
}

export interface MonitoringReviewGateRoleSummary {
  agent_name: MonitoringAgentRole;
  outcomes: MonitoringReviewGateOutcomeCounts;
}

export interface MonitoringReviewGateRoleResult {
  agent_name: MonitoringAgentRole;
  outcome: MonitoringReviewGateOutcome;
  validation_status: "validated" | "repaired" | "fallback_applied" | "unknown" | null;
  recommended_action: MonitoringReviewRecommendedAction | null;
}

export interface MonitoringReviewGateCase {
  case_id: string;
  context_id: string;
  context_ordinal: number;
  repetition: number;
  trigger_type: MonitoringTriggerType;
  reason_code: MonitoringTriggerReasonCode;
  condition_start_cursor: number;
  cutoff_cursor: number;
  session_id: string | null;
  trigger_id: string | null;
  child_run_id: string | null;
  child_lifecycle_status: MonitoringChildRunStatus | null;
  bridge_lifecycle_status: MonitoringTriggerLifecycle | null;
  observed_role_count: number;
  expected_role_count: number;
  role_results: MonitoringReviewGateRoleResult[];
}

export interface MonitoringReviewGateCoverage {
  kind: MonitoringReviewGateCoverageKind;
  passed_count: number;
  expected_count: number;
}

export interface MonitoringReviewGateView {
  schema_version: "monitoring_review_gate_view_v1";
  publication_status: "published";
  gate_id: string;
  verdict: "passed" | "blocked";
  blockers: string[];
  completed_at: string;
  provider: string;
  model: string;
  memory_mode: "off";
  policy_application_status: "not_applied";
  complete_repetition_count: number;
  expected_repetition_count: number;
  complete_context_count: number;
  expected_context_count: number;
  resolved_child_run_count: number;
  expected_child_run_count: number;
  outcomes: MonitoringReviewGateOutcomeCounts;
  roles: MonitoringReviewGateRoleSummary[];
  cases: MonitoringReviewGateCase[];
  coverage: MonitoringReviewGateCoverage[];
}

export type MonitoringEvidenceCampaignStatus =
  | "planned"
  | "running"
  | "completed"
  | "interrupted"
  | "failed";
export type MonitoringEvidenceCampaignPhase =
  | "planned"
  | "pre_roll"
  | "agentic_window"
  | "completed";
export type MonitoringEvidenceCampaignVerdict = "pending" | "passed" | "blocked";
export type MonitoringEvidenceCampaignReviewLifecycle =
  | "pending"
  | "running"
  | "resolved"
  | "failed"
  | "interrupted";

export interface MonitoringEvidenceCampaignReviewView {
  context_id: string;
  ordinal: number;
  trigger_type: MonitoringTriggerType;
  reason_code: MonitoringTriggerReasonCode;
  condition_start_cursor: number;
  cutoff_cursor: number;
  source_time: string;
  lifecycle: MonitoringEvidenceCampaignReviewLifecycle;
  trigger_id: string | null;
  child_run_id: string | null;
  decision_count: number;
  llm_origin_count: number;
  repaired_count: number;
  fallback_count: number;
  proposal_status: string | null;
  proposal_application_status: string | null;
  error: string | null;
}

export interface MonitoringEvidenceCampaignView {
  schema_version: "monitoring_evidence_campaign_view_v1";
  publication_status: "published";
  publication_sha256: string;
  published_at: string;
  registration_sha256: string;
  registered_at: string;
  plan_sha256: string;
  state_sha256: string;
  result_sha256: string | null;
  campaign_id: string;
  session_id: string;
  status: MonitoringEvidenceCampaignStatus;
  phase: MonitoringEvidenceCampaignPhase;
  evidence_verdict: MonitoringEvidenceCampaignVerdict;
  operational_verdict: MonitoringEvidenceCampaignVerdict;
  agentic_verdict: MonitoringEvidenceCampaignVerdict;
  current_revision: number;
  execution_cursor: number | null;
  progress_ratio: number;
  reviews: MonitoringEvidenceCampaignReviewView[];
  observed_trigger_count: number;
  terminal_child_run_count: number;
  resolved_child_run_count: number;
  observed_decision_count: number;
  physical_attempt_count: number;
  llm_origin_decision_count: number;
  repaired_decision_count: number;
  fallback_count: number;
  policy_proposal_count: number;
  blockers: string[];
  started_at: string | null;
  updated_at: string;
  completed_at: string | null;
  runtime_elapsed_seconds: number;
  execution_mode: "historical_replay_accelerated";
  experiment_mode: "frozen_benchmark";
  memory_mode: "off";
  policy_application_status: "not_applied";
  expected_total_monitoring_ticks: 689;
  pre_roll_start_cursor: 0;
  pre_roll_end_cursor: 352;
  agentic_window_start_cursor: 353;
  agentic_window_end_cursor: 688;
  agentic_window_source_start: "2004-02-16T22:32:39";
  agentic_window_source_end: "2004-02-19T06:22:39";
  agentic_window_source_duration_seconds: 201000;
  source_timezone_status: "not_declared";
  speed_multiplier: number;
  expected_trigger_count: 4;
  expected_child_run_count: 4;
  expected_decision_count: 28;
  expected_policy_proposal_count: 4;
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
  degradation_persistent_alert_run_rate: number | null;
  degradation_mean_first_persistent_alert_time_to_trajectory_end: number | null;
  degradation_mean_pre_monitoring_alert_rate: number | null;
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
  decision_origin:
    | "llm"
    | "deterministic"
    | "guardrail_fallback"
    | "protocol_restricted"
    | "unknown";
  origin_evidence: string | null;
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
  | "policy_proposal"
  | "executor_result"
  | "error";

export type AgentRuntimeEventSource =
  | "job"
  | "supervisor"
  | "agent"
  | "memory"
  | "system"
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
  data_provenance: "official" | "synthetic" | "unknown";
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

export interface MemoryReadinessBlocker {
  code: string;
  message: string;
}

export interface MemoryStatusResponse {
  backend: {
    configured_backend: string;
    backend_name: string;
    operational: boolean;
    embedding_model: string | null;
    error_type: string | null;
    diagnostic: string | null;
  };
  corpus: {
    available: boolean;
    total_records: number;
    reusable_records: number;
    official_records: number;
    official_reusable_records: number;
    shared_methodology_records: number;
    shared_methodology_reusable_records: number;
    corpus_fingerprint: string | null;
    frozen_manifest_available: boolean;
    reusable_dataset_coverage: string[];
    reusable_agent_coverage: AgentMemoryTarget[];
    n_reusable_datasets: number;
    n_reusable_agents: number;
    candidate_queue_available: boolean;
    pending_candidates: number;
    candidate_queue_error_type: string | null;
    candidate_queue_diagnostic: string | null;
  };
  scientific_readiness: {
    ready_for_memory_effect_benchmark: boolean;
    minimum_reusable_datasets: number;
    minimum_reusable_agents: number;
    blockers: MemoryReadinessBlocker[];
  };
  checked_at: string;
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
