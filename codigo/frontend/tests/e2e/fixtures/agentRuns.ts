import type {
  AgentRuntimeEvent,
  RunIndexEntry,
  RunSnapshot,
} from "../../../src/types";

export type AgentRunScenarioId =
  | "exact-seven-agents"
  | "monitoring-record-catalog"
  | "modeler-rag-used"
  | "modeler-rag-filtered-not-used"
  | "modeler-rag-unavailable";

export interface AgentRunScenarioExpectation {
  decisionCount: number;
  fallbackCount: number;
  filteredCount: number;
  firstPassCount: number;
  ignoredCount: number;
  participatingAgentCount: number;
  retrievedCount: number;
  unavailableEventCount: number;
  usedCount: number;
}

export interface AgentRunScenario {
  events: AgentRuntimeEvent[];
  expected: AgentRunScenarioExpectation;
  id: AgentRunScenarioId;
  run: RunIndexEntry;
  snapshot: RunSnapshot;
}

type AgentId =
  | "supervisor"
  | "cleaner"
  | "structurer"
  | "modeler"
  | "evaluator"
  | "report_writer"
  | "report_verifier";

type HypothesisKind =
  | "routing_readiness"
  | "data_quality"
  | "temporal_representation"
  | "model_performance"
  | "operational_acceptance"
  | "report_grounding"
  | "report_fidelity";

interface RuntimeEventInput {
  agentName?: string | null;
  confidence?: number | null;
  decisionId?: string | null;
  kind: AgentRuntimeEvent["kind"];
  memoryContextId?: string | null;
  memoryRecordIds?: string[];
  nextNode?: string | null;
  nextStage?: string | null;
  node?: string | null;
  payload?: Record<string, unknown>;
  rationale?: string | null;
  sequence: number;
  source: AgentRuntimeEvent["source"];
  stage?: string | null;
  summary: string;
  title: string;
}

interface DecisionInput {
  agentId: AgentId;
  decisionData: Record<string, unknown>;
  decisionKind: string;
  hypothesisKind: HypothesisKind;
  hypothesisStatement: string;
  nextNode?: string | null;
  nextStage?: string | null;
  node: string;
  rationale: string;
  sequence: number;
  stage: string;
}

const FIXTURE_STARTED_AT = "2026-08-10T09:00:00.000Z";
const FIXTURE_DATASET = "nasa_ims_bearing";

export const EXACT_SEVEN_AGENTS_SCENARIO = buildExactSevenAgentsScenario();
export const MONITORING_RECORD_CATALOG_SCENARIO =
  buildMonitoringRecordCatalogScenario();
export const MODELER_RAG_USED_SCENARIO = buildModelerRagUsedScenario();
export const MODELER_RAG_FILTERED_NOT_USED_SCENARIO =
  buildModelerRagFilteredNotUsedScenario();
export const MODELER_RAG_UNAVAILABLE_SCENARIO =
  buildModelerRagUnavailableScenario();

export const AGENT_RUN_SCENARIOS: Record<AgentRunScenarioId, AgentRunScenario> = {
  "exact-seven-agents": EXACT_SEVEN_AGENTS_SCENARIO,
  "monitoring-record-catalog": MONITORING_RECORD_CATALOG_SCENARIO,
  "modeler-rag-used": MODELER_RAG_USED_SCENARIO,
  "modeler-rag-filtered-not-used": MODELER_RAG_FILTERED_NOT_USED_SCENARIO,
  "modeler-rag-unavailable": MODELER_RAG_UNAVAILABLE_SCENARIO,
};

export function agentRunScenario(id: AgentRunScenarioId): AgentRunScenario {
  return AGENT_RUN_SCENARIOS[id];
}

function buildExactSevenAgentsScenario(): AgentRunScenario {
  const runId = "e2e-exact-seven-agents";
  const events: AgentRuntimeEvent[] = [
    jobEvent(runId, 1, "running", "Run agentica iniciada."),
    decisionEvent(runId, {
      agentId: "supervisor",
      decisionData: {
        current_stage: "profiling",
        next_node: "cleaner_agent",
        next_stage: "cleaning",
      },
      decisionKind: "routing",
      hypothesisKind: "routing_readiness",
      hypothesisStatement:
        "El perfil disponible contiene evidencia suficiente para iniciar la limpieza.",
      nextNode: "cleaner_agent",
      nextStage: "cleaning",
      node: "supervisor",
      rationale: "El perfil predecisional permite continuar con el flujo previsto.",
      sequence: 2,
      stage: "profiling",
    }),
    decisionEvent(runId, {
      agentId: "cleaner",
      decisionData: {
        cleaning_config: {
          selected_channel: "bearing_1_x",
          strategy_id: "robust_signal_cleaning",
        },
      },
      decisionKind: "cleaning",
      hypothesisKind: "data_quality",
      hypothesisStatement:
        "Una limpieza robusta conservara la estructura temporal relevante de la senal.",
      node: "cleaner_agent",
      rationale: "La estrategia limita valores extremos sin reescribir la señal arbitrariamente.",
      sequence: 3,
      stage: "cleaning",
    }),
    executorEvent(runId, 4, "cleaner", "cleaning", "Limpieza aplicada."),
    decisionEvent(runId, {
      agentId: "structurer",
      decisionData: {
        structuring_config: {
          feature_set: "statistical_vibration",
          overlap: 0.5,
          window_size: 2048,
        },
      },
      decisionKind: "structuring",
      hypothesisKind: "temporal_representation",
      hypothesisStatement:
        "Ventanas solapadas representaran la evolucion temporal sin mezclar el futuro.",
      node: "structuring_agent",
      rationale: "La ventana propuesta mantiene orden temporal y resolucion suficiente.",
      sequence: 5,
      stage: "structuring",
    }),
    executorEvent(runId, 6, "structurer", "structuring", "Ventanas generadas."),
    decisionEvent(runId, {
      agentId: "modeler",
      decisionData: {
        modeling_config: {
          model_name: "isolation_forest",
          n_estimators: 100,
          threshold_quantile: 0.98,
        },
      },
      decisionKind: "modeling",
      hypothesisKind: "model_performance",
      hypothesisStatement:
        "Isolation Forest separara desviaciones persistentes del comportamiento nominal.",
      node: "modeling_agent",
      rationale: "El modelo es compatible con el perfil no supervisado de la run.",
      sequence: 7,
      stage: "modeling",
    }),
    executorEvent(runId, 8, "modeler", "modeling", "Modelo entrenado."),
    decisionEvent(runId, {
      agentId: "evaluator",
      decisionData: {
        evaluation: {
          approved: true,
          summary: "Las metricas registradas permiten continuar al informe.",
        },
      },
      decisionKind: "evaluation",
      hypothesisKind: "operational_acceptance",
      hypothesisStatement:
        "Las metricas observadas cumplen el criterio operativo declarado para esta run.",
      node: "evaluation_agent",
      rationale: "La evaluacion se limita a las metricas presentes en la evidencia.",
      sequence: 9,
      stage: "evaluation",
    }),
    decisionEvent(runId, {
      agentId: "report_writer",
      decisionData: {
        output_format: "markdown",
        revision_round: 1,
      },
      decisionKind: "report_draft",
      hypothesisKind: "report_grounding",
      hypothesisStatement:
        "El informe puede sintetizar la run sin introducir resultados no observados.",
      node: "report_writer",
      rationale: "La redaccion se apoya unicamente en artefactos y decisiones registradas.",
      sequence: 10,
      stage: "reporting",
    }),
    executorEvent(runId, 11, "report_writer", "reporting", "Informe generado."),
    decisionEvent(runId, {
      agentId: "report_verifier",
      decisionData: {
        verification_status: "approved",
      },
      decisionKind: "report_verification",
      hypothesisKind: "report_fidelity",
      hypothesisStatement:
        "Las afirmaciones del informe son trazables a la evidencia registrada.",
      node: "report_verifier",
      rationale: "La comprobacion no detecta afirmaciones fuera del paquete de evidencia.",
      sequence: 12,
      stage: "reporting",
    }),
    jobEvent(runId, 13, "completed", "Run agentica completada."),
  ];
  return scenario(
    "exact-seven-agents",
    runId,
    events,
    {
      decisionCount: 7,
      fallbackCount: 0,
      filteredCount: 0,
      firstPassCount: 7,
      ignoredCount: 0,
      participatingAgentCount: 7,
      retrievedCount: 0,
      unavailableEventCount: 0,
      usedCount: 0,
    },
    true,
  );
}

function buildMonitoringRecordCatalogScenario(): AgentRunScenario {
  const runId = "e2e-monitoring-record-catalog";
  const supportRefs = [
    `causal-record:${"a".repeat(64)}:${"b".repeat(64)}`,
    `causal-record:${"a".repeat(64)}:${"e".repeat(64)}`,
  ];
  const evidenceRecords = {
    E02: {
      analysis_status: "modeled",
      asset_id: "bearing_1",
      channel_id: "channel_1",
      gap_detected: false,
      handle: "E02",
      record_sha256: "2".repeat(64),
      health_state: "warning",
      score_ratio: 1.1458,
      snapshot_id: "set_2_2004_02_17_21_52_39",
      source_time: "2004-02-17T21:52:39Z",
    },
    E05: {
      analysis_status: "telemetry_only",
      asset_id: "bearing_3",
      channel_id: "channel_3",
      gap_detected: true,
      handle: "E05",
      record_sha256: "5".repeat(64),
      health_state: null,
      score_ratio: null,
      snapshot_id: "set_2_2004_02_17_22_02_39",
      source_time: "2004-02-17T22:02:39Z",
    },
  } as const;
  const contributionSpecs = [
    ["supervisor", "maintain_policy", "no_change", "policy_configuration", "unchanged", "unchanged", false, ["E02"]],
    ["cleaner", "intensify_observation", "observation", "observation_cadence", "current_schedule", "intensification_requested", false, ["E02", "E05"]],
    ["structurer", "maintain_policy", "no_change", "policy_configuration", "unchanged", "unchanged", false, ["E02"]],
    ["modeler", "intensify_observation", "observation", "observation_cadence", "current_schedule", "intensification_requested", false, ["E02", "E05"]],
    ["evaluator", "request_human_review", "workflow", "human_review", "not_requested", "requested", true, ["E05"]],
    ["report_writer", "insufficient_evidence", "abstain", "policy_change", "unchanged", "withheld", false, ["E02"]],
    ["report_verifier", "pause_replay", "workflow", "replay_execution", "current_execution", "pause_requested", false, ["E05"]],
  ] as const;
  const contributions = contributionSpecs.map(([
    agentName,
    recommendedAction,
    proposalKind,
    advisorySubject,
    currentState,
    proposedState,
    requiresHumanReview,
    handles,
  ], index) => ({
    action_rationale: `${agentName} declara un efecto operativo que debe contrastarse antes de cualquier cambio.`,
    advisory_subject: advisorySubject,
    agent_name: agentName,
    current_state: currentState,
    decision_id: `${runId}:${agentName}:001`,
    decision_sha256: String(index + 1).repeat(64),
    evidence_handles: handles,
    evidence_support_refs: handles.map((handle) => handle === "E02" ? supportRefs[0] : supportRefs[1]),
    generation_origin: "llm",
    proposal_kind: proposalKind,
    proposed_state: proposedState,
    recommended_action: recommendedAction,
    requires_human_review: requiresHumanReview,
    risk_notes: [`Riesgo ${index + 1}: la recomendación puede no mejorar el detector.`],
    schema_version: "policy_proposal_contribution_v1",
  }));
  const decisionEvents = contributions.map((contribution, index) => {
    const event = decisionEvent(runId, {
      agentId: contribution.agent_name,
      decisionData: {
        action_rationale: contribution.action_rationale,
        decision_sha256: contribution.decision_sha256,
        evidence_refs: contribution.evidence_support_refs,
        recommended_action: contribution.recommended_action,
        requires_human_review: contribution.requires_human_review,
      },
      decisionKind: "monitoring_review",
      hypothesisKind: "operational_acceptance",
      hypothesisStatement: `${contribution.agent_name} plantea una recomendación consultiva sobre la monitorización.`,
      node: contribution.agent_name === "supervisor"
        ? "supervisor"
        : `${contribution.agent_name}_agent`,
      rationale: contribution.action_rationale,
      sequence: index + 2,
      stage: "monitoring_review",
    });
    const decision = event.payload.decision as Record<string, unknown>;
    const hypothesis = decision.hypothesis as Record<string, unknown>;
    event.payload = {
      decision: {
        ...decision,
        hypothesis: {
          ...hypothesis,
          evidence_refs: contribution.evidence_support_refs,
          risk_notes: contribution.risk_notes,
        },
      },
      evidence_binding: {
        available_count: 5,
        available_handles: ["E01", "E02", "E03", "E04", "E05"],
        catalog_sha256: "d".repeat(64),
        causal_scope_refs: ["evidence:e2e-monitoring-record-catalog"],
        mode: "server_record_catalog",
        selection_origin: "agent",
        selected_handles: contribution.evidence_handles,
        selected_records: contribution.evidence_handles.map(
          (handle) => evidenceRecords[handle],
        ),
        support_refs: contribution.evidence_support_refs,
      },
    };
    return event;
  });
  const policyProposalEvent = runtimeEvent(runId, {
    kind: "policy_proposal",
    node: "policy_proposal_builder",
    payload: {
      policy_proposal: {
        active_policy_refs: {
          activation_version: "activation_policy_v1",
          scoring_version: "scoring_policy_v1",
        },
        aggregate_action: null,
        aggregate_kind: null,
        agreement_status: "disagreement",
        application_status: "not_applied",
        causal_view_sha256: "c".repeat(64),
        child_run_id: runId,
        contributions,
        created_at: eventTime(3),
        cutoff_cursor: 17,
        cutoff_snapshot_id: "set_2_2004_02_17_22_02_39",
        cutoff_source_time: "2004-02-17T22:02:39Z",
        evidence_catalog_sha256: "d".repeat(64),
        human_review_recommended: true,
        origin_tick_id: `${runId}:tick:017`,
        policy_validation_eligible: false,
        proposal_id: `${runId}:policy-proposal`,
        proposal_origin: "deterministic_server",
        proposal_sha256: "f".repeat(64),
        request_id: `${runId}:request`,
        request_sha256: "a".repeat(64),
        schema_version: "monitoring_policy_proposal_v1",
        session_id: "e2e-monitoring-session",
        status: "advisory_not_applied",
        trigger_event_id: `${runId}:trigger-event`,
        trigger_id: `${runId}:trigger`,
      },
    },
    sequence: 9,
    source: "system",
    stage: "monitoring_review",
    summary: "Siete recomendaciones sintetizadas sin aplicar cambios.",
    title: "Propuesta consultiva de política",
  });
  return scenario(
    "monitoring-record-catalog",
    runId,
    [
      jobEvent(runId, 1, "running", "Revision de monitorizacion iniciada."),
      ...decisionEvents,
      policyProposalEvent,
      jobEvent(runId, 10, "completed", "Revision de monitorizacion completada."),
    ],
    {
      decisionCount: 7,
      fallbackCount: 0,
      filteredCount: 0,
      firstPassCount: 7,
      ignoredCount: 0,
      participatingAgentCount: 7,
      retrievedCount: 0,
      unavailableEventCount: 0,
      usedCount: 0,
    },
    true,
  );
}

function buildModelerRagUsedScenario(): AgentRunScenario {
  const runId = "e2e-modeler-rag-used";
  const contextId = `${runId}:modeler:memory`;
  const decisionSequence = 4;
  const decisionId = `${runId}:modeler:001`;
  const memoryId = "mem-compatible";
  const events = [
    jobEvent(runId, 1, "running", "Run con memoria iniciada."),
    retrievalRequestedEvent(runId, 2, contextId),
    retrievalReturnedEvent(runId, 3, contextId, [memoryId]),
    modelerDecisionEvent(runId, decisionSequence, {
      memory_context_id: contextId,
      memory_record_ids: [memoryId],
      memory_record_uses: [
        {
          influence_summary: "Se adopto como antecedente metodologico, no como prueba del resultado.",
          memory_record_id: memoryId,
          risk_mitigation: "La hipotesis permanece pendiente de contraste en esta run.",
          usage: "adapted",
        },
      ],
      memory_usage_summary:
        "El recuerdo se cito como antecedente metodologico para configurar el modelo.",
      used_memory_context: true,
    }),
    memoryUsageEvent(runId, 5, contextId, decisionId, [memoryId], [memoryId]),
    executorEvent(runId, 6, "modeler", "modeling", "Modelo entrenado."),
    jobEvent(runId, 7, "completed", "Run con memoria completada."),
  ];
  return scenario("modeler-rag-used", runId, events, {
    decisionCount: 1,
    fallbackCount: 0,
    filteredCount: 0,
    firstPassCount: 1,
    ignoredCount: 0,
    participatingAgentCount: 1,
    retrievedCount: 1,
    unavailableEventCount: 0,
    usedCount: 1,
  });
}

function buildModelerRagFilteredNotUsedScenario(): AgentRunScenario {
  const runId = "e2e-modeler-rag-filtered-not-used";
  const contextId = `${runId}:modeler:memory`;
  const decisionSequence = 4;
  const decisionId = `${runId}:modeler:001`;
  const effectiveId = "mem-effective";
  const filteredId = "mem-filtered";
  const events = [
    jobEvent(runId, 1, "running", "Run con control de calidad RAG iniciada."),
    retrievalRequestedEvent(runId, 2, contextId),
    retrievalReturnedEvent(runId, 3, contextId, [effectiveId], {
      effectiveCount: 1,
      excluded: [
        {
          memory_record_id: filteredId,
          reason_codes: ["profile_conflict"],
        },
      ],
      rawCount: 2,
    }),
    modelerDecisionEvent(runId, decisionSequence, {
      memory_context_id: contextId,
      memory_record_ids: [],
      memory_record_uses: [],
      used_memory_context: false,
    }),
    memoryUsageEvent(runId, 5, contextId, decisionId, [effectiveId], []),
    executorEvent(runId, 6, "modeler", "modeling", "Modelo entrenado."),
    jobEvent(runId, 7, "completed", "Run con control de calidad RAG completada."),
  ];
  return scenario("modeler-rag-filtered-not-used", runId, events, {
    decisionCount: 1,
    fallbackCount: 0,
    filteredCount: 1,
    firstPassCount: 1,
    ignoredCount: 1,
    participatingAgentCount: 1,
    retrievedCount: 1,
    unavailableEventCount: 0,
    usedCount: 0,
  });
}

function buildModelerRagUnavailableScenario(): AgentRunScenario {
  const runId = "e2e-modeler-rag-unavailable";
  const decisionSequence = 3;
  const events = [
    jobEvent(runId, 1, "running", "Run sin contexto RAG disponible iniciada."),
    runtimeEvent(runId, {
      agentName: "modeler",
      kind: "memory_retrieval",
      node: "modeler_memory",
      payload: {
        available: false,
        items: [],
        reason: "memory disabled or no memory store configured",
        retrieval_event: "retrieval_unavailable",
      },
      sequence: 2,
      source: "memory",
      stage: "modeling",
      summary: "No se recupero contexto de memoria para esta decision.",
      title: "Memoria para modeler",
    }),
    modelerDecisionEvent(runId, decisionSequence, {}),
    executorEvent(runId, 4, "modeler", "modeling", "Modelo entrenado."),
    jobEvent(runId, 5, "completed", "Run sin contexto RAG disponible completada."),
  ];
  return scenario("modeler-rag-unavailable", runId, events, {
    decisionCount: 1,
    fallbackCount: 0,
    filteredCount: 0,
    firstPassCount: 1,
    ignoredCount: 0,
    participatingAgentCount: 1,
    retrievedCount: 0,
    unavailableEventCount: 1,
    usedCount: 0,
  });
}

function modelerDecisionEvent(
  runId: string,
  sequence: number,
  memoryDeclaration: Record<string, unknown>,
): AgentRuntimeEvent {
  return decisionEvent(runId, {
    agentId: "modeler",
    decisionData: {
      modeling_config: {
        model_name: "isolation_forest",
        n_estimators: 100,
        threshold_quantile: 0.98,
      },
      ...memoryDeclaration,
    },
    decisionKind: "modeling",
    hypothesisKind: "model_performance",
    hypothesisStatement:
      "Isolation Forest separara desviaciones persistentes del comportamiento nominal.",
    node: "modeling_agent",
    rationale: "La configuracion se propone con la evidencia disponible antes de ejecutar.",
    sequence,
    stage: "modeling",
  });
}

function decisionEvent(runId: string, input: DecisionInput): AgentRuntimeEvent {
  const decisionId = `${runId}:${input.agentId}:001`;
  const confidence = 0.82;
  const decision: Record<string, unknown> = {
    agent_name: input.agentId,
    confidence,
    created_at: eventTime(input.sequence),
    decision_id: decisionId,
    decision_kind: input.decisionKind,
    generation_trace: {
      attempt_id: `${decisionId}:attempt:001`,
      attempt_index: 1,
      fallback_cause: null,
      fallback_from_attempt_id: null,
      origin: "llm",
      validation_status: "validated",
    },
    hypothesis: {
      assumptions: [],
      evidence_cutoff: "Evidencia disponible antes de la decision de esta fixture.",
      evidence_refs: [`fixture://${runId}/${input.agentId}/predecision`],
      expected_observation:
        "La evidencia posterior permitira contrastar la hipotesis sin alterar la decision original.",
      falsification_criterion:
        "La evidencia posterior contradice la observacion esperada o resulta insuficiente.",
      kind: input.hypothesisKind,
      risk_notes: ["Una ejecucion correcta no confirma por si sola la hipotesis."],
      scope: `Run sintetica ${runId}; rol ${input.agentId}.`,
      statement: input.hypothesisStatement,
    },
    next_node: input.nextNode ?? null,
    next_stage: input.nextStage ?? null,
    rationale: input.rationale,
    ...input.decisionData,
  };
  const memoryContextId = stringOrNull(decision.memory_context_id);
  const memoryRecordIds = stringArray(decision.memory_record_ids);
  return runtimeEvent(runId, {
    agentName: input.agentId,
    confidence,
    decisionId,
    kind: input.agentId === "supervisor" ? "supervisor_decision" : "agent_decision",
    memoryContextId,
    memoryRecordIds,
    nextNode: input.nextNode ?? null,
    nextStage: input.nextStage ?? null,
    node: input.node,
    payload: { decision },
    rationale: input.rationale,
    sequence: input.sequence,
    source: input.agentId === "supervisor" ? "supervisor" : "agent",
    stage: input.stage,
    summary: input.rationale,
    title: `Decision de ${input.agentId}`,
  });
}

function retrievalRequestedEvent(
  runId: string,
  sequence: number,
  contextId: string,
): AgentRuntimeEvent {
  const query = memoryQuery(runId);
  return runtimeEvent(runId, {
    agentName: "modeler",
    kind: "memory_retrieval",
    memoryContextId: contextId,
    node: "modeler_memory",
    payload: {
      available: true,
      candidate_pool_size: query.top_k,
      query,
      query_artifact_path: null,
      retrieval_event: "retrieval_requested",
    },
    sequence,
    source: "memory",
    stage: "modeling",
    summary: `Consulta ${query.query_id} registrada.`,
    title: "Consulta RAG para modeler",
  });
}

function retrievalReturnedEvent(
  runId: string,
  sequence: number,
  contextId: string,
  effectiveIds: string[],
  gate: {
    effectiveCount?: number;
    excluded?: Array<{ memory_record_id: string; reason_codes: string[] }>;
    rawCount?: number;
  } = {},
): AgentRuntimeEvent {
  const excluded = gate.excluded ?? [];
  const effectiveCount = gate.effectiveCount ?? effectiveIds.length;
  const rawCount = gate.rawCount ?? effectiveIds.length;
  return runtimeEvent(runId, {
    agentName: "modeler",
    kind: "memory_retrieval",
    memoryContextId: contextId,
    memoryRecordIds: effectiveIds,
    node: "modeler_memory",
    payload: {
      available: true,
      context_artifact_path: null,
      effective_count: effectiveCount,
      embedding_model: "nomic-embed-text:fixture",
      filtered_count: excluded.length,
      items: effectiveIds.map((memoryId, index) => compactMemoryItem(memoryId, index + 1)),
      quality_gate: excluded.length === 0
        ? null
        : {
            caution_count: 0,
            exclude_candidate_count: excluded.length,
            excluded,
            pass_count: effectiveCount,
          },
      quality_gate_artifact_path: null,
      query: memoryQuery(runId),
      query_id: memoryQuery(runId).query_id,
      raw_context_artifact_path: null,
      raw_count: rawCount,
      retrieval_backend: "qdrant",
      retrieval_event: "retrieval_returned",
    },
    sequence,
    source: "memory",
    stage: "modeling",
    summary: `${effectiveCount} recuerdo(s) efectivo(s) de ${rawCount} candidato(s).`,
    title: "Memoria recuperada para modeler",
  });
}

function memoryUsageEvent(
  runId: string,
  sequence: number,
  contextId: string,
  decisionId: string,
  retrievedIds: string[],
  citedIds: string[],
): AgentRuntimeEvent {
  const ignoredIds = retrievedIds.filter((id) => !citedIds.includes(id));
  const used = citedIds.length > 0;
  return runtimeEvent(runId, {
    agentName: "modeler",
    decisionId,
    kind: "memory_retrieval",
    memoryContextId: contextId,
    memoryRecordIds: citedIds,
    node: "modeler_memory",
    payload: {
      cited_memory_record_ids: citedIds,
      ignored_memory_record_ids: ignoredIds,
      memory_context_id: contextId,
      memory_record_uses: used
        ? citedIds.map((id) => ({
            influence_summary: "Antecedente metodologico citado sin atribuirle el resultado.",
            memory_record_id: id,
            risk_mitigation: "La hipotesis continua pendiente de contraste.",
            usage: "adapted",
          }))
        : [],
      memory_usage_summary: used
        ? "El agente declaro y cito el contexto usado."
        : "El agente recibio contexto, pero no declaro uso.",
      retrieval_event: used ? "retrieval_used" : "retrieval_rejected_by_agent",
      retrieved_memory_record_ids: retrievedIds,
      used_memory_context: used,
    },
    sequence,
    source: "memory",
    stage: "modeling",
    summary: used
      ? `${citedIds.length} de ${retrievedIds.length} recuerdos fueron citados.`
      : "El contexto fue recuperado, pero no consta uso efectivo.",
    title: used ? "Memoria usada por modeler" : "Memoria no usada por modeler",
  });
}

function executorEvent(
  runId: string,
  sequence: number,
  agentId: "cleaner" | "structurer" | "modeler" | "report_writer",
  stage: string,
  summary: string,
): AgentRuntimeEvent {
  const decisionId = `${runId}:${agentId}:001`;
  return runtimeEvent(runId, {
    decisionId,
    kind: "executor_result",
    nextNode: null,
    nextStage: stage === "reporting" ? "completed" : null,
    node: `${agentId}_executor`,
    payload: {
      artifact_names: [],
      artifact_types: [],
      errors: [],
      source_decision_id: decisionId,
      state_updates: {},
      status: "success",
    },
    sequence,
    source: "executor",
    stage,
    summary,
    title: `Ejecutor ${agentId}`,
  });
}

function jobEvent(
  runId: string,
  sequence: number,
  status: "running" | "completed",
  summary: string,
): AgentRuntimeEvent {
  return runtimeEvent(runId, {
    kind: "job_status",
    node: "run_job",
    payload: { status },
    sequence,
    source: "job",
    stage: status === "completed" ? "completed" : "profiling",
    summary,
    title: status === "completed" ? "Run completada" : "Run iniciada",
  });
}

function runtimeEvent(runId: string, input: RuntimeEventInput): AgentRuntimeEvent {
  return {
    agent_name: input.agentName ?? null,
    confidence: input.confidence ?? null,
    created_at: eventTime(input.sequence),
    decision_id: input.decisionId ?? null,
    event_id: `${runId}:runtime:${String(input.sequence).padStart(4, "0")}`,
    kind: input.kind,
    memory_context_id: input.memoryContextId ?? null,
    memory_record_ids: input.memoryRecordIds ?? [],
    next_node: input.nextNode ?? null,
    next_stage: input.nextStage ?? null,
    node: input.node ?? null,
    payload: {
      ...input.payload,
      trace_origin: "persisted_runtime",
    },
    rationale: input.rationale ?? null,
    run_id: runId,
    sequence: input.sequence,
    source: input.source,
    stage: input.stage ?? null,
    summary: input.summary,
    title: input.title,
  };
}

function scenario(
  id: AgentRunScenarioId,
  runId: string,
  events: AgentRuntimeEvent[],
  expected: AgentRunScenarioExpectation,
  approved: boolean | null = null,
): AgentRunScenario {
  const createdAt = eventTime(events.length + 1);
  const snapshot: RunSnapshot = {
    approved,
    artifacts_path: `/fixtures/${runId}/artifacts.json`,
    audit_report_path: null,
    created_at: createdAt,
    current_stage: "completed",
    dataset: FIXTURE_DATASET,
    decisions_path: `/fixtures/${runId}/decisions.json`,
    evidence_pack_markdown_path: null,
    evidence_pack_path: null,
    evaluation_path: `/fixtures/${runId}/evaluation.json`,
    metadata_path: `/fixtures/${runId}/snapshot.json`,
    metrics_path: `/fixtures/${runId}/metrics.json`,
    n_artifacts: 0,
    n_decisions: expected.decisionCount,
    n_errors: 0,
    report_path: null,
    run_id: runId,
    runtime_events_path: `/fixtures/${runId}/runtime_events.json`,
    snapshot_dir: `/fixtures/${runId}`,
    state_path: `/fixtures/${runId}/state_final.json`,
    summary_path: `/fixtures/${runId}/summary.md`,
    thread_id: `${runId}:thread`,
  };
  const run: RunIndexEntry = {
    approved,
    created_at: createdAt,
    current_stage: "completed",
    dataset: FIXTURE_DATASET,
    f1_score: null,
    false_positive_rate: null,
    n_artifacts: 0,
    n_decisions: expected.decisionCount,
    n_errors: 0,
    precision: null,
    recall: null,
    report_path: null,
    run_id: runId,
    snapshot_path: `/fixtures/${runId}/snapshot.json`,
    thread_id: `${runId}:thread`,
  };
  return { events, expected, id, run, snapshot };
}

function memoryQuery(runId: string) {
  return {
    allowed_memory_roles: [
      "positive_example",
      "negative_example",
      "boundary_case",
      "warning",
      "methodology",
      "evidence",
    ],
    created_at: eventTime(1),
    data_provenance: "official",
    dataset: FIXTURE_DATASET,
    decision_context: { task: "model_selection" },
    decision_id: `${runId}:modeler:001`,
    excluded_verdicts: ["unsafe"],
    human_review_mode: "off",
    min_similarity: 0.2,
    query_id: `${runId}:modeler:query`,
    query_text: "Seleccion de modelo para degradacion temporal de rodamientos.",
    run_id: runId,
    target_agent: "modeler",
    top_k: 3,
  } as const;
}

function compactMemoryItem(memoryRecordId: string, rank: number) {
  return {
    collection_name: "modeler_memory",
    dataset: FIXTURE_DATASET,
    embedding_dimension: 768,
    embedding_model: "nomic-embed-text:fixture",
    human_verdict: "correct",
    memory_record_id: memoryRecordId,
    memory_role: memoryRecordId === "mem-filtered" ? "boundary_case" : "positive_example",
    outcome: "validated",
    rank,
    retrieval_use: memoryRecordId === "mem-filtered" ? "boundary_context" : "positive_context",
    run_id: `historical-${memoryRecordId}`,
    similarity: 0.84 - (rank - 1) * 0.05,
    source_path: null,
    source_type: "decision_episode",
    summary: `Recuerdo controlado ${memoryRecordId}.`,
    tags: ["e2e", "controlled-fixture"],
    target_agent: "modeler",
    vector_id: `vector-${memoryRecordId}`,
  };
}

function eventTime(sequence: number): string {
  return new Date(Date.parse(FIXTURE_STARTED_AT) + sequence * 1_000).toISOString();
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}
