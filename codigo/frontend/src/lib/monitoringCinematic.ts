import type {
  AgentRuntimeEvent,
  HealthState,
  MonitoringAnalysisStatus,
  MonitoringEvidenceCampaignView,
  MonitoringTriggerEvent,
  ReplayAssetSpec,
  ReplayTick,
} from "../types";
import {
  AGENT_PROFILES,
  agentDecisionPayload,
  isRecord,
  monitoringEvidenceCatalogModel,
  monitoringPolicyProposalModel,
  stringValue,
} from "./agentRuntime";
import { buildAgentStoryModel } from "./agentStory";

export interface MonitoringCinematicBearing {
  analysisStatus: MonitoringAnalysisStatus;
  assetId: string;
  channelId: string;
  gapDetected: boolean;
  healthIndex: number | null;
  healthState: HealthState | null;
  label: string;
  riskIndex: number | null;
  scoreRatio: number | null;
  signalPeakAbs: number | null;
  signalRms: number | null;
}

export interface MonitoringCinematicTrendPoint {
  cursor: number;
  gapDetected: boolean;
  healthIndex: number;
  healthState: HealthState;
  riskIndex: number;
  scoreRatio: number;
  sourceTime: string;
}

export interface MonitoringCinematicTelemetryPoint {
  cursor: number;
  gapDetected: boolean;
  signalPeakAbs: number;
  signalRms: number;
  sourceTime: string;
}

export interface MonitoringCinematicAgentCell {
  agentId: string;
  agentLabel: string;
  confidence: number | null;
  decisionEventId: string | null;
  evidenceHandles: string[];
  expectedObservation: string | null;
  falsificationCriterion: string | null;
  generationOrigin: string | null;
  hypothesis: string | null;
  recommendedAction: string | null;
  role: string;
  state: "pending" | "first_pass" | "repaired" | "fallback" | "error";
  validationStatus: string | null;
}

export interface MonitoringCinematicProposal {
  actionCounts: Record<string, number>;
  aggregateAction: string | null;
  agreementStatus: string;
  applicationStatus: "not_applied";
  humanReviewRecommended: boolean;
  status: string;
}

export interface MonitoringCinematicAct {
  agents: MonitoringCinematicAgentCell[];
  childRunId: string | null;
  cutoffCursor: number;
  lifecycle: string;
  ordinal: number;
  proposal: MonitoringCinematicProposal | null;
  sourceTime: string;
  triggerId: string | null;
  triggerType: string;
  visible: boolean;
}

export interface MonitoringCinematicModel {
  activeAct: MonitoringCinematicAct | null;
  activeAgent: MonitoringCinematicAgentCell | null;
  bearings: MonitoringCinematicBearing[];
  currentSourceTime: string | null;
  currentTick: ReplayTick | null;
  healthRiskSeries: MonitoringCinematicTrendPoint[];
  phase: "pre_roll" | "agentic_window" | "completed" | "idle";
  progressRatio: number;
  scoreRatioSeries: MonitoringCinematicTrendPoint[];
  storyboard: MonitoringCinematicAct[];
  telemetrySeriesByAssetId: Record<string, MonitoringCinematicTelemetryPoint[]>;
  visibleCursor: number | null;
  visibleTriggers: MonitoringTriggerEvent[];
}

export function buildMonitoringCinematicModel({
  assetSpecs,
  campaign,
  inspectionCursor,
  runEventsByChildId,
  ticks,
  triggers,
}: {
  assetSpecs: ReplayAssetSpec[];
  campaign: MonitoringEvidenceCampaignView | null;
  inspectionCursor: number | null;
  runEventsByChildId: Record<string, AgentRuntimeEvent[]>;
  ticks: ReplayTick[];
  triggers: MonitoringTriggerEvent[];
}): MonitoringCinematicModel {
  const orderedTicks = [...ticks].sort((left, right) => left.cursor - right.cursor);
  const maximumCursor = orderedTicks[orderedTicks.length - 1]?.cursor ?? null;
  const visibleCursor = inspectionCursor === null
    ? maximumCursor
    : maximumCursor === null ? null : Math.min(inspectionCursor, maximumCursor);
  const visibleTicks = visibleCursor === null
    ? []
    : orderedTicks.filter((tick) => tick.cursor <= visibleCursor);
  const currentTick = visibleTicks[visibleTicks.length - 1] ?? null;
  const bearings = assetSpecs.map((asset, index) => {
    const frame = currentTick?.frames.find(
      (item) => item.asset_id === asset.asset_id && item.channel_id === asset.channel_id,
    ) ?? null;
    return {
      analysisStatus: frame?.analysis_status ?? asset.analysis_status,
      assetId: asset.asset_id,
      channelId: asset.channel_id,
      gapDetected: frame?.gap_detected ?? false,
      healthIndex: frame?.analysis_status === "modeled" ? frame.health_index : null,
      healthState: frame?.analysis_status === "modeled" ? frame.health_state : null,
      label: `B${index + 1}`,
      riskIndex: frame?.analysis_status === "modeled" ? frame.risk_index : null,
      scoreRatio: frame?.analysis_status === "modeled" ? frame.score_ratio : null,
      signalPeakAbs: frame?.telemetry?.signal_peak_abs ?? null,
      signalRms: frame?.telemetry?.signal_rms ?? null,
    } satisfies MonitoringCinematicBearing;
  });
  const trends = visibleTicks.flatMap((tick) => {
    const frame = tick.frames.find((item) => item.analysis_status === "modeled");
    return frame?.analysis_status === "modeled"
      ? [{
          cursor: tick.cursor,
          gapDetected: frame.gap_detected,
          healthIndex: frame.health_index,
          healthState: frame.health_state,
          riskIndex: frame.risk_index,
          scoreRatio: frame.score_ratio,
          sourceTime: tick.source_time,
        } satisfies MonitoringCinematicTrendPoint]
      : [];
  });
  const telemetrySeriesByAssetId = Object.fromEntries(assetSpecs.map((asset) => [
    asset.asset_id,
    visibleTicks.flatMap((tick) => {
      const frame = tick.frames.find(
        (item) => item.asset_id === asset.asset_id && item.channel_id === asset.channel_id,
      );
      return frame?.telemetry
        ? [{
            cursor: tick.cursor,
            gapDetected: frame.gap_detected,
            signalPeakAbs: frame.telemetry.signal_peak_abs,
            signalRms: frame.telemetry.signal_rms,
            sourceTime: tick.source_time,
          } satisfies MonitoringCinematicTelemetryPoint]
        : [];
    }),
  ]));
  const storyboard = campaign
    ? campaign.reviews.map((review) => {
        const visible = visibleCursor !== null && visibleCursor >= review.cutoff_cursor;
        const events = visible && review.child_run_id
          ? runEventsByChildId[review.child_run_id] ?? []
          : [];
        return {
          agents: projectAgents(events),
          childRunId: review.child_run_id,
          cutoffCursor: review.cutoff_cursor,
          lifecycle: visible ? review.lifecycle : "pending",
          ordinal: review.ordinal,
          proposal: projectProposal(events),
          sourceTime: review.source_time,
          triggerId: visible ? review.trigger_id : null,
          triggerType: review.trigger_type,
          visible,
        } satisfies MonitoringCinematicAct;
      })
    : [];
  const activeAct = [...storyboard].reverse().find((act) => act.visible) ?? null;
  const activeAgent = activeAct
    ? [...activeAct.agents].reverse().find((agent) => agent.state !== "pending") ?? null
    : null;
  const visibleTriggers = visibleCursor === null
    ? []
    : latestTriggersByIdentity(triggers).filter(
        (trigger) => trigger.cutoff_cursor !== null && trigger.cutoff_cursor <= visibleCursor,
      );

  return {
    activeAct,
    activeAgent,
    bearings,
    currentSourceTime: currentTick?.source_time ?? null,
    currentTick,
    healthRiskSeries: trends,
    phase: cinematicPhase(campaign, visibleCursor),
    progressRatio: visibleCursor === null
      ? 0
      : Math.min(1, (visibleCursor + 1) / (campaign?.expected_total_monitoring_ticks ?? 689)),
    scoreRatioSeries: trends,
    storyboard,
    telemetrySeriesByAssetId,
    visibleCursor,
    visibleTriggers,
  };
}

function projectAgents(events: AgentRuntimeEvent[]): MonitoringCinematicAgentCell[] {
  const story = buildAgentStoryModel(events, null, null);
  const proposal = monitoringPolicyProposalModel(events);
  return AGENT_PROFILES.map((profile) => {
    const agent = story.agents.find((item) => item.id === profile.id);
    const decision = agent?.latestDecisionEvent ?? null;
    const payload = decision ? agentDecisionPayload(decision) : null;
    const trace = payload && isRecord(payload.generation_trace)
      ? payload.generation_trace
      : null;
    const evidence = decision ? monitoringEvidenceCatalogModel(decision) : null;
    const contribution = proposal?.contributions.find(
      (item) => item.agentId === profile.id,
    ) ?? null;
    return {
      agentId: profile.id,
      agentLabel: profile.label,
      confidence: decision?.confidence ?? null,
      decisionEventId: decision?.event_id ?? null,
      evidenceHandles: evidence?.selectedHandles ?? [],
      expectedObservation: agent?.primaryHypothesis?.expectedObservation ?? null,
      falsificationCriterion: agent?.primaryHypothesis?.falsificationCriterion ?? null,
      generationOrigin: trace ? stringValue(trace.origin) : null,
      hypothesis: agent?.primaryHypothesis?.statement ?? null,
      recommendedAction: contribution?.recommendedAction
        ?? (payload ? stringValue(payload.recommended_action) : null),
      role: profile.role,
      state: agentState(agent?.agenticState ?? "unknown", Boolean(decision)),
      validationStatus: trace ? stringValue(trace.validation_status) : null,
    } satisfies MonitoringCinematicAgentCell;
  });
}

function latestTriggersByIdentity(
  triggers: MonitoringTriggerEvent[],
): MonitoringTriggerEvent[] {
  const latest = new Map<string, MonitoringTriggerEvent>();
  for (const trigger of triggers) {
    const current = latest.get(trigger.trigger_id);
    if (
      !current
      || trigger.lifecycle_revision > current.lifecycle_revision
      || (
        trigger.lifecycle_revision === current.lifecycle_revision
        && trigger.sequence > current.sequence
      )
    ) {
      latest.set(trigger.trigger_id, trigger);
    }
  }
  return [...latest.values()].sort(
    (left, right) => (left.cutoff_cursor ?? -1) - (right.cutoff_cursor ?? -1),
  );
}

function projectProposal(events: AgentRuntimeEvent[]): MonitoringCinematicProposal | null {
  const proposal = monitoringPolicyProposalModel(events);
  if (!proposal) return null;
  const actionCounts = proposal.contributions.reduce<Record<string, number>>(
    (counts, item) => {
      counts[item.recommendedAction] = (counts[item.recommendedAction] ?? 0) + 1;
      return counts;
    },
    {},
  );
  return {
    actionCounts,
    aggregateAction: proposal.aggregateAction,
    agreementStatus: proposal.agreementStatus,
    applicationStatus: proposal.applicationStatus,
    humanReviewRecommended: proposal.humanReviewRecommended,
    status: proposal.status,
  };
}

function agentState(
  state: ReturnType<typeof buildAgentStoryModel>["agents"][number]["agenticState"],
  hasDecision: boolean,
): MonitoringCinematicAgentCell["state"] {
  if (!hasDecision) return "pending";
  if (
    state === "fallback"
    || state === "non_agentic"
    || state === "llm_protocol_restricted"
  ) return "fallback";
  if (state === "llm_repaired") return "repaired";
  if (state === "unknown") return "error";
  return "first_pass";
}

function cinematicPhase(
  campaign: MonitoringEvidenceCampaignView | null,
  cursor: number | null,
): MonitoringCinematicModel["phase"] {
  if (cursor === null) return "idle";
  if (
    campaign !== null
    && ["completed", "failed", "interrupted"].includes(campaign.status)
  ) {
    return "completed";
  }
  if (cursor < (campaign?.agentic_window_start_cursor ?? 353)) return "pre_roll";
  return "agentic_window";
}
