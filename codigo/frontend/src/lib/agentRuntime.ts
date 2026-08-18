import { STAGE_LABELS } from "../constants/pipeline";
import { confidenceText } from "./formatters";
import type { AgentRuntimeEvent, PipelineRunStage } from "../types";

export const AGENT_PROFILES = [
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
  {
    id: "report_verifier",
    label: "Verificador",
    role: "Auditoria",
    node: "report_verifier",
  },
] as const;

export interface AgentConversationMessage {
  id: string;
  sequence: number;
  agentId: string;
  agentLabel: string;
  role: string;
  title: string;
  text: string;
  createdAt: string;
  stage: string | null;
  status: "normal" | "success" | "warning" | "error";
  badges: string[];
}

export type HypothesisAssessmentStatus =
  | "pending"
  | "supported_in_run"
  | "partially_supported"
  | "contradicted_in_run"
  | "inconclusive"
  | "not_evaluable";

const COMMON_HYPOTHESIS_KINDS = new Set([
  "routing_readiness",
  "data_quality",
  "temporal_representation",
  "model_performance",
  "operational_acceptance",
  "report_grounding",
  "report_fidelity",
  "revision_effectiveness",
]);

export interface AgentHypothesisViewModel {
  assumptions: string[];
  assessmentStatus: HypothesisAssessmentStatus;
  contractComplete: boolean;
  evidenceCutoff: string | null;
  evidenceRefs: string[];
  expectedObservation: string | null;
  falsificationCriterion: string | null;
  kind: string | null;
  label: string;
  riskNotes: string[];
  scope: string | null;
  source: "common_contract" | "legacy_modeler";
  statement: string;
}

export interface AgentDecisionEvidenceModel {
  agentId: string;
  decisionId: string | null;
  decisionKind: string | null;
  hypotheses: AgentHypothesisViewModel[];
  primaryHypothesis: AgentHypothesisViewModel | null;
}

export interface MonitoringEvidenceRecordViewModel {
  analysisStatus: string | null;
  assetId: string | null;
  channelId: string | null;
  gapDetected: boolean | null;
  handle: string;
  healthState: string | null;
  scoreRatio: number | null;
  snapshotId: string | null;
  sourceTime: string | null;
}

export interface MonitoringEvidenceCatalogViewModel {
  availableHandles: string[];
  catalogSha256: string;
  selectedHandles: string[];
  selectedRecords: MonitoringEvidenceRecordViewModel[];
  supportRefs: string[];
  totalCount: number;
}

export type MonitoringPolicyProposalAction =
  | "maintain_policy"
  | "intensify_observation"
  | "request_human_review"
  | "pause_replay"
  | "insufficient_evidence";

export type MonitoringPolicyProposalKind =
  | "no_change"
  | "observation"
  | "workflow"
  | "abstain";

export interface MonitoringPolicyProposalContributionViewModel {
  actionRationale: string;
  advisorySubject: string;
  agentId: string;
  currentState: string;
  evidenceHandles: string[];
  generationOrigin: string;
  proposalKind: MonitoringPolicyProposalKind;
  proposedState: string;
  recommendedAction: MonitoringPolicyProposalAction;
  requiresHumanReview: boolean;
  riskNotes: string[];
}

export interface MonitoringPolicyProposalViewModel {
  aggregateAction: MonitoringPolicyProposalAction | null;
  aggregateKind: MonitoringPolicyProposalKind | null;
  agreementStatus: "unanimous" | "disagreement" | "invalid_review";
  applicationStatus: "not_applied";
  contributions: MonitoringPolicyProposalContributionViewModel[];
  evidenceCatalogSha256: string;
  humanReviewRecommended: boolean;
  proposalId: string;
  proposalSha256: string;
  status: "advisory_not_applied";
}

export function agentDecisionEvidenceModel(
  event: AgentRuntimeEvent,
): AgentDecisionEvidenceModel {
  const payload = agentDecisionPayload(event);
  const hypotheses = hypothesisViewModelsForPayload(payload);
  return {
    agentId: eventOwnerId(event),
    decisionId: event.decision_id ?? stringValue(payload.decision_id),
    decisionKind: stringValue(payload.decision_kind),
    hypotheses,
    primaryHypothesis: hypotheses.length > 0 ? hypotheses[hypotheses.length - 1] : null,
  };
}

export function monitoringEvidenceCatalogModel(
  event: AgentRuntimeEvent,
): MonitoringEvidenceCatalogViewModel | null {
  const binding = isRecord(event.payload.evidence_binding)
    ? event.payload.evidence_binding
    : null;
  if (binding?.mode !== "server_record_catalog") return null;

  const catalogSha256 = strictString(binding.catalog_sha256);
  const availableHandles = evidenceHandleArray(binding.available_handles);
  const selectedHandles = evidenceHandleArray(binding.selected_handles);
  const supportRefs = strictStringArray(binding.support_refs);
  const totalCount = integerValue(binding.available_count);
  if (
    catalogSha256 === null
    || !/^[0-9a-f]{64}$/.test(catalogSha256)
    || availableHandles.length === 0
    || selectedHandles.length === 0
    || totalCount !== availableHandles.length
    || supportRefs.length !== selectedHandles.length
    || new Set(supportRefs).size !== supportRefs.length
    || availableHandles.some(
      (handle, index) => handle !== `E${String(index + 1).padStart(2, "0")}`,
    )
    || selectedHandles.some((handle) => !availableHandles.includes(handle))
  ) {
    return null;
  }

  const rawRecords = binding.selected_records;
  if (!Array.isArray(rawRecords) || rawRecords.length !== selectedHandles.length) {
    return null;
  }
  const recordsByHandle = new Map<string, MonitoringEvidenceRecordViewModel>();
  for (const candidate of rawRecords) {
    if (!isRecord(candidate)) return null;
    const handle = strictString(candidate.handle);
    if (
      handle === null
      || !selectedHandles.includes(handle)
      || recordsByHandle.has(handle)
    ) {
      return null;
    }
    recordsByHandle.set(handle, {
      analysisStatus: strictString(candidate.analysis_status),
      assetId: strictString(candidate.asset_id),
      channelId: strictString(candidate.channel_id),
      gapDetected: typeof candidate.gap_detected === "boolean"
        ? candidate.gap_detected
        : null,
      handle,
      healthState: strictString(candidate.health_state),
      scoreRatio: numberValue(candidate.score_ratio),
      snapshotId: strictString(candidate.snapshot_id),
      sourceTime: strictString(candidate.source_time),
    });
  }
  const selectedRecords = selectedHandles.map((handle) => recordsByHandle.get(handle));
  if (selectedRecords.some((record) => record === undefined)) return null;

  return {
    availableHandles,
    catalogSha256,
    selectedHandles,
    selectedRecords: selectedRecords as MonitoringEvidenceRecordViewModel[],
    supportRefs,
    totalCount,
  };
}

const MONITORING_POLICY_AGENTS = AGENT_PROFILES.map((profile) => profile.id);
const MONITORING_POLICY_ACTIONS: MonitoringPolicyProposalAction[] = [
  "maintain_policy",
  "intensify_observation",
  "request_human_review",
  "pause_replay",
  "insufficient_evidence",
];
const MONITORING_POLICY_EFFECTS: Record<
  MonitoringPolicyProposalAction,
  {
    kind: MonitoringPolicyProposalKind;
    subject: string;
    current: string;
    proposed: string;
  }
> = {
  maintain_policy: {
    kind: "no_change",
    subject: "policy_configuration",
    current: "unchanged",
    proposed: "unchanged",
  },
  intensify_observation: {
    kind: "observation",
    subject: "observation_cadence",
    current: "current_schedule",
    proposed: "intensification_requested",
  },
  request_human_review: {
    kind: "workflow",
    subject: "human_review",
    current: "not_requested",
    proposed: "requested",
  },
  pause_replay: {
    kind: "workflow",
    subject: "replay_execution",
    current: "current_execution",
    proposed: "pause_requested",
  },
  insufficient_evidence: {
    kind: "abstain",
    subject: "policy_change",
    current: "unchanged",
    proposed: "withheld",
  },
};

export function monitoringPolicyProposalModel(
  events: AgentRuntimeEvent[],
): MonitoringPolicyProposalViewModel | null {
  const proposalEvent = [...events].reverse().find(
    (event) => event.kind === "policy_proposal" && event.source === "system",
  );
  const proposal = proposalEvent && isRecord(proposalEvent.payload.policy_proposal)
    ? proposalEvent.payload.policy_proposal
    : null;
  if (!proposal) return null;

  const proposalId = strictString(proposal.proposal_id);
  const proposalSha256 = strictSha256(proposal.proposal_sha256);
  const evidenceCatalogSha256 = strictSha256(proposal.evidence_catalog_sha256);
  const agreementStatus = proposal.agreement_status;
  const aggregateAction = proposal.aggregate_action;
  const aggregateKind = proposal.aggregate_kind;
  const activePolicyRefs = isRecord(proposal.active_policy_refs)
    ? proposal.active_policy_refs
    : null;
  const bindingsValid = [
    proposal.request_id,
    proposal.child_run_id,
    proposal.session_id,
    proposal.trigger_id,
    proposal.trigger_event_id,
    proposal.origin_tick_id,
    proposal.cutoff_snapshot_id,
    proposal.cutoff_source_time,
    proposal.created_at,
  ].every((value) => strictString(value) !== null)
    && strictSha256(proposal.request_sha256) !== null
    && strictSha256(proposal.causal_view_sha256) !== null
    && Number.isInteger(proposal.cutoff_cursor)
    && Number(proposal.cutoff_cursor) >= 0
    && strictString(activePolicyRefs?.scoring_version) !== null
    && strictString(activePolicyRefs?.activation_version) !== null;
  if (
    proposal.schema_version !== "monitoring_policy_proposal_v1"
    || proposalId === null
    || proposalSha256 === null
    || evidenceCatalogSha256 === null
    || proposal.status !== "advisory_not_applied"
    || proposal.application_status !== "not_applied"
    || proposal.proposal_origin !== "deterministic_server"
    || proposal.policy_validation_eligible !== false
    || !["unanimous", "disagreement", "invalid_review"].includes(String(agreementStatus))
    || typeof proposal.human_review_recommended !== "boolean"
    || !bindingsValid
    || !Array.isArray(proposal.contributions)
    || proposal.contributions.length !== MONITORING_POLICY_AGENTS.length
  ) {
    return null;
  }

  const contributions: MonitoringPolicyProposalContributionViewModel[] = [];
  const decisionIds = new Set<string>();
  const decisionHashes = new Set<string>();
  for (let index = 0; index < proposal.contributions.length; index += 1) {
    const raw = proposal.contributions[index];
    if (!isRecord(raw) || raw.agent_name !== MONITORING_POLICY_AGENTS[index]) return null;
    const action = raw.recommended_action;
    if (!MONITORING_POLICY_ACTIONS.includes(action as MonitoringPolicyProposalAction)) {
      return null;
    }
    const expected = MONITORING_POLICY_EFFECTS[action as MonitoringPolicyProposalAction];
    const handles = evidenceHandleArray(raw.evidence_handles);
    const supportRefs = strictStringArray(raw.evidence_support_refs);
    const risks = strictUniqueStringArray(raw.risk_notes);
    const decisionId = strictString(raw.decision_id);
    const decisionSha256 = strictSha256(raw.decision_sha256);
    const rationale = strictString(raw.action_rationale);
    const generationOrigin = strictString(raw.generation_origin);
    if (
      raw.schema_version !== "policy_proposal_contribution_v1"
      || decisionId === null
      || decisionSha256 === null
      || !["llm", "deterministic", "guardrail_fallback", "protocol_restricted", "unknown"].includes(generationOrigin ?? "")
      || raw.proposal_kind !== expected.kind
      || raw.advisory_subject !== expected.subject
      || raw.current_state !== expected.current
      || raw.proposed_state !== expected.proposed
      || rationale === null
      || risks.length === 0
      || handles.length === 0
      || supportRefs.length !== handles.length
      || new Set(supportRefs).size !== supportRefs.length
      || typeof raw.requires_human_review !== "boolean"
      || (action === "request_human_review" && raw.requires_human_review !== true)
    ) {
      return null;
    }
    if (decisionIds.has(decisionId) || decisionHashes.has(decisionSha256)) return null;
    decisionIds.add(decisionId);
    decisionHashes.add(decisionSha256);

    const boundDecisionEvent = events.find((event) => {
      if (
        !["agent_decision", "supervisor_decision"].includes(event.kind)
        || event.agent_name !== raw.agent_name
      ) {
        return false;
      }
      const decision = agentDecisionPayload(event);
      return decision.decision_id === decisionId
        && decision.decision_sha256 === decisionSha256;
    });
    const boundCatalog = boundDecisionEvent
      ? monitoringEvidenceCatalogModel(boundDecisionEvent)
      : null;
    if (
      boundCatalog === null
      || boundCatalog.catalogSha256 !== evidenceCatalogSha256
      || !sameStrings(handles, boundCatalog.selectedHandles)
      || !sameStrings(supportRefs, boundCatalog.supportRefs)
    ) {
      return null;
    }
    contributions.push({
      actionRationale: rationale,
      advisorySubject: expected.subject,
      agentId: String(raw.agent_name),
      currentState: expected.current,
      evidenceHandles: handles,
      generationOrigin: generationOrigin!,
      proposalKind: expected.kind,
      proposedState: expected.proposed,
      recommendedAction: action as MonitoringPolicyProposalAction,
      requiresHumanReview: raw.requires_human_review,
      riskNotes: risks,
    });
  }

  const actions = new Set(contributions.map((item) => item.recommendedAction));
  const invalidReview = contributions.some((item) => item.generationOrigin !== "llm");
  const expectedAgreement = invalidReview
    ? "invalid_review"
    : actions.size === 1 ? "unanimous" : "disagreement";
  const expectedAggregateAction = expectedAgreement === "unanimous"
    ? contributions[0].recommendedAction
    : null;
  const expectedAggregateKind = expectedAgreement === "unanimous"
    ? contributions[0].proposalKind
    : null;
  const humanReviewRecommended = contributions.some(
    (item) => item.requiresHumanReview,
  );
  if (
    agreementStatus !== expectedAgreement
    || aggregateAction !== expectedAggregateAction
    || aggregateKind !== expectedAggregateKind
    || proposal.human_review_recommended !== humanReviewRecommended
    || proposalEvent?.run_id !== proposal.child_run_id
  ) {
    return null;
  }

  return {
    aggregateAction: expectedAggregateAction,
    aggregateKind: expectedAggregateKind,
    agreementStatus: expectedAgreement,
    applicationStatus: "not_applied",
    contributions,
    evidenceCatalogSha256,
    humanReviewRecommended,
    proposalId,
    proposalSha256,
    status: "advisory_not_applied",
  };
}

function strictSha256(value: unknown): string | null {
  const parsed = strictString(value);
  return parsed !== null && /^[0-9a-f]{64}$/.test(parsed) ? parsed : null;
}

function strictUniqueStringArray(value: unknown): string[] {
  const values = strictStringArray(value);
  return values.length > 0 && new Set(values).size === values.length ? values : [];
}

function sameStrings(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function evidenceHandleArray(value: unknown): string[] {
  const values = strictStringArray(value);
  if (
    values.some((item) => !/^E(?:0[1-9]|[1-9][0-9])$/.test(item))
    || new Set(values).size !== values.length
  ) {
    return [];
  }
  return values;
}

function strictStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const values = value.map(strictString);
  return values.every((item): item is string => item !== null) ? values : [];
}

function strictString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function integerValue(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

export function agentDecisionPayload(
  event: AgentRuntimeEvent,
): Record<string, unknown> {
  const nested = event.payload.decision;
  return isRecord(nested) ? nested : event.payload;
}

export function hypothesisViewModelsForPayload(
  payload: Record<string, unknown>,
): AgentHypothesisViewModel[] {
  const protocolTrace = isRecord(payload.protocol_trace) ? payload.protocol_trace : null;
  const proposal = protocolTrace && isRecord(protocolTrace.agent_proposal)
    ? protocolTrace.agent_proposal
    : null;
  const results: AgentHypothesisViewModel[] = [];
  const append = (
    candidate: Record<string, unknown> | null,
    label: string,
  ) => {
    if (!candidate) return;
    const common = isRecord(candidate.hypothesis) ? candidate.hypothesis : null;
    const statement = stringValue(common?.statement);
    if (statement) {
      results.push({
        assumptions: stringArrayValue(common?.assumptions),
        assessmentStatus: hypothesisAssessmentStatus(candidate),
        contractComplete: isCompleteCommonHypothesisRecord(common),
        evidenceCutoff: stringValue(common?.evidence_cutoff),
        evidenceRefs: stringArrayValue(common?.evidence_refs),
        expectedObservation: stringValue(common?.expected_observation),
        falsificationCriterion: stringValue(common?.falsification_criterion),
        kind: stringValue(common?.kind),
        label,
        riskNotes: stringArrayValue(common?.risk_notes),
        scope: stringValue(common?.scope),
        source: "common_contract",
        statement,
      });
      return;
    }
    const strategy = isRecord(candidate.decision_strategy)
      ? candidate.decision_strategy
      : null;
    const legacyStatement = stringValue(strategy?.hypothesis);
    if (!legacyStatement || results.some((item) => item.statement === legacyStatement)) return;
    results.push({
      assumptions: [],
      assessmentStatus: "not_evaluable",
      contractComplete: false,
      evidenceCutoff: null,
      evidenceRefs: stringArrayValue(strategy?.evidence_refs),
      expectedObservation: null,
      falsificationCriterion: null,
      kind: "model_performance",
      label: `${label} · legacy`,
      riskNotes: stringArrayValue(strategy?.risk_notes),
      scope: null,
      source: "legacy_modeler",
      statement: legacyStatement,
    });
  };
  if (proposal) append(proposal, "Hipotesis propuesta por el LLM");
  append(payload, proposal ? "Hipotesis efectiva" : "Hipotesis operativa");
  return results;
}

export function hasCompleteCommonHypothesisForPayload(
  payload: Record<string, unknown>,
): boolean {
  const hypothesis = isRecord(payload.hypothesis) ? payload.hypothesis : null;
  return isCompleteCommonHypothesisRecord(hypothesis);
}

function isCompleteCommonHypothesisRecord(
  hypothesis: Record<string, unknown> | null,
): boolean {
  if (!hypothesis) return false;
  const requiredTextFields = [
    hypothesis.statement,
    hypothesis.scope,
    hypothesis.evidence_cutoff,
    hypothesis.expected_observation,
    hypothesis.falsification_criterion,
  ];
  return (
    isNonEmptyString(hypothesis.kind)
    && COMMON_HYPOTHESIS_KINDS.has(hypothesis.kind)
    && requiredTextFields.every(isNonEmptyString)
    && isNonEmptyStringArray(hypothesis.evidence_refs)
    && isNonEmptyStringArray(hypothesis.risk_notes)
    && (
      hypothesis.assumptions === undefined
      || isStringArray(hypothesis.assumptions)
    )
  );
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isNonEmptyString);
}

function isNonEmptyStringArray(value: unknown): value is string[] {
  return isStringArray(value) && value.length > 0;
}

function hypothesisAssessmentStatus(
  payload: Record<string, unknown>,
): HypothesisAssessmentStatus {
  const assessment = isRecord(payload.hypothesis_assessment)
    ? payload.hypothesis_assessment
    : null;
  const status = stringValue(assessment?.status);
  if (
    status === "supported_in_run"
    || status === "partially_supported"
    || status === "contradicted_in_run"
    || status === "inconclusive"
    || status === "not_evaluable"
  ) {
    return status;
  }
  return "pending";
}

function stringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => stringValue(item))
    .filter((item): item is string => item !== null);
}

export function eventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
): AgentRuntimeEvent[] {
  return events.filter((event) => eventRelatedAgentId(event) === agentId);
}

export function agentDecisionEventsForAgent(
  events: AgentRuntimeEvent[],
  agentId: string,
): AgentRuntimeEvent[] {
  return events.filter((event) => eventEmittingAgentId(event) === agentId);
}

export function agentConversationMessages(
  events: AgentRuntimeEvent[],
): AgentConversationMessage[] {
  return events
    .filter(isConversationEvent)
    .map((event) => {
      const agentId = eventOwnerId(event);
      const status = conversationStatus(event);
      return {
        id: event.event_id,
        sequence: event.sequence,
        agentId,
        agentLabel: agentLabel(agentId),
        role: conversationRole(agentId),
        title: event.title,
        text: conversationText(event),
        createdAt: event.created_at,
        stage: event.stage,
        status,
        badges: conversationBadges(event),
      };
    });
}

function isConversationEvent(event: AgentRuntimeEvent): boolean {
  if (!["supervisor_decision", "agent_decision", "error"].includes(event.kind)) {
    return false;
  }
  const owner = eventOwnerId(event);
  return AGENT_PROFILES.some((agent) => agent.id === owner);
}

/** Actor para etiquetas de UI; no debe usarse para medir autoria o participacion. */
export function eventOwnerId(event: AgentRuntimeEvent): string {
  return eventEmittingAgentId(event) ?? eventRelatedAgentId(event) ?? "system";
}

/** Agente que emitio realmente una decision, no el rol relacionado con un ejecutor. */
export function eventEmittingAgentId(event: AgentRuntimeEvent): string | null {
  if (event.kind === "supervisor_decision") return "supervisor";
  if (event.kind !== "agent_decision") return null;
  return knownAgentId(event.agent_name) ?? agentIdFromNode(event.node);
}

/** Rol relacionado con un evento; permite asociar memoria o ejecutores sin atribuir autoria. */
export function eventRelatedAgentId(event: AgentRuntimeEvent): string | null {
  const explicitAgent = knownAgentId(event.agent_name);
  if (explicitAgent) return explicitAgent;
  if (event.source === "supervisor") return "supervisor";
  return agentIdFromNode(event.node);
}

function agentIdFromNode(node: string | null): string | null {
  if (!node) return null;
  if (node === "report_verifier") {
    return "report_verifier";
  }
  if (node.includes("modeling")) {
    return "modeler";
  }
  if (node.includes("structuring")) {
    return "structurer";
  }
  if (node.includes("clean")) {
    return "cleaner";
  }
  if (node.includes("evaluation") || node === "evaluator") {
    return "evaluator";
  }
  if (node.includes("report")) {
    return "report_writer";
  }
  if (node === "supervisor") return "supervisor";
  return null;
}

function knownAgentId(value: string | null): string | null {
  return value && AGENT_PROFILES.some((agent) => agent.id === value)
    ? value
    : null;
}

function conversationRole(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.role ?? "Agente";
}

function conversationStatus(event: AgentRuntimeEvent): AgentConversationMessage["status"] {
  if (event.kind === "error") {
    return "error";
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus === "approved") {
    return "success";
  }
  if (verificationStatus === "needs_revision" || verificationStatus === "blocked") {
    return "warning";
  }
  const evaluation = recordFromPayload(event.payload, "evaluation");
  const approved = evaluation?.approved;
  if (approved === true) {
    return "success";
  }
  if (approved === false) {
    return "warning";
  }
  return "normal";
}

function conversationText(event: AgentRuntimeEvent): string {
  if (event.kind === "error") {
    return event.summary;
  }
  const agentId = eventOwnerId(event);
  if (agentId === "supervisor") {
    return supervisorConversationText(event);
  }
  if (agentId === "cleaner") {
    const config = recordFromPayload(event.payload, "cleaning_config");
    const strategy = stringValue(config?.strategy_id);
    return strategy
      ? `Propone la estrategia de limpieza ${strategy}.`
      : conciseEventSummary(event);
  }
  if (agentId === "structurer") {
    const config = recordFromPayload(event.payload, "structuring_config");
    const windowSize = stringValue(config?.window_size);
    const featureSet = stringValue(config?.feature_set) ?? stringValue(config?.feature_mode);
    const parts = [
      windowSize ? `ventanas de ${windowSize}` : null,
      featureSet ? `features ${featureSet}` : null,
    ].filter((item): item is string => item !== null);
    return parts.length > 0
      ? `Organiza la serie temporal con ${parts.join(" y ")}.`
      : conciseEventSummary(event);
  }
  if (agentId === "modeler") {
    const config = recordFromPayload(event.payload, "modeling_config");
    const modelName = stringValue(config?.model_name);
    const threshold = stringValue(config?.threshold_quantile);
    if (modelName && threshold) {
      return `Selecciona ${modelName} con umbral cuantilico ${threshold}.`;
    }
    return modelName ? `Selecciona ${modelName} para el modelado.` : conciseEventSummary(event);
  }
  if (agentId === "evaluator") {
    const evaluation = recordFromPayload(event.payload, "evaluation");
    const summary = stringValue(evaluation?.summary);
    const approved = evaluation?.approved;
    if (summary) {
      return approved === false ? `No aprueba la run: ${summary}` : summary;
    }
    return conciseEventSummary(event);
  }
  if (agentId === "report_writer") {
    const revisionRound = stringValue(event.payload.revision_round);
    const changes = stringArrayFromPayload(event.payload, "changes_summary");
    if (revisionRound) {
      return changes.length > 0
        ? `Revisa el informe en la ronda ${revisionRound}: ${joinShortList(changes)}.`
        : `Revisa el informe en la ronda ${revisionRound}.`;
    }
    return "Prepara el informe final con las secciones y evidencias seleccionadas.";
  }
  if (agentId === "report_verifier") {
    const status = stringFromPayload(event.payload, "verification_status");
    const summary = stringFromPayload(event.payload, "human_summary") ?? event.summary;
    const corrections = stringArrayFromPayload(event.payload, "required_corrections");
    const statusText = status ? `Veredicto: ${verificationStatusLabel(status)}.` : "";
    const correctionText =
      corrections.length > 0 ? ` Pide corregir: ${joinShortList(corrections)}.` : "";
    return `${statusText} ${summary}${correctionText}`.trim();
  }
  return conciseEventSummary(event);
}

function supervisorConversationText(event: AgentRuntimeEvent): string {
  const stopReason = stringFromNestedPayload(event.payload, "decision", "stop_reason");
  if (stopReason) {
    return `Cierra la ejecucion: ${stopReason}.`;
  }
  const next = event.next_node ?? event.next_stage;
  if (next) {
    return `Decide continuar hacia ${readableFlowLabel(next)}.`;
  }
  return conciseEventSummary(event);
}

function conversationBadges(event: AgentRuntimeEvent): string[] {
  const badges: string[] = [];
  if (event.stage) {
    badges.push(STAGE_LABELS[event.stage as PipelineRunStage] ?? readableFlowLabel(event.stage));
  }
  if (event.confidence !== null) {
    badges.push(confidenceText(event.confidence));
  }
  if (event.memory_record_ids.length > 0) {
    badges.push(`${event.memory_record_ids.length} memoria`);
  }
  const verificationStatus = stringFromPayload(event.payload, "verification_status");
  if (verificationStatus) {
    badges.push(verificationStatusLabel(verificationStatus));
  }
  const next = event.next_node ?? event.next_stage;
  if (eventOwnerId(event) === "supervisor" && next) {
    badges.push(`sigue: ${readableFlowLabel(next)}`);
  }
  return badges.slice(0, 4);
}

function conciseEventSummary(event: AgentRuntimeEvent): string {
  return event.summary.length > 220 ? `${event.summary.slice(0, 217)}...` : event.summary;
}

export function readableFlowLabel(value: string): string {
  const labels: Record<string, string> = {
    manifest_executor: "manifest",
    profiler_executor: "perfilado",
    cleaner_agent: "limpiador",
    cleaning_executor: "ejecutor de limpieza",
    structuring_agent: "estructurador",
    structuring_executor: "ejecutor de estructuracion",
    modeling_agent: "modelador",
    modeling_executor: "ejecutor de modelado",
    evaluation_executor: "ejecutor de evaluacion",
    evaluation_agent: "evaluador",
    report_writer: "redactor",
    report_verifier: "verificador",
  };
  return labels[value] ?? value.replace(/_/g, " ");
}

function verificationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    approved: "aprobado",
    needs_revision: "requiere revision",
    blocked: "bloqueado",
  };
  return labels[status] ?? status;
}

export function agentInitials(label: string): string {
  return label
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function recordFromPayload(
  payload: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = payload[key];
  return isRecord(value) ? value : null;
}

export function stringFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  return stringValue(payload[key]);
}

function stringFromNestedPayload(
  payload: Record<string, unknown>,
  key: string,
  nestedKey: string,
): string | null {
  return stringValue(recordFromPayload(payload, key)?.[nestedKey]);
}

export function stringArrayFromPayload(
  payload: Record<string, unknown>,
  key: string,
): string[] {
  const value = payload[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => stringValue(item))
    .filter((item): item is string => item !== null);
}

export function stringValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

export function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function joinShortList(values: string[]): string {
  const visible = values.slice(0, 2);
  const suffix = values.length > visible.length ? ` y ${values.length - visible.length} mas` : "";
  return `${visible.join("; ")}${suffix}`;
}

export function agentLabel(agentId: string): string {
  return AGENT_PROFILES.find((agent) => agent.id === agentId)?.label ?? agentId;
}

export function kindLabel(kind: AgentRuntimeEvent["kind"]): string {
  const labels: Record<AgentRuntimeEvent["kind"], string> = {
    job_status: "Job",
    supervisor_decision: "Supervisor",
    agent_decision: "Decision",
    memory_retrieval: "Memoria",
    policy_proposal: "Propuesta consultiva",
    executor_result: "Ejecutor",
    error: "Error",
  };
  return labels[kind];
}

export function agentEventPlainText(event: AgentRuntimeEvent): string {
  const relatedActor = event.agent_name ? agentLabel(event.agent_name) : null;
  const actor = relatedActor ?? sourceLabel(event);
  const stage = event.stage ? ` durante ${STAGE_LABELS[event.stage as PipelineRunStage] ?? event.stage}` : "";
  const confidence =
    event.confidence === null ? "" : ` con confianza ${confidenceText(event.confidence)}`;
  const next = event.next_node ?? event.next_stage;
  const nextText = next ? ` y propone continuar hacia ${next}` : "";
  const memoryText =
    event.memory_record_ids.length > 0
      ? ` usando ${event.memory_record_ids.length} recuerdo(s) como contexto`
      : "";
  const payloadText = payloadPlainText(event.payload);

  if (event.kind === "memory_retrieval") {
    const recipient = relatedActor ? ` para ${relatedActor}` : "";
    const retrievalEvent =
      typeof event.payload.retrieval_event === "string"
        ? event.payload.retrieval_event
        : "unknown";
    const recordCount = event.memory_record_ids.length;
    const records = recordCount > 0
      ? `${recordCount} recuerdo(s)`
      : "ningun recuerdo";
    const memoryAction: Record<string, string> = {
      retrieval_unavailable: `No se dispuso de contexto RAG${recipient}${stage}`,
      retrieval_requested: `El servicio RAG registra una solicitud de contexto${recipient}${stage}`,
      retrieval_returned: recordCount > 0
        ? `El servicio RAG devuelve ${records} como candidatos${recipient}${stage}`
        : `El servicio RAG no devuelve recuerdos candidatos${recipient}${stage}`,
      retrieval_used: recordCount > 0
        ? `${relatedActor ?? "El agente"} declara usar ${records}${stage}`
        : `${relatedActor ?? "El agente"} registra uso de memoria sin identificadores de recuerdo${stage}`,
      retrieval_rejected_by_agent: recordCount > 0
        ? `${relatedActor ?? "El agente"} descarta los recuerdos recuperados${stage}`
        : `${relatedActor ?? "El agente"} no recibio recuerdos utilizables${stage}`,
      unknown: `El servicio RAG registra actividad${recipient}${stage}`,
    };
    return `${memoryAction[retrievalEvent] ?? memoryAction.unknown}. ${payloadText}`;
  }
  if (event.kind === "policy_proposal") {
    return `El sistema sintetiza una propuesta consultiva sin aplicarla${stage}. ${payloadText}`;
  }
  if (event.kind === "executor_result") {
    const relation = relatedActor ? ` relacionado con ${relatedActor}` : "";
    return `El ejecutor registra un resultado${relation}${stage}. ${payloadText}`;
  }
  if (event.kind === "supervisor_decision" || event.kind === "agent_decision") {
    return `${actor} toma una decision${stage}${confidence}${nextText}${memoryText}. ${payloadText}`;
  }
  if (event.kind === "error") {
    return `${actor} informa de un error${stage}. ${event.summary}`;
  }
  return `${actor} actualiza el estado del job. ${event.summary}`;
}

function payloadPlainText(payload: Record<string, unknown>): string {
  const candidates = [
    ["model_name", "modelo"],
    ["strategy_id", "estrategia"],
    ["decision_id", "decision"],
    ["status", "estado"],
    ["verification_status", "verificacion"],
    ["debate_round", "ronda"],
    ["human_summary", "resumen"],
    ["message", "mensaje"],
    ["n_records", "recuerdos"],
    ["n_artifacts", "artefactos"],
    ["n_unsupported_claims", "claims sin soporte"],
    ["n_misleading_claims", "claims confusos"],
    ["n_missing_limitations", "limitaciones ausentes"],
    ["threshold", "umbral"],
  ];
  const fragments = candidates
    .map(([key, label]) =>
      payload[key] === undefined ? null : `${label}: ${String(payload[key])}`,
    )
    .filter((item): item is string => item !== null);
  for (const key of ["required_corrections", "changes_summary"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "required_corrections" ? "correcciones" : "cambios"}: ${value.length}`);
    }
  }
  for (const key of ["accepted_issue_ids", "rejected_issue_ids"]) {
    const value = payload[key];
    if (Array.isArray(value) && value.length > 0) {
      fragments.push(`${key === "accepted_issue_ids" ? "incidencias aceptadas" : "incidencias rechazadas"}: ${value.length}`);
    }
  }
  return fragments.length > 0
    ? `Campos clave: ${fragments.join(", ")}.`
    : "El JSON adjunto contiene el detalle tecnico completo.";
}

export function sourceLabel(event: AgentRuntimeEvent): string {
  if (event.kind === "agent_decision" || event.kind === "supervisor_decision") {
    if (event.agent_name) return agentLabel(event.agent_name);
  }
  if (event.kind === "error" && event.agent_name) {
    return agentLabel(event.agent_name);
  }
  return kindLabel(event.kind);
}
