import type {
  ActivePolicyRefs,
  ApiRunJobStatus,
  ModeledMonitoringFrame,
  MonitoringChildRunAttempt,
  MonitoringReplaySourceSummary,
  MonitoringReviewGateView,
  MonitoringReviewDispatchResponse,
  MonitoringSessionView,
  MonitoringStepResponse,
  MonitoringTelemetrySummary,
  MonitoringTriggerEvent,
  ReplayActivationCheckpoint,
  ReplayAssetCheckpoint,
  ReplaySessionState,
  ReplayTick,
  TelemetryOnlyMonitoringFrame,
} from "../../../src/types";
import {
  EXACT_SEVEN_AGENTS_SCENARIO,
  type AgentRunScenario,
} from "./agentRuns";

export interface MonitoringReplayScenario {
  childJob?: ApiRunJobStatus;
  childRunScenario?: AgentRunScenario;
  dispatch?: {
    response: MonitoringReviewDispatchResponse;
    triggerId: string;
  };
  initialSession: MonitoringSessionView;
  source: MonitoringReplaySourceSummary;
  steps: MonitoringStepResponse[];
}

const SESSION_ID = "e2e-monitoring-replay";
const POLICY: ActivePolicyRefs = {
  activation_version: "e2e-event-driven-p3-v1",
  scoring_version: "nasa-set2-pca-fixture-v1",
};
const ASSET_SPECS = [1, 2, 3, 4].map((index) => ({
  analysis_status: index === 1 ? "modeled" as const : "telemetry_only" as const,
  asset_id: `bearing_${index}`,
  channel_id: `channel_${index}`,
}));
const REQUESTED_ROLES: MonitoringTriggerEvent["requested_roles"] = [
  "supervisor",
  "cleaner",
  "structurer",
  "modeler",
  "evaluator",
  "report_writer",
  "report_verifier",
];

export const MONITORING_REPLAY_SCENARIO: MonitoringReplayScenario = buildScenario();
export const MONITORING_AGENT_BRIDGE_SCENARIO: MonitoringReplayScenario =
  buildAgentBridgeScenario();
export const MONITORING_DISPATCH_SCENARIO: MonitoringReplayScenario =
  buildDispatchScenario();
export const MONITORING_GATE_SCENARIO: MonitoringReplayScenario =
  buildGateScenario();

export const MONITORING_REVIEW_GATE_FIXTURE: MonitoringReviewGateView =
  buildReviewGateFixture();

function buildScenario(): MonitoringReplayScenario {
  const source: MonitoringReplaySourceSummary = {
    available: true,
    channel_ids: ASSET_SPECS.map((spec) => spec.channel_id),
    dataset_id: "nasa_ims_bearing",
    modeled_channel_id: "channel_1",
    scenario_id: "NASA-RTF-HYB-01",
    source_label: "NASA IMS Set 2 oficial · fixture causal E2E",
    title: "NASA IMS Set 2 · replay causal PCA",
    total_monitoring_ticks: 689,
    trajectory_id: "set_2",
    unavailable_reason: null,
    available_activation_policy_kinds: ["P0", "P3"],
  };
  const firstTick = tick(0, {
    healthIndex: 30,
    healthState: "warning",
    riskIndex: 70,
    score: 1,
    threshold: 1,
  });
  const secondTick = tick(1, {
    healthIndex: 0,
    healthState: "critical",
    riskIndex: 100,
    score: 1.5,
    threshold: 1,
  });
  const thirdTick = tick(2, {
    gapDetected: true,
    healthIndex: 0,
    healthState: "critical",
    intervalSeconds: 1_200,
    riskIndex: 100,
    score: 1.5,
    segmentId: 1,
    threshold: 1,
  });
  const emittedTrigger = stateTransitionTrigger(secondTick, {
    eventId: "evt-monitoring-critical-emitted",
    lifecycleRevision: 1,
    lifecycleStatus: "emitted",
    sequence: 1,
  });
  const suppressedTrigger = persistentAlertTrigger(secondTick, "suppressed", 2);
  const coalescedTrigger = continuityGapTrigger(thirdTick, 3, emittedTrigger.trigger_id);
  const failedTrigger = stateTransitionTrigger(secondTick, {
    eventId: "evt-monitoring-critical-failed",
    lifecycleRevision: 2,
    lifecycleStatus: "failed",
    previousEventId: emittedTrigger.event_id,
    sequence: 4,
  });
  const initialSession: MonitoringSessionView = {
    active_child_run_id: null,
    child_revision: 0,
    child_runs: [],
    config: {
      asset_ids: ASSET_SPECS.map((spec) => spec.asset_id),
      asset_specs: ASSET_SPECS,
      activation_policy_kind: "P3",
      created_at: "2026-08-11T10:00:00Z",
      dataset_id: source.dataset_id,
      experiment_mode: "frozen_benchmark",
      initial_mode: "manual",
      initial_policy_refs: POLICY,
      initial_speed_multiplier: 1,
      bootstrap_checkpoints_sha256: "d".repeat(64),
      manifest_ref: "artifact:e2e:manifest",
      manifest_sha256: "a".repeat(64),
      partition_policy_id: "nasa_ims_run_to_failure_v2",
      pilot_id: source.scenario_id,
      schema_version: "monitoring_replay_session_config_v1",
      session_id: SESSION_ID,
      source_fingerprint_sha256: "b".repeat(64),
      source_timezone: null,
      trajectory_id: source.trajectory_id,
    },
    source,
    state: sessionState(0, null),
    ticks: [],
    total_monitoring_ticks: source.total_monitoring_ticks,
    triggers: [],
  };
  return {
    initialSession,
    source,
    steps: [
      stepResponse(firstTick, sessionState(1, firstTick), []),
      stepResponse(
        secondTick,
        sessionState(2, secondTick, emittedTrigger.trigger_id, 3, 1),
        [emittedTrigger, suppressedTrigger],
      ),
      stepResponse(
        thirdTick,
        sessionState(3, thirdTick, emittedTrigger.trigger_id, 5, 1),
        [coalescedTrigger, failedTrigger],
      ),
    ],
  };
}

function buildGateScenario(): MonitoringReplayScenario {
  const scenario = buildScenario();
  const childRunScenario = EXACT_SEVEN_AGENTS_SCENARIO;
  return {
    ...scenario,
    childJob: {
      created_at: "2026-08-12T10:00:00Z",
      detail: "monitoring review gate fixture completed",
      events: childRunScenario.events,
      finished_at: "2026-08-12T10:01:00Z",
      job_id: childRunScenario.run.run_id,
      run_id: childRunScenario.run.run_id,
      snapshot: childRunScenario.snapshot,
      started_at: "2026-08-12T10:00:01Z",
      status: "completed",
    },
    childRunScenario,
  };
}

function buildReviewGateFixture(): MonitoringReviewGateView {
  const contexts = [
    { id: "state_transition_353", ordinal: 1, type: "state_transition" as const, reason: "health_state_escalation" as const, start: 353, cutoff: 353 },
    { id: "persistent_alert_498_from_496", ordinal: 2, type: "persistent_alert" as const, reason: "persistent_confirmation" as const, start: 496, cutoff: 498 },
    { id: "state_transition_499", ordinal: 3, type: "state_transition" as const, reason: "health_state_escalation" as const, start: 499, cutoff: 499 },
    { id: "session_close_688", ordinal: 4, type: "session_close" as const, reason: "session_completed" as const, start: 688, cutoff: 688 },
  ];
  const roles = REQUESTED_ROLES;
  const cases = contexts.flatMap((context) => [1, 2, 3].map((repetition) => {
    const isLinkedFixture = context.ordinal === 1 && repetition === 1;
    const childRunId = isLinkedFixture
      ? EXACT_SEVEN_AGENTS_SCENARIO.run.run_id
      : `gate-child-${repetition}-${context.ordinal}`;
    return {
      bridge_lifecycle_status: "resolved" as const,
      case_id: `gate-fixture:${context.id}:rep:${repetition}`,
      child_lifecycle_status: "resolved" as const,
      child_run_id: childRunId,
      condition_start_cursor: context.start,
      context_id: context.id,
      context_ordinal: context.ordinal,
      cutoff_cursor: context.cutoff,
      expected_role_count: roles.length,
      observed_role_count: roles.length,
      reason_code: context.reason,
      repetition,
      role_results: roles.map((agentName) => {
        const fallback = context.ordinal === 1 && repetition === 1
          && ["supervisor", "cleaner"].includes(agentName);
        const recommendedAction = context.ordinal === 1
          ? "maintain_policy" as const
          : context.ordinal === 2
            ? "intensify_observation" as const
            : context.ordinal === 3 && ["evaluator", "report_verifier"].includes(agentName)
              ? "request_human_review" as const
              : context.ordinal === 4 && agentName === "report_verifier"
                ? "insufficient_evidence" as const
                : "maintain_policy" as const;
        return {
          agent_name: agentName,
          outcome: fallback ? "fallback" as const : "first_pass" as const,
          recommended_action: recommendedAction,
          validation_status: fallback ? "fallback_applied" as const : "validated" as const,
        };
      }),
      session_id: SESSION_ID,
      trigger_id: isLinkedFixture
        ? "trg-monitoring-critical"
        : `gate-trigger-${repetition}-${context.ordinal}`,
      trigger_type: context.type,
    };
  }));
  const outcomeCounts = (firstPass: number, repaired: number) => ({
    error_count: 0,
    expected_count: firstPass + repaired,
    fallback_count: 0,
    first_pass_count: firstPass,
    missing_count: 0,
    non_agentic_count: 0,
    observed_count: firstPass + repaired,
    repaired_count: repaired,
  });
  return {
    blockers: [
      "resolved_child_run_count:11!=12",
      "fallback_count:2",
      "llm_origin_rate:0.976190<1.000000",
    ],
    cases,
    complete_context_count: 4,
    complete_repetition_count: 3,
    completed_at: "2026-08-12T16:31:44.822572Z",
    coverage: [
      { expected_count: 84, kind: "hypothesis_structure", passed_count: 84 },
      { expected_count: 84, kind: "causal_grounding", passed_count: 84 },
      { expected_count: 84, kind: "trigger_decision_result_binding", passed_count: 84 },
    ],
    expected_child_run_count: 12,
    expected_context_count: 4,
    expected_repetition_count: 3,
    gate_id: "nasa-p3-monitoring-review-qwen35-v3",
    memory_mode: "off",
    model: "qwen3.5:4b",
    outcomes: {
      ...outcomeCounts(82, 0),
      expected_count: 84,
      fallback_count: 2,
      observed_count: 84,
    },
    policy_application_status: "not_applied",
    provider: "ollama",
    publication_status: "published",
    resolved_child_run_count: 11,
    roles: roles.map((agentName) => ({
      agent_name: agentName,
      outcomes: ["supervisor", "cleaner"].includes(agentName)
        ? {
            ...outcomeCounts(11, 0),
            expected_count: 12,
            fallback_count: 1,
            observed_count: 12,
          }
        : outcomeCounts(12, 0),
    })),
    schema_version: "monitoring_review_gate_view_v1",
    verdict: "blocked",
  };
}

function buildDispatchScenario(): MonitoringReplayScenario {
  const scenario = buildScenario();
  const childRunScenario = EXACT_SEVEN_AGENTS_SCENARIO;
  const childRunId = childRunScenario.run.run_id;
  const emitted = scenario.steps[1].triggers.find(
    (event) => event.trigger_id === "trg-monitoring-critical",
  );
  const firstTick = scenario.steps[0].tick;
  const secondTick = scenario.steps[1].tick;
  if (!emitted || !firstTick || !secondTick) {
    throw new Error("La fixture no contiene el trigger emitido despachable.");
  }
  const dispatched: MonitoringTriggerEvent = {
    ...emitted,
    budget_reservation_index: null,
    child_run_id: childRunId,
    event_id: "evt-monitoring-critical-dispatched-guided",
    lifecycle_revision: 2,
    lifecycle_status: "dispatched",
    previous_event_id: emitted.event_id,
    recorded_at: "2026-08-11T10:00:02Z",
    sequence: 3,
  };
  const attempt: MonitoringChildRunAttempt = {
    attempt_no: 1,
    causal_view_ref: "artifact:e2e:causal-view",
    causal_view_sha256: "6".repeat(64),
    child_revision: 1,
    child_run_id: childRunId,
    completed_at: null,
    dispatched_at: "2026-08-11T10:00:02Z",
    error: null,
    job_id: childRunId,
    lifecycle_status: "dispatched",
    request_ref: "artifact:e2e:monitoring-review-request",
    request_sha256: "5".repeat(64),
    result_ref: null,
    result_sha256: null,
    run_id: childRunId,
    schema_version: "monitoring_child_run_attempt_v1",
    session_id: SESSION_ID,
    started_at: null,
    trigger_event_id: emitted.event_id,
    trigger_id: emitted.trigger_id,
    updated_at: "2026-08-11T10:00:02Z",
  };
  const dispatchedState: ReplaySessionState = {
    ...scenario.steps[1].state,
    active_child_run_id: childRunId,
    child_run_ids: [childRunId],
  };
  const responseSession: MonitoringSessionView = {
    ...scenario.initialSession,
    active_child_run_id: childRunId,
    child_revision: 1,
    child_runs: [attempt],
    state: dispatchedState,
    ticks: [firstTick, secondTick],
    triggers: [...scenario.steps[1].triggers, dispatched],
  };
  const response: MonitoringReviewDispatchResponse = {
    attempt,
    receipt: {
      attempt,
      attempt_no: 1,
      causal_view_ref: attempt.causal_view_ref,
      causal_view_sha256: attempt.causal_view_sha256,
      child_revision: 1,
      child_run_id: childRunId,
      command_id: "fixture-dispatch-command",
      command_sha256: "7".repeat(64),
      error: null,
      expected_child_revision: 0,
      job_id: childRunId,
      outcome: "dispatched",
      receipt_id: "fixture-dispatch-receipt",
      receipt_sha256: "8".repeat(64),
      recorded_at: "2026-08-11T10:00:02Z",
      request_ref: attempt.request_ref,
      request_sha256: attempt.request_sha256,
      run_id: childRunId,
      schema_version: "monitoring_review_dispatch_receipt_v1",
      session_id: SESSION_ID,
      trigger_event_id: emitted.event_id,
      trigger_id: emitted.trigger_id,
    },
    session: responseSession,
  };
  return {
    ...scenario,
    childJob: {
      created_at: attempt.dispatched_at,
      detail: "monitoring child review queued",
      events: [],
      finished_at: null,
      job_id: childRunId,
      run_id: childRunId,
      snapshot: null,
      started_at: null,
      status: "queued",
    },
    childRunScenario,
    dispatch: {
      response,
      triggerId: emitted.trigger_id,
    },
  };
}

function buildAgentBridgeScenario(): MonitoringReplayScenario {
  const scenario = buildScenario();
  const childRunScenario = EXACT_SEVEN_AGENTS_SCENARIO;
  const childRunId = childRunScenario.run.run_id;
  const emitted = scenario.steps[1].triggers.find(
    (event) => event.trigger_id === "trg-monitoring-critical",
  );
  const finalStep = scenario.steps[2];
  if (!emitted || !finalStep.tick) {
    throw new Error("La fixture base no contiene el trigger causal esperado.");
  }
  const dispatched: MonitoringTriggerEvent = {
    ...emitted,
    budget_reservation_index: null,
    child_run_id: childRunId,
    event_id: "evt-monitoring-critical-dispatched",
    lifecycle_revision: 2,
    lifecycle_status: "dispatched",
    previous_event_id: emitted.event_id,
    recorded_at: "2026-08-11T10:00:03Z",
    sequence: 4,
  };
  const running: MonitoringTriggerEvent = {
    ...dispatched,
    child_run_id: null,
    event_id: "evt-monitoring-critical-running",
    lifecycle_revision: 3,
    lifecycle_status: "running",
    previous_event_id: dispatched.event_id,
    recorded_at: "2026-08-11T10:00:04Z",
    sequence: 5,
  };
  finalStep.triggers = [
    ...finalStep.triggers.filter(
      (event) => event.trigger_id !== emitted.trigger_id,
    ),
    dispatched,
    running,
  ];
  finalStep.state = {
    ...finalStep.state,
    active_child_run_id: childRunId,
    child_run_ids: [childRunId],
    activation_checkpoint: finalStep.state.activation_checkpoint
      ? {
          ...finalStep.state.activation_checkpoint,
          next_event_sequence: 6,
        }
      : null,
  };
  return {
    ...scenario,
    childJob: {
      created_at: "2026-08-11T10:00:03Z",
      detail: "monitoring child review running",
      events: childRunScenario.events.slice(0, 4),
      finished_at: null,
      job_id: childRunId,
      run_id: childRunId,
      snapshot: null,
      started_at: "2026-08-11T10:00:03Z",
      status: "running",
    },
    childRunScenario,
  };
}

function tick(
  cursor: number,
  modeled: {
    gapDetected?: boolean;
    healthIndex: number;
    healthState: ModeledMonitoringFrame["health_state"];
    intervalSeconds?: number;
    riskIndex: number;
    score: number;
    segmentId?: number;
    threshold: number;
  },
): ReplayTick {
  const tickId = `${SESSION_ID}:tick:${String(cursor).padStart(6, "0")}`;
  const snapshotId = `2004.02.14.12.${String(cursor).padStart(2, "0")}.00`;
  const sourceTime = `2004-02-14T12:${String(cursor).padStart(2, "0")}:00`;
  const telemetry = (index: number): MonitoringTelemetrySummary => ({
    n_samples: 20_480,
    signal_peak_abs: 0.7 * index,
    signal_rms: 0.13 * index,
  });
  const modeledFrame: ModeledMonitoringFrame = {
    analysis_status: "modeled",
    asset_id: "bearing_1",
    channel_id: "channel_1",
    evidence_refs: [`evidence:features:${snapshotId}`],
    frame_id: `${tickId}:bearing_1:channel_1`,
    gap_detected: modeled.gapDetected ?? false,
    health_index: modeled.healthIndex,
    health_state: modeled.healthState,
    interval_seconds: modeled.intervalSeconds ?? 600,
    risk_index: modeled.riskIndex,
    schema_version: "monitoring_frame_v1",
    score: modeled.score,
    score_ratio: modeled.score / modeled.threshold,
    predicted_anomaly: modeled.score > modeled.threshold,
    scoring_version: POLICY.scoring_version,
    segment_id: modeled.segmentId ?? 0,
    telemetry: telemetry(1),
    threshold: modeled.threshold,
    tick_id: tickId,
    unavailable_reason: null,
  };
  const contextualFrames: TelemetryOnlyMonitoringFrame[] = [2, 3, 4].map(
    (index) => ({
      analysis_status: "telemetry_only",
      asset_id: `bearing_${index}`,
      channel_id: `channel_${index}`,
      evidence_refs: [`evidence:raw:${snapshotId}`],
      frame_id: `${tickId}:bearing_${index}:channel_${index}`,
      gap_detected: modeled.gapDetected ?? false,
      health_index: null,
      health_state: null,
      interval_seconds: modeled.intervalSeconds ?? 600,
      risk_index: null,
      schema_version: "monitoring_frame_v1",
      score: null,
      score_ratio: null,
      predicted_anomaly: null,
      scoring_version: null,
      segment_id: null,
      telemetry: telemetry(index),
      threshold: null,
      tick_id: tickId,
      unavailable_reason: null,
    }),
  );
  return {
    active_policy_refs: POLICY,
    commit_status: "committed",
    committed_at: "2026-08-11T10:00:00Z",
    cursor,
    frames: [modeledFrame, ...contextualFrames],
    input_record_hash: String(cursor + 1).repeat(64),
    schema_version: "monitoring_replay_tick_v1",
    sequence: cursor + 1,
    session_id: SESSION_ID,
    snapshot_id: snapshotId,
    source_time: sourceTime,
    tick_id: tickId,
  };
}

function sessionState(
  revision: number,
  committedTick: ReplayTick | null,
  lastTriggerId: string | null = null,
  nextEventSequence = 1,
  variableRunSlotsReserved = 0,
): ReplaySessionState {
  const executionCursor = committedTick?.cursor ?? null;
  const modeledFrame = committedTick?.frames.find(
    (frame) => frame.analysis_status === "modeled",
  );
  const checkpoints: ReplayAssetCheckpoint[] = ASSET_SPECS.map((spec) => {
    const frame = committedTick?.frames.find(
      (candidate) =>
        candidate.asset_id === spec.asset_id && candidate.channel_id === spec.channel_id,
    );
    const modeled = spec.analysis_status === "modeled";
    const healthState = modeledFrame?.analysis_status === "modeled"
      ? modeledFrame.health_state
      : "warning";
    const healthIndex = modeledFrame?.analysis_status === "modeled"
      ? modeledFrame.health_index
      : 30;
    return {
      alert_persistence_count: modeled && healthState !== "nominal" ? 1 : 0,
      analysis_status: spec.analysis_status,
      asset_id: spec.asset_id,
      last_frame_id: frame?.frame_id ?? (modeled ? "bootstrap:bearing_1" : null),
      last_health_state: modeled ? healthState : null,
      last_source_time: committedTick?.source_time ?? (modeled ? "2004-02-14T11:50:00" : null),
      raw_health_history: modeled ? [healthIndex] : [],
      recovery_persistence_count: modeled && healthState === "nominal" ? 1 : 0,
      scoring_version: modeled ? POLICY.scoring_version : null,
      segment_id: frame?.segment_id ?? 0,
      smoothed_health_history: modeled ? [healthIndex] : [],
    };
  });
  return {
    active_child_run_id: null,
    active_policy_refs: POLICY,
    activation_checkpoint: activationCheckpoint(
      committedTick,
      lastTriggerId,
      nextEventSequence,
      variableRunSlotsReserved,
    ),
    asset_checkpoints: checkpoints,
    child_run_ids: [],
    config_sha256: "c".repeat(64),
    execution_cursor: executionCursor,
    failure_reason: null,
    last_command_id: revision ? `fixture-step-${revision}` : null,
    last_committed_tick_id: committedTick?.tick_id ?? null,
    last_trigger_id: lastTriggerId,
    mode: "manual",
    revision,
    schema_version: "monitoring_replay_session_state_v1",
    sequence: revision,
    session_id: SESSION_ID,
    speed_multiplier: 1,
    status: executionCursor === null ? "ready" : "paused",
    updated_at: "2026-08-11T10:00:00Z",
  };
}

function activationCheckpoint(
  committedTick: ReplayTick | null,
  lastTriggerId: string | null,
  nextEventSequence: number,
  variableRunSlotsReserved: number,
): ReplayActivationCheckpoint {
  const hasEpisode = lastTriggerId !== null;
  return {
    activation_version: POLICY.activation_version,
    alert_episode_handled_trigger_id: lastTriggerId,
    alert_episode_id: hasEpisode ? "episode-bearing-1-warning" : null,
    alert_episode_start_cursor: hasEpisode ? 0 : null,
    alert_episode_start_snapshot_id: hasEpisode ? "2004.02.14.12.00.00" : null,
    last_evaluated_cursor: committedTick?.cursor ?? null,
    last_evaluated_tick_id: committedTick?.tick_id ?? null,
    next_event_sequence: nextEventSequence,
    persistent_alert_armed: !hasEpisode,
    rule_checkpoints: hasEpisode && committedTick
      ? [{
          last_effective_source_time: "2004-02-14T12:01:00",
          last_effective_trigger_id: lastTriggerId,
          trigger_type: "state_transition",
        }]
      : [],
    variable_run_slots_reserved: variableRunSlotsReserved,
  };
}

function stepResponse(
  committedTick: ReplayTick,
  state: ReplaySessionState,
  triggers: MonitoringTriggerEvent[],
): MonitoringStepResponse {
  return {
    receipt: {
      accepted_revision: state.revision,
      command_id: `fixture-step-${state.revision}`,
      expected_revision: state.revision - 1,
      outcome: "applied",
      reason: null,
      recorded_at: "2026-08-11T10:00:00Z",
      schema_version: "monitoring_replay_step_receipt_v1",
      session_id: SESSION_ID,
      tick_id: committedTick.tick_id,
    },
    state,
    tick: committedTick,
    triggers,
  };
}

function stateTransitionTrigger(
  tickValue: ReplayTick,
  options: {
    eventId: string;
    lifecycleRevision: number;
    lifecycleStatus: "emitted" | "failed";
    previousEventId?: string;
    sequence: number;
  },
): MonitoringTriggerEvent {
  return {
    activation_policy_sha256: "d".repeat(64),
    activation_version: POLICY.activation_version,
    asset_id: "bearing_1",
    budget_reservation_index: options.lifecycleStatus === "emitted" ? 1 : null,
    child_run_id: null,
    coalesced_into_trigger_id: null,
    coalescing_group: "health_episode",
    condition_start_cursor: tickValue.cursor,
    counts_toward_variable_budget: true,
    cooldown_source_seconds: 0,
    cutoff_cursor: tickValue.cursor,
    cutoff_source_time: tickValue.source_time,
    dedupe_key: "state-transition:bearing-1:critical",
    episode_id: "episode-bearing-1-warning",
    event_id: options.eventId,
    evidence_refs: ["evidence:fixture:critical"],
    frame_ids: [tickValue.frames[0].frame_id],
    lifecycle_revision: options.lifecycleRevision,
    lifecycle_status: options.lifecycleStatus,
    new_state: "critical",
    origin_tick_id: tickValue.tick_id,
    previous_event_id: options.previousEventId ?? null,
    previous_state: "warning",
    priority: 90,
    reason: options.lifecycleStatus === "emitted"
      ? "El canal modelado cambia de advertencia a crítico en el prefijo ejecutado."
      : "La revisión no llegó a despacharse; no existe una run hija enlazada.",
    reason_code: "health_state_escalation",
    rearm_policy: "after_recovery",
    recorded_at: options.lifecycleStatus === "emitted"
      ? "2026-08-11T10:00:01Z"
      : "2026-08-11T10:00:03Z",
    requested_roles: REQUESTED_ROLES,
    schema_version: "monitoring_trigger_event_v1",
    sequence: options.sequence,
    session_id: SESSION_ID,
    snapshot_end_id: tickValue.snapshot_id,
    snapshot_start_id: tickValue.snapshot_id,
    suppression_reason: null,
    suppressed_by_trigger_id: null,
    trigger_id: "trg-monitoring-critical",
    trigger_type: "state_transition",
  };
}

function persistentAlertTrigger(
  tickValue: ReplayTick,
  lifecycleStatus: "suppressed",
  sequence: number,
): MonitoringTriggerEvent {
  return {
    activation_policy_sha256: "d".repeat(64),
    activation_version: POLICY.activation_version,
    asset_id: "bearing_1",
    budget_reservation_index: null,
    child_run_id: null,
    coalesced_into_trigger_id: null,
    coalescing_group: "health_episode",
    condition_start_cursor: 0,
    counts_toward_variable_budget: true,
    cooldown_source_seconds: 600,
    cutoff_cursor: tickValue.cursor,
    cutoff_source_time: tickValue.source_time,
    dedupe_key: "persistent-alert:bearing-1:episode-bearing-1-warning",
    episode_id: "episode-bearing-1-warning",
    event_id: "evt-monitoring-persistent-suppressed",
    evidence_refs: ["evidence:fixture:persistence"],
    frame_ids: [tickValue.frames[0].frame_id],
    lifecycle_revision: 1,
    lifecycle_status: lifecycleStatus,
    new_state: null,
    origin_tick_id: tickValue.tick_id,
    previous_event_id: null,
    previous_state: null,
    priority: 70,
    reason: "La alerta persistente pertenece al episodio ya cubierto por el cambio crítico.",
    reason_code: "persistent_confirmation",
    rearm_policy: "after_recovery",
    recorded_at: "2026-08-11T10:00:01Z",
    requested_roles: REQUESTED_ROLES,
    schema_version: "monitoring_trigger_event_v1",
    sequence,
    session_id: SESSION_ID,
    snapshot_end_id: tickValue.snapshot_id,
    snapshot_start_id: "2004.02.14.12.00.00",
    suppression_reason: "episode_already_covered",
    suppressed_by_trigger_id: "trg-monitoring-critical",
    trigger_id: "trg-persistent-suppressed",
    trigger_type: "persistent_alert",
  };
}

function continuityGapTrigger(
  tickValue: ReplayTick,
  sequence: number,
  coalescedIntoTriggerId: string,
): MonitoringTriggerEvent {
  return {
    activation_policy_sha256: "d".repeat(64),
    activation_version: POLICY.activation_version,
    asset_id: "bearing_1",
    budget_reservation_index: null,
    child_run_id: null,
    coalesced_into_trigger_id: coalescedIntoTriggerId,
    coalescing_group: "health_episode",
    condition_start_cursor: tickValue.cursor,
    counts_toward_variable_budget: true,
    cooldown_source_seconds: 0,
    cutoff_cursor: tickValue.cursor,
    cutoff_source_time: tickValue.source_time,
    dedupe_key: `continuity-gap:bearing-1:${tickValue.tick_id}`,
    episode_id: "episode-bearing-1-warning",
    event_id: "evt-monitoring-gap-coalesced",
    evidence_refs: ["evidence:fixture:gap"],
    frame_ids: [tickValue.frames[0].frame_id],
    lifecycle_revision: 1,
    lifecycle_status: "coalesced",
    new_state: null,
    origin_tick_id: tickValue.tick_id,
    previous_event_id: null,
    previous_state: null,
    priority: 80,
    reason: "El hueco se agrupa en la revisión crítica ya registrada para el episodio.",
    reason_code: "continuity_gap",
    rearm_policy: "after_cooldown",
    recorded_at: "2026-08-11T10:00:02Z",
    requested_roles: REQUESTED_ROLES,
    schema_version: "monitoring_trigger_event_v1",
    sequence,
    session_id: SESSION_ID,
    snapshot_end_id: tickValue.snapshot_id,
    snapshot_start_id: tickValue.snapshot_id,
    suppression_reason: null,
    suppressed_by_trigger_id: null,
    trigger_id: "trg-gap-coalesced",
    trigger_type: "continuity_gap",
  };
}
