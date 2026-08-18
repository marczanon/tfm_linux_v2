"""Harness ligero para medir fiabilidad LLM sin ejecutar datasets.

La frontera de este modulo es deliberadamente estrecha: materializa estados
Pydantic pequenos, invoca los mismos agentes de produccion y clasifica su
salida. No compila LangGraph, no llama ejecutores, no recupera memoria y no
convierte una decision determinista de fallback en evidencia agentica.

``experiment_protocol.py`` conserva la puerta metodologica pre-Qwen. Este
servicio produce la evidencia concreta que esa puerta puede consumir sin
sobrecargar ``pipeline_runner.py`` o registrar falsos snapshots de pipeline.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from codigo.app.agents.modeler import decide_modeling_retry_action
from codigo.app.agents.report_verifier import decide_report_verification_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import (
    AgentDecisionBase,
    AgentHypothesis,
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.state import (
    ArtifactRef,
    CleaningConfig,
    DatasetProfileSummary,
    EvaluationResult,
    MetricsReport,
    ModelingConfig,
    ProjectContext,
    StructuringConfig,
    TFMStateModel,
)
from codigo.app.services.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_NUM_CTX,
    DEFAULT_OLLAMA_NUM_PREDICT,
    JSONLLMClient,
    LLMMessage,
    OllamaJSONClient,
)
from codigo.app.services.llm_agents import build_ollama_pipeline_agents


DEFAULT_AGENT_RELIABILITY_OUTPUT_DIR = Path(
    "codigo/reports/validation/agent_reliability"
)
AGENT_RELIABILITY_PROTOCOL_ID = "agent_decision_reliability_v1"

AgentReliabilityEntrypoint = Literal[
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "modeler_retry",
    "evaluator",
    "report_writer",
    "report_reviser",
    "report_verifier",
]
AgentReliabilityStateProfile = Literal[
    "cwru_initial",
    "cwru_evaluation_route",
    "cwru_cleaning",
    "nasa_cleaning",
    "cwru_structuring",
    "nasa_structuring",
    "cwru_modeling",
    "nasa_online_blind_modeling",
    "cwru_modeling_retry",
    "cwru_evaluation",
    "nasa_evaluation",
    "nasa_reporting",
    "cwru_report_safe",
    "cwru_report_unsafe",
    "cwru_report_revision",
]
AgentReliabilityOutcome = Literal[
    "first_pass",
    "llm_repaired",
    "fallback",
    "non_agentic",
    "semantic_failure",
    "error",
]
AttemptKind = Literal["initial", "json_repair", "logical_complete_json"]
AttemptStatus = Literal["success", "error"]
TransportTraceScope = Literal[
    "physical_ollama_chat",
    "logical_complete_json_only",
]


class AgentReliabilityScenario(StrictBaseModel):
    """Caso pequeno y cerrado para una unica decision agentica."""

    scenario_id: str = Field(min_length=1)
    entrypoint: AgentReliabilityEntrypoint
    state_profile: AgentReliabilityStateProfile
    dataset: Literal["cwru_bearing", "nasa_ims_bearing"]
    description: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    expected_next_stage: str | None = Field(default=None, min_length=1)
    expected_next_node: str | None = Field(default=None, min_length=1)
    expected_approved: bool | None = None
    expected_verification_status: str | None = Field(default=None, min_length=1)


class AgentReliabilityAcceptancePolicy(StrictBaseModel):
    """Gate inicial; una reparacion LLM sigue siendo exito agentico."""

    minimum_repetitions: int = Field(default=3, ge=1)
    minimum_first_pass_rate: float = Field(default=0.90, ge=0.0, le=1.0)
    require_complete_trace: bool = True
    require_zero_fallbacks: bool = True
    require_zero_non_agentic: bool = True
    require_zero_semantic_failures: bool = True
    require_zero_errors: bool = True


class AgentReliabilityPlan(StrictBaseModel):
    """Plan reproducible que nunca incluye ejecutores o memoria."""

    schema_version: Literal["agent_reliability_plan_v1"] = (
        "agent_reliability_plan_v1"
    )
    protocol_id: Literal["agent_decision_reliability_v1"] = (
        AGENT_RELIABILITY_PROTOCOL_ID
    )
    plan_id: str = Field(default="agent-reliability-qwen35-v1", min_length=1)
    repetitions: int = Field(default=3, ge=1)
    memory_enabled: Literal[False] = False
    pipeline_executed: Literal[False] = False
    scenarios: list[AgentReliabilityScenario] = Field(min_length=1)
    acceptance: AgentReliabilityAcceptancePolicy = Field(
        default_factory=AgentReliabilityAcceptancePolicy
    )

    @model_validator(mode="after")
    def validate_scenario_identity(self) -> "AgentReliabilityPlan":
        scenario_ids = [item.scenario_id for item in self.scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("agent reliability scenario_id values must be unique")
        return self


class AgentReliabilityModelConfig(StrictBaseModel):
    """Configuracion LLM auditable, sin persistir host ni credenciales."""

    provider: str = Field(default="ollama", min_length=1)
    model: str = Field(default=DEFAULT_OLLAMA_CHAT_MODEL, min_length=1)
    think: bool | None = False
    timeout_seconds: float = Field(default=120.0, gt=0.0)
    temperature: float = 0.0
    num_ctx: int = Field(default=DEFAULT_OLLAMA_NUM_CTX, gt=0)
    num_predict: int = Field(default=DEFAULT_OLLAMA_NUM_PREDICT, gt=0)
    max_json_repair_attempts: int = Field(default=1, ge=0)
    transport_trace_scope: TransportTraceScope = "physical_ollama_chat"


class AgentReliabilityAttempt(StrictBaseModel):
    """Llamada observada sin guardar el prompt en claro.

    La respuesta estructurada solo se conserva en intentos logicos. Esto hace
    auditables las propuestas rechazadas sin duplicar el sobre HTTP de Ollama.
    """

    attempt_index: int = Field(ge=1)
    kind: AttemptKind
    status: AttemptStatus
    message_count: int = Field(ge=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_payload: dict[str, Any] | None = None
    elapsed_ms: float = Field(ge=0.0)
    prompt_eval_count: int | None = Field(default=None, ge=0)
    eval_count: int | None = Field(default=None, ge=0)
    provider_duration_ns: int | None = Field(default=None, ge=0)
    done_reason: str | None = Field(default=None, min_length=1)
    error_type: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)


class AgentReliabilityInvariant(StrictBaseModel):
    """Resultado de un oraculo semantico cerrado."""

    invariant_id: str = Field(min_length=1)
    passed: bool
    detail: str = Field(min_length=1)


class AgentReliabilityObservation(StrictBaseModel):
    """Resultado completo de una decision dentro de una repeticion."""

    observation_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    entrypoint: AgentReliabilityEntrypoint
    dataset: str = Field(min_length=1)
    repetition: int = Field(ge=1)
    outcome: AgentReliabilityOutcome
    elapsed_ms: float = Field(ge=0.0)
    decision_id: str | None = Field(default=None, min_length=1)
    generation_origin: str | None = Field(default=None, min_length=1)
    generation_validation_status: str | None = Field(default=None, min_length=1)
    generation_attempt_index: int | None = Field(default=None, ge=1)
    fallback_cause: str | None = Field(default=None, min_length=1)
    trace_available: bool = False
    invariants: list[AgentReliabilityInvariant] = Field(default_factory=list)
    logical_attempts: list[AgentReliabilityAttempt] = Field(default_factory=list)
    physical_attempts: list[AgentReliabilityAttempt] = Field(default_factory=list)
    decision_payload: dict[str, Any] | None = None
    error_type: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)


class AgentReliabilityEntrypointSummary(StrictBaseModel):
    """Agregado de resultados para un callable concreto."""

    entrypoint: AgentReliabilityEntrypoint
    observation_count: int = Field(ge=0)
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    semantic_failure_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    agentic_success_rate: float = Field(ge=0.0, le=1.0)
    first_pass_rate: float = Field(ge=0.0, le=1.0)
    p50_elapsed_ms: float | None = Field(default=None, ge=0.0)
    p95_elapsed_ms: float | None = Field(default=None, ge=0.0)


class AgentReliabilitySummary(StrictBaseModel):
    """Resumen global y por entrypoint del pack decision-only."""

    observation_count: int = Field(ge=0)
    repetition_count: int = Field(ge=0)
    scenario_count: int = Field(ge=0)
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    semantic_failure_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    trace_coverage_rate: float = Field(ge=0.0, le=1.0)
    agentic_success_rate: float = Field(ge=0.0, le=1.0)
    first_pass_rate: float = Field(ge=0.0, le=1.0)
    flow_success_count: int = Field(ge=0)
    flow_success_rate: float = Field(ge=0.0, le=1.0)
    logical_call_count: int = Field(ge=0)
    physical_call_count: int = Field(ge=0)
    entrypoints: list[AgentReliabilityEntrypointSummary] = Field(
        default_factory=list
    )


class AgentReliabilityGate(StrictBaseModel):
    """Dictamen bloqueante anterior a una validacion pesada."""

    verdict: Literal["passed", "blocked"]
    blockers: list[str] = Field(default_factory=list)
    detail: str = Field(min_length=1)


class AgentReliabilityManifest(StrictBaseModel):
    """Identidad reproducible de modelo, prompts, esquemas y escenarios."""

    schema_version: Literal["agent_reliability_manifest_v1"] = (
        "agent_reliability_manifest_v1"
    )
    protocol_id: Literal["agent_decision_reliability_v1"] = (
        AGENT_RELIABILITY_PROTOCOL_ID
    )
    plan_id: str = Field(min_length=1)
    scenario_pack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    llm_config: AgentReliabilityModelConfig
    memory_enabled: Literal[False] = False
    pipeline_executed: Literal[False] = False
    prompt_sha256s: list[str] = Field(default_factory=list)
    schema_sha256s: list[str] = Field(default_factory=list)
    source_sha256s: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime
    trace_limitation: str = Field(min_length=1)


class AgentReliabilityResult(StrictBaseModel):
    """Resultado autocontenido de la bateria decision-only."""

    manifest: AgentReliabilityManifest
    plan: AgentReliabilityPlan
    observations: list[AgentReliabilityObservation]
    summary: AgentReliabilitySummary
    gate: AgentReliabilityGate


class AgentReliabilityArtifacts(StrictBaseModel):
    """Rutas persistidas del harness, separadas de los snapshots de runs."""

    output_dir: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    observations_path: str = Field(min_length=1)
    summary_path: str = Field(min_length=1)
    report_path: str = Field(min_length=1)


class AgentReliabilityClientFactory(Protocol):
    """Crea un cliente aislado por observacion."""

    def __call__(
        self,
        scenario: AgentReliabilityScenario,
        state: TFMStateModel,
        physical_attempts: list[AgentReliabilityAttempt],
    ) -> JSONLLMClient:
        """Devuelve un cliente que no comparte conversacion entre escenarios."""


class _LogicalCallRecordingClient:
    """Observa ``complete_json`` sin alterar el contrato de los agentes."""

    def __init__(
        self,
        inner: JSONLLMClient,
        attempts: list[AgentReliabilityAttempt],
    ) -> None:
        self._inner = inner
        self._attempts = attempts

    def complete_json(
        self,
        messages: Sequence[LLMMessage],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempt_index = len(self._attempts) + 1
        started = time.perf_counter()
        try:
            payload = self._inner.complete_json(messages, json_schema=json_schema)
        except Exception as exc:
            self._attempts.append(
                _attempt_from_error(
                    attempt_index=attempt_index,
                    kind="logical_complete_json",
                    messages=messages,
                    json_schema=json_schema,
                    elapsed_ms=_elapsed_ms(started),
                    exc=exc,
                )
            )
            raise
        self._attempts.append(
            AgentReliabilityAttempt(
                attempt_index=attempt_index,
                kind="logical_complete_json",
                status="success",
                message_count=len(messages),
                prompt_sha256=_messages_sha256(messages),
                schema_sha256=_json_sha256(json_schema),
                response_sha256=_json_sha256(payload),
                response_payload=payload,
                elapsed_ms=_elapsed_ms(started),
            )
        )
        return payload


class ObservedOllamaJSONClient(OllamaJSONClient):
    """Subclase local que hace visible cada ``/api/chat`` fisico.

    Se mantiene fuera de ``llm.py`` para no cambiar el cliente productivo en
    este hito. El CLI usa esta clase; clientes inyectados de terceros solo
    pueden ofrecer telemetria logica y se declaran como tal en el manifiesto.
    """

    def __init__(
        self,
        *,
        physical_attempts: list[AgentReliabilityAttempt],
        model: str,
        host: str = DEFAULT_OLLAMA_HOST,
        timeout_seconds: float = 120.0,
        think: bool | None = False,
        max_json_repair_attempts: int = 1,
        num_ctx: int = DEFAULT_OLLAMA_NUM_CTX,
        num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT,
    ) -> None:
        super().__init__(
            model=model,
            host=host,
            timeout_seconds=timeout_seconds,
            think=think,
            max_json_repair_attempts=max_json_repair_attempts,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
        object.__setattr__(self, "_reliability_physical_attempts", physical_attempts)

    def _chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        attempts: list[AgentReliabilityAttempt] = getattr(
            self,
            "_reliability_physical_attempts",
        )
        attempt_index = len(attempts) + 1
        kind: AttemptKind = (
            "json_repair" if _is_json_repair_call(messages) else "initial"
        )
        started = time.perf_counter()
        try:
            payload = super()._chat(messages, json_schema=json_schema)
        except Exception as exc:
            attempts.append(
                _attempt_from_error(
                    attempt_index=attempt_index,
                    kind=kind,
                    messages=messages,
                    json_schema=json_schema,
                    elapsed_ms=_elapsed_ms(started),
                    exc=exc,
                )
            )
            raise
        attempts.append(
            AgentReliabilityAttempt(
                attempt_index=attempt_index,
                kind=kind,
                status="success",
                message_count=len(messages),
                prompt_sha256=_messages_sha256(messages),
                schema_sha256=_json_sha256(json_schema),
                response_sha256=_json_sha256(payload),
                elapsed_ms=_elapsed_ms(started),
                prompt_eval_count=_optional_non_negative_int(
                    payload.get("prompt_eval_count")
                ),
                eval_count=_optional_non_negative_int(payload.get("eval_count")),
                provider_duration_ns=_optional_non_negative_int(
                    payload.get("total_duration")
                ),
                done_reason=_optional_non_empty_string(payload.get("done_reason")),
            )
        )
        return payload


def default_agent_reliability_plan(
    *,
    plan_id: str = "agent-reliability-qwen35-v1",
    repetitions: int = 3,
    minimum_first_pass_rate: float = 0.90,
) -> AgentReliabilityPlan:
    """Devuelve el pack v1 con todos los callables agenticos."""

    scenarios = [
        AgentReliabilityScenario(
            scenario_id="supervisor_cwru_initial",
            entrypoint="supervisor",
            state_profile="cwru_initial",
            dataset="cwru_bearing",
            description="Enruta el estado inicial al generador de manifiesto.",
            tags=["flow", "cwru", "initial"],
            expected_next_stage="dataset_manifest",
            expected_next_node="manifest_executor",
        ),
        AgentReliabilityScenario(
            scenario_id="supervisor_cwru_evaluation",
            entrypoint="supervisor",
            state_profile="cwru_evaluation_route",
            dataset="cwru_bearing",
            description="Enruta predicciones disponibles hacia el evaluador.",
            tags=["flow", "cwru", "evaluation"],
            expected_next_stage="evaluation",
            expected_next_node="evaluator",
        ),
        AgentReliabilityScenario(
            scenario_id="cleaner_cwru",
            entrypoint="cleaner",
            state_profile="cwru_cleaning",
            dataset="cwru_bearing",
            description="Limpieza CWRU a 12 kHz sobre DE_time.",
            tags=["cleaning", "cwru"],
        ),
        AgentReliabilityScenario(
            scenario_id="cleaner_nasa",
            entrypoint="cleaner",
            state_profile="nasa_cleaning",
            dataset="nasa_ims_bearing",
            description="Limpieza NASA IMS a 20 kHz sin inferir fallo.",
            tags=["cleaning", "nasa", "run_to_failure"],
        ),
        AgentReliabilityScenario(
            scenario_id="structurer_cwru",
            entrypoint="structurer",
            state_profile="cwru_structuring",
            dataset="cwru_bearing",
            description="Ventanas y features para el contraste CWRU.",
            tags=["structuring", "cwru"],
        ),
        AgentReliabilityScenario(
            scenario_id="structurer_nasa",
            entrypoint="structurer",
            state_profile="nasa_structuring",
            dataset="nasa_ims_bearing",
            description="Estructuracion temporal NASA IMS sin memoria.",
            tags=["structuring", "nasa", "run_to_failure"],
        ),
        AgentReliabilityScenario(
            scenario_id="modeler_cwru",
            entrypoint="modeler",
            state_profile="cwru_modeling",
            dataset="cwru_bearing",
            description="Seleccion de familia de modelo soportada para CWRU.",
            tags=["modeling", "cwru"],
        ),
        AgentReliabilityScenario(
            scenario_id="modeler_nasa_online_blind",
            entrypoint="modeler",
            state_profile="nasa_online_blind_modeling",
            dataset="nasa_ims_bearing",
            description="Decision NASA oficial sin evidencia futura ni etiquetas.",
            tags=["modeling", "nasa", "online_blind"],
        ),
        AgentReliabilityScenario(
            scenario_id="modeler_retry_cwru",
            entrypoint="modeler_retry",
            state_profile="cwru_modeling_retry",
            dataset="cwru_bearing",
            description="Analiza un intento fallido y decide reintento o parada.",
            tags=["modeling", "retry", "cwru"],
        ),
        AgentReliabilityScenario(
            scenario_id="evaluator_cwru_approved",
            entrypoint="evaluator",
            state_profile="cwru_evaluation",
            dataset="cwru_bearing",
            description="Interpreta metricas binarias que superan los umbrales.",
            tags=["evaluation", "cwru"],
            expected_approved=True,
        ),
        AgentReliabilityScenario(
            scenario_id="evaluator_nasa_temporal",
            entrypoint="evaluator",
            state_profile="nasa_evaluation",
            dataset="nasa_ims_bearing",
            description="Interpreta controles temporales oficiales causal-v2.",
            tags=["evaluation", "nasa", "online_blind"],
            expected_approved=True,
        ),
        AgentReliabilityScenario(
            scenario_id="report_writer_nasa",
            entrypoint="report_writer",
            state_profile="nasa_reporting",
            dataset="nasa_ims_bearing",
            description="Redacta un informe NASA con limitaciones fisicas explicitas.",
            tags=["report", "nasa"],
        ),
        AgentReliabilityScenario(
            scenario_id="report_verifier_safe",
            entrypoint="report_verifier",
            state_profile="cwru_report_safe",
            dataset="cwru_bearing",
            description="Aprueba un informe local prudente y trazable.",
            tags=["report", "verification", "safe"],
            expected_verification_status="approved",
        ),
        AgentReliabilityScenario(
            scenario_id="report_verifier_unsafe",
            entrypoint="report_verifier",
            state_profile="cwru_report_unsafe",
            dataset="cwru_bearing",
            description="Detecta afirmaciones industriales no soportadas.",
            tags=["report", "verification", "guardrail"],
            expected_verification_status="blocked",
        ),
        AgentReliabilityScenario(
            scenario_id="report_reviser_cwru",
            entrypoint="report_reviser",
            state_profile="cwru_report_revision",
            dataset="cwru_bearing",
            description="Corrige una afirmacion rechazada por el verificador.",
            tags=["report", "revision", "cwru"],
        ),
    ]
    return AgentReliabilityPlan(
        plan_id=plan_id,
        repetitions=repetitions,
        scenarios=scenarios,
        acceptance=AgentReliabilityAcceptancePolicy(
            minimum_first_pass_rate=minimum_first_pass_rate,
        ),
    )


def run_agent_reliability_plan(
    plan: AgentReliabilityPlan,
    *,
    client_factory: AgentReliabilityClientFactory,
    model_config: AgentReliabilityModelConfig,
) -> AgentReliabilityResult:
    """Ejecuta solo decisiones LLM sobre estados pequenos y congelados."""

    started_at = datetime.now(UTC)
    observations: list[AgentReliabilityObservation] = []
    for repetition in range(1, plan.repetitions + 1):
        for scenario in plan.scenarios:
            observation_id = (
                f"{plan.plan_id}:{scenario.scenario_id}:rep:{repetition:03d}"
            )
            state = materialize_agent_reliability_state(
                scenario,
                run_id=_plain_observation_run_id(observation_id),
            )
            logical_attempts: list[AgentReliabilityAttempt] = []
            physical_attempts: list[AgentReliabilityAttempt] = []
            base_client = client_factory(scenario, state, physical_attempts)
            client = _LogicalCallRecordingClient(base_client, logical_attempts)
            decision_started = time.perf_counter()
            try:
                decision = _invoke_scenario(scenario, state, client)
            except Exception as exc:
                observations.append(
                    AgentReliabilityObservation(
                        observation_id=observation_id,
                        scenario_id=scenario.scenario_id,
                        entrypoint=scenario.entrypoint,
                        dataset=scenario.dataset,
                        repetition=repetition,
                        outcome="error",
                        elapsed_ms=_elapsed_ms(decision_started),
                        logical_attempts=logical_attempts,
                        physical_attempts=physical_attempts,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                continue
            observations.append(
                _observation_from_decision(
                    observation_id=observation_id,
                    scenario=scenario,
                    repetition=repetition,
                    state=state,
                    decision=decision,
                    elapsed_ms=_elapsed_ms(decision_started),
                    logical_attempts=logical_attempts,
                    physical_attempts=physical_attempts,
                )
            )

    summary = summarize_agent_reliability(plan, observations)
    gate = assess_agent_reliability_gate(plan, summary)
    prompt_hashes = sorted(
        {
            attempt.prompt_sha256
            for item in observations
            for attempt in [*item.logical_attempts, *item.physical_attempts]
        }
    )
    schema_hashes = sorted(
        {
            attempt.schema_sha256
            for item in observations
            for attempt in [*item.logical_attempts, *item.physical_attempts]
            if attempt.schema_sha256 is not None
        }
    )
    manifest = AgentReliabilityManifest(
        plan_id=plan.plan_id,
        scenario_pack_sha256=_scenario_pack_sha256(plan.scenarios),
        llm_config=model_config,
        prompt_sha256s=prompt_hashes,
        schema_sha256s=schema_hashes,
        source_sha256s=_reliability_source_sha256s(),
        started_at=started_at,
        completed_at=datetime.now(UTC),
        trace_limitation=(
            "physical_ollama_chat distingue la reparacion JSON interna solo "
            "cuando se usa ObservedOllamaJSONClient. Con clientes inyectados "
            "genericos, first_pass significa primera llamada logica a "
            "complete_json y no garantiza una unica llamada fisica al proveedor."
        ),
    )
    return AgentReliabilityResult(
        manifest=manifest,
        plan=plan,
        observations=observations,
        summary=summary,
        gate=gate,
    )


def materialize_agent_reliability_state(
    scenario: AgentReliabilityScenario,
    *,
    run_id: str,
) -> TFMStateModel:
    """Construye un estado tipado; nunca carga ni transforma un dataset."""

    state = validate_state(
        create_initial_cwru_state(
            thread_id=f"{run_id}-thread",
            run_id=run_id,
            raw_path="codigo/data/raw/cwru_bearing/reliability_fixture",
        )
    )
    payload = state.model_dump(mode="json")
    profile = scenario.state_profile
    if profile.startswith("nasa_"):
        payload["raw_path"] = "codigo/data/raw/nasa_ims_bearing/reliability_fixture"
        payload["project_context"] = _nasa_online_blind_context().model_dump(
            mode="json"
        )

    if profile == "cwru_initial":
        return validate_state(payload)
    if profile == "cwru_evaluation_route":
        payload.update(
            current_stage="evaluation",
            next_node="supervisor",
            artifacts=[
                ArtifactRef(
                    name="predictions",
                    artifact_type="predictions",
                    path="codigo/experiments/agent_reliability/predictions.csv",
                    producer="modeling_executor",
                ).model_dump(mode="json")
            ],
        )
        return validate_state(payload)
    if profile in {"cwru_cleaning", "nasa_cleaning"}:
        payload.update(
            current_stage="cleaning",
            next_node="cleaner_agent",
            manifest_path="codigo/experiments/agent_reliability/manifest.csv",
            profile_path="codigo/experiments/agent_reliability/profile.json",
        )
        return validate_state(payload)
    if profile in {"cwru_structuring", "nasa_structuring"}:
        context = ProjectContext.model_validate(payload["project_context"])
        payload.update(
            current_stage="structuring",
            next_node="structuring_agent",
            clean_path="codigo/experiments/agent_reliability/clean_signals",
            cleaning_config=CleaningConfig(
                strategy_id=f"{context.dataset}_fixture_clean_v1",
                remove_non_finite=True,
                resample_to_hz=context.target_sample_rate_hz,
                normalization="none",
                selected_channel=context.main_channel,
            ).model_dump(mode="json"),
        )
        return validate_state(payload)
    if profile in {
        "cwru_modeling",
        "nasa_online_blind_modeling",
        "cwru_modeling_retry",
    }:
        context = ProjectContext.model_validate(payload["project_context"])
        payload.update(
            current_stage="modeling",
            next_node="modeling_agent",
            tensor_path="codigo/experiments/agent_reliability/windows_raw.npz",
            splits_path="codigo/experiments/agent_reliability/splits.json",
            structuring_config=StructuringConfig(
                window_size=2048,
                overlap=0.5,
                main_channel=context.main_channel,
                target_sample_rate_hz=context.target_sample_rate_hz,
                label_mode=context.label_mode,
            ).model_dump(mode="json"),
            artifacts=[
                ArtifactRef(
                    name="windows_features",
                    artifact_type="features",
                    path="codigo/experiments/agent_reliability/windows_features.csv",
                    producer="structuring_executor",
                ).model_dump(mode="json")
            ],
        )
        if profile == "nasa_online_blind_modeling":
            payload["dataset_profile"] = DatasetProfileSummary(
                dataset_name="NASA IMS Set 2 online-blind fixture",
                n_files=984,
                n_samples_total=20_152_320,
                channels=["channel_1", "channel_2", "channel_3", "channel_4"],
                sample_rates_hz=[20_000],
                label_counts={},
                summary={"evidence_view": "online_blind_baseline_profile"},
            ).model_dump(mode="json")
        if profile == "cwru_modeling_retry":
            payload["modeling_config"] = ModelingConfig(
                model_name="isolation_forest",
                random_state=42,
                hyperparameters={"threshold_quantile": 0.99},
            ).model_dump(mode="json")
        return validate_state(payload)
    if profile in {"cwru_evaluation", "nasa_evaluation"}:
        payload.update(
            current_stage="evaluation",
            next_node="evaluation_agent",
            metrics=(
                _nasa_metrics().model_dump(mode="json")
                if profile == "nasa_evaluation"
                else MetricsReport(
                    precision=0.94,
                    recall=0.95,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ).model_dump(mode="json")
            ),
            artifacts=[
                ArtifactRef(
                    name="predictions",
                    artifact_type="predictions",
                    path="codigo/experiments/agent_reliability/predictions.csv",
                    producer="modeling_executor",
                ).model_dump(mode="json")
            ],
        )
        return validate_state(payload)
    if profile in {
        "nasa_reporting",
        "cwru_report_safe",
        "cwru_report_unsafe",
        "cwru_report_revision",
    }:
        if profile != "nasa_reporting":
            payload["project_context"] = ProjectContext(
                dataset="cwru_bearing",
                data_provenance="official",
                provenance_detection_method="trusted_adapter",
            ).model_dump(mode="json")
        payload.update(
            current_stage="reporting",
            next_node="report_writer",
            report_path=(
                f"codigo/reports/{ProjectContext.model_validate(payload['project_context']).dataset}/"
                f"{run_id}/final_report.md"
            ),
            metrics=(
                _nasa_metrics().model_dump(mode="json")
                if profile == "nasa_reporting"
                else MetricsReport(
                    precision=0.94,
                    recall=0.95,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ).model_dump(mode="json")
            ),
            evaluation=EvaluationResult(
                approved=True,
                summary=(
                    "Aceptada por controles operativos internos; no valida fallo fisico."
                    if profile == "nasa_reporting"
                    else "Ejecucion local CWRU aprobada."
                ),
                next_action="continue",
                limitations=[
                    "No hay ground truth fisico por snapshot."
                    if profile == "nasa_reporting"
                    else "Validacion limitada al benchmark local CWRU."
                ],
            ).model_dump(mode="json"),
            artifacts=[
                ArtifactRef(
                    name="metrics",
                    artifact_type="metrics",
                    path="codigo/experiments/agent_reliability/metrics.json",
                    producer="evaluator",
                ).model_dump(mode="json")
            ],
        )
        return validate_state(payload)
    raise ValueError(f"unsupported reliability state profile: {profile}")


def summarize_agent_reliability(
    plan: AgentReliabilityPlan,
    observations: Sequence[AgentReliabilityObservation],
) -> AgentReliabilitySummary:
    """Agrega resultados sin convertir reparaciones en first-pass."""

    entrypoints = sorted({item.entrypoint for item in plan.scenarios})
    role_summaries = [
        _entrypoint_summary(
            entrypoint,
            [item for item in observations if item.entrypoint == entrypoint],
        )
        for entrypoint in entrypoints
    ]
    observation_count = len(observations)
    success_outcomes = {"first_pass", "llm_repaired"}
    first_pass_count = _count_outcome(observations, "first_pass")
    repaired_count = _count_outcome(observations, "llm_repaired")
    trace_count = sum(item.trace_available for item in observations)
    successful_repetitions = 0
    for repetition in range(1, plan.repetitions + 1):
        items = [item for item in observations if item.repetition == repetition]
        if len(items) == len(plan.scenarios) and all(
            item.outcome in success_outcomes for item in items
        ):
            successful_repetitions += 1
    return AgentReliabilitySummary(
        observation_count=observation_count,
        repetition_count=plan.repetitions,
        scenario_count=len(plan.scenarios),
        first_pass_count=first_pass_count,
        repaired_count=repaired_count,
        fallback_count=_count_outcome(observations, "fallback"),
        non_agentic_count=_count_outcome(observations, "non_agentic"),
        semantic_failure_count=_count_outcome(observations, "semantic_failure"),
        error_count=_count_outcome(observations, "error"),
        trace_coverage_rate=_safe_rate(trace_count, observation_count),
        agentic_success_rate=_safe_rate(
            first_pass_count + repaired_count,
            observation_count,
        ),
        first_pass_rate=_safe_rate(first_pass_count, observation_count),
        flow_success_count=successful_repetitions,
        flow_success_rate=_safe_rate(successful_repetitions, plan.repetitions),
        logical_call_count=sum(len(item.logical_attempts) for item in observations),
        physical_call_count=sum(len(item.physical_attempts) for item in observations),
        entrypoints=role_summaries,
    )


def assess_agent_reliability_gate(
    plan: AgentReliabilityPlan,
    summary: AgentReliabilitySummary,
) -> AgentReliabilityGate:
    """Bloquea cualquier fallback, ruta no agentica o fallo semantico."""

    policy = plan.acceptance
    blockers: list[str] = []
    if plan.repetitions < policy.minimum_repetitions:
        blockers.append(
            f"insufficient_repetitions:{plan.repetitions}<{policy.minimum_repetitions}"
        )
    if policy.require_zero_fallbacks and summary.fallback_count:
        blockers.append(f"fallback_count:{summary.fallback_count}")
    if policy.require_zero_non_agentic and summary.non_agentic_count:
        blockers.append(f"non_agentic_count:{summary.non_agentic_count}")
    if policy.require_zero_semantic_failures and summary.semantic_failure_count:
        blockers.append(f"semantic_failure_count:{summary.semantic_failure_count}")
    if policy.require_zero_errors and summary.error_count:
        blockers.append(f"error_count:{summary.error_count}")
    if policy.require_complete_trace and summary.trace_coverage_rate < 1.0:
        blockers.append(
            f"trace_coverage_rate:{summary.trace_coverage_rate:.6f}<1.000000"
        )
    if summary.agentic_success_rate < 1.0:
        blockers.append(
            f"agentic_success_rate:{summary.agentic_success_rate:.6f}<1.000000"
        )
    if summary.first_pass_rate < policy.minimum_first_pass_rate:
        blockers.append(
            "first_pass_rate:"
            f"{summary.first_pass_rate:.6f}<{policy.minimum_first_pass_rate:.6f}"
        )
    if blockers:
        return AgentReliabilityGate(
            verdict="blocked",
            blockers=blockers,
            detail=(
                "La base agentica no supera el gate decision-only; no se debe "
                "usar esta bateria como autorizacion para una validacion pesada."
            ),
        )
    return AgentReliabilityGate(
        verdict="passed",
        blockers=[],
        detail=(
            "Todas las decisiones permanecieron en LLM, incluidas las "
            "reparaciones controladas, sin fallback ni fallo semantico."
        ),
    )


def write_agent_reliability_artifacts(
    result: AgentReliabilityResult,
    *,
    output_root: Path | str = DEFAULT_AGENT_RELIABILITY_OUTPUT_DIR,
) -> AgentReliabilityArtifacts:
    """Persiste evidencia propia sin crear un snapshot de pipeline ficticio."""

    _ensure_plain_name(result.plan.plan_id)
    destination = Path(output_root) / result.plan.plan_id
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "manifest.json"
    observations_path = destination / "observations.jsonl"
    summary_path = destination / "summary.json"
    report_path = destination / "report.md"
    _write_json(manifest_path, result.manifest.model_dump(mode="json"))
    observations_path.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
            + "\n"
            for item in result.observations
        ),
        encoding="utf-8",
    )
    _write_json(
        summary_path,
        {
            "summary": result.summary.model_dump(mode="json"),
            "gate": result.gate.model_dump(mode="json"),
        },
    )
    report_path.write_text(_render_reliability_report(result), encoding="utf-8")
    return AgentReliabilityArtifacts(
        output_dir=destination.as_posix(),
        manifest_path=manifest_path.as_posix(),
        observations_path=observations_path.as_posix(),
        summary_path=summary_path.as_posix(),
        report_path=report_path.as_posix(),
    )


def build_observed_ollama_client_factory(
    model_config: AgentReliabilityModelConfig,
    *,
    host: str = DEFAULT_OLLAMA_HOST,
) -> AgentReliabilityClientFactory:
    """Crea clientes Ollama aislados con telemetria fisica por escenario."""

    def factory(
        _scenario: AgentReliabilityScenario,
        _state: TFMStateModel,
        physical_attempts: list[AgentReliabilityAttempt],
    ) -> JSONLLMClient:
        return ObservedOllamaJSONClient(
            physical_attempts=physical_attempts,
            model=model_config.model,
            host=host,
            timeout_seconds=model_config.timeout_seconds,
            think=model_config.think,
            max_json_repair_attempts=model_config.max_json_repair_attempts,
            num_ctx=model_config.num_ctx,
            num_predict=model_config.num_predict,
        )

    return factory


def _invoke_scenario(
    scenario: AgentReliabilityScenario,
    state: TFMStateModel,
    client: JSONLLMClient,
) -> AgentDecisionBase:
    agents = build_ollama_pipeline_agents(client)
    if scenario.entrypoint == "supervisor":
        return agents.supervisor(state)
    if scenario.entrypoint == "cleaner":
        return agents.cleaner(state)
    if scenario.entrypoint == "structurer":
        return agents.structurer(state, memory_context=None)
    if scenario.entrypoint == "modeler":
        return agents.modeler(state, memory_context=None)
    if scenario.entrypoint == "evaluator":
        return agents.evaluator(state, memory_context=None)
    if scenario.entrypoint == "report_writer":
        return agents.report_writer(state)
    if scenario.entrypoint == "report_reviser":
        return agents.report_reviser(
            state,
            _revision_verification(state),
            revision_round=1,
        )
    if scenario.entrypoint == "report_verifier":
        return decide_report_verification_action(
            state,
            report_markdown=_report_markdown_for_scenario(scenario),
            llm_client=client,
            use_llm=True,
        )
    if scenario.entrypoint == "modeler_retry":
        return decide_modeling_retry_action(
            state,
            failure_analysis={
                "failure_kind": "metric_threshold_failure",
                "recall": 0.71,
                "false_positive_rate": 0.18,
                "evidence_refs": ["metrics:recall", "metrics:false_positive_rate"],
            },
            source_run_id=f"{state.run_id}:source",
            attempt_number=1,
            max_attempts=2,
            memory_context=None,
            llm_client=client,
            use_llm=True,
        )
    raise ValueError(f"unsupported agent reliability entrypoint: {scenario.entrypoint}")


def _observation_from_decision(
    *,
    observation_id: str,
    scenario: AgentReliabilityScenario,
    repetition: int,
    state: TFMStateModel,
    decision: AgentDecisionBase,
    elapsed_ms: float,
    logical_attempts: list[AgentReliabilityAttempt],
    physical_attempts: list[AgentReliabilityAttempt],
) -> AgentReliabilityObservation:
    trace = decision.generation_trace
    invariants = _semantic_invariants(scenario, state, decision)
    origin = None if trace is None else trace.origin
    validation_status = None if trace is None else trace.validation_status
    if origin == "guardrail_fallback":
        outcome: AgentReliabilityOutcome = "fallback"
    elif origin != "llm":
        outcome = "non_agentic"
    elif not all(item.passed for item in invariants):
        outcome = "semantic_failure"
    elif (
        validation_status == "repaired"
        or len(logical_attempts) > 1
        or len(physical_attempts) > len(logical_attempts)
        or any(item.kind == "json_repair" for item in physical_attempts)
    ):
        outcome = "llm_repaired"
    else:
        outcome = "first_pass"
    return AgentReliabilityObservation(
        observation_id=observation_id,
        scenario_id=scenario.scenario_id,
        entrypoint=scenario.entrypoint,
        dataset=scenario.dataset,
        repetition=repetition,
        outcome=outcome,
        elapsed_ms=elapsed_ms,
        decision_id=decision.decision_id,
        generation_origin=origin,
        generation_validation_status=validation_status,
        generation_attempt_index=None if trace is None else trace.attempt_index,
        fallback_cause=None if trace is None else trace.fallback_cause,
        trace_available=trace is not None,
        invariants=invariants,
        logical_attempts=logical_attempts,
        physical_attempts=physical_attempts,
        decision_payload=decision.model_dump(mode="json"),
    )


def _semantic_invariants(
    scenario: AgentReliabilityScenario,
    state: TFMStateModel,
    decision: AgentDecisionBase,
) -> list[AgentReliabilityInvariant]:
    expected_agent = {
        "supervisor": "supervisor",
        "cleaner": "cleaner",
        "structurer": "structurer",
        "modeler": "modeler",
        "modeler_retry": "modeler",
        "evaluator": "evaluator",
        "report_writer": "report_writer",
        "report_reviser": "report_writer",
        "report_verifier": "report_verifier",
    }[scenario.entrypoint]
    checks = [
        AgentReliabilityInvariant(
            invariant_id="agent_identity",
            passed=decision.agent_name == expected_agent,
            detail=f"expected={expected_agent}; observed={decision.agent_name}",
        ),
        AgentReliabilityInvariant(
            invariant_id="decision_id_scoped_to_run",
            passed=decision.decision_id.startswith(f"{state.run_id}:"),
            detail=f"decision_id={decision.decision_id}",
        ),
    ]
    payload = decision.model_dump(mode="python")
    hypothesis = payload.get("hypothesis") or {}
    expected_hypothesis_kind = {
        "supervisor": "routing_readiness",
        "cleaner": "data_quality",
        "structurer": "temporal_representation",
        "modeler": "model_performance",
        "modeler_retry": "model_performance",
        "evaluator": "operational_acceptance",
        "report_writer": "report_grounding",
        "report_reviser": "revision_effectiveness",
        "report_verifier": "report_fidelity",
    }[scenario.entrypoint]
    required_hypothesis_fields = (
        "statement",
        "scope",
        "evidence_cutoff",
        "expected_observation",
        "falsification_criterion",
        "evidence_refs",
        "risk_notes",
    )
    missing_hypothesis_fields = [
        field
        for field in required_hypothesis_fields
        if not hypothesis.get(field)
    ]
    checks.extend(
        [
            _invariant(
                "common_hypothesis_kind",
                hypothesis.get("kind") == expected_hypothesis_kind,
                (
                    f"expected={expected_hypothesis_kind}; "
                    f"observed={hypothesis.get('kind')}"
                ),
            ),
            _invariant(
                "common_hypothesis_complete",
                not missing_hypothesis_fields,
                f"missing={missing_hypothesis_fields}",
            ),
        ]
    )
    if scenario.entrypoint == "supervisor":
        checks.extend(
            [
                _invariant(
                    "supervisor_next_stage",
                    payload.get("next_stage") == scenario.expected_next_stage,
                    f"expected={scenario.expected_next_stage}; observed={payload.get('next_stage')}",
                ),
                _invariant(
                    "supervisor_next_node",
                    payload.get("next_node") == scenario.expected_next_node,
                    f"expected={scenario.expected_next_node}; observed={payload.get('next_node')}",
                ),
            ]
        )
    elif scenario.entrypoint == "cleaner":
        config = payload.get("cleaning_config") or {}
        checks.extend(
            [
                _invariant(
                    "cleaner_removes_non_finite",
                    config.get("remove_non_finite") is True,
                    f"remove_non_finite={config.get('remove_non_finite')}",
                ),
                _invariant(
                    "cleaner_sample_rate",
                    config.get("resample_to_hz")
                    == state.project_context.target_sample_rate_hz,
                    (
                        f"expected={state.project_context.target_sample_rate_hz}; "
                        f"observed={config.get('resample_to_hz')}"
                    ),
                ),
            ]
        )
    elif scenario.entrypoint == "structurer":
        config = payload.get("structuring_config") or {}
        checks.extend(
            [
                _invariant(
                    "structurer_channel",
                    config.get("main_channel") == state.project_context.main_channel,
                    (
                        f"expected={state.project_context.main_channel}; "
                        f"observed={config.get('main_channel')}"
                    ),
                ),
                _invariant(
                    "structurer_features",
                    bool(config.get("features")),
                    f"features={config.get('features')}",
                ),
            ]
        )
    elif scenario.entrypoint == "modeler":
        strategy = payload.get("decision_strategy") or {}
        checks.extend(
            [
                _invariant(
                    "modeler_hypothesis",
                    bool(strategy.get("hypothesis")),
                    f"hypothesis={strategy.get('hypothesis')}",
                ),
                _invariant(
                    "modeler_supported_family",
                    (payload.get("modeling_config") or {}).get("model_name")
                    in {
                        "autoencoder_dense",
                        "isolation_forest",
                        "one_class_svm",
                        "pca_reconstruction_error",
                    },
                    (
                        "model_name="
                        f"{(payload.get('modeling_config') or {}).get('model_name')}"
                    ),
                ),
            ]
        )
    elif scenario.entrypoint == "modeler_retry":
        checks.extend(
            [
                _invariant(
                    "retry_attempt_number",
                    payload.get("attempt_number") == 1,
                    f"attempt_number={payload.get('attempt_number')}",
                ),
                _invariant(
                    "retry_learning_summary",
                    bool(payload.get("learning_summary")),
                    f"learning_summary={payload.get('learning_summary')}",
                ),
            ]
        )
    elif scenario.entrypoint == "evaluator":
        evaluation = payload.get("evaluation") or {}
        checks.append(
            _invariant(
                "evaluator_approval",
                evaluation.get("approved") == scenario.expected_approved,
                (
                    f"expected={scenario.expected_approved}; "
                    f"observed={evaluation.get('approved')}"
                ),
            )
        )
    elif scenario.entrypoint == "report_writer":
        sections = payload.get("sections") or []
        checks.append(
            _invariant(
                "report_sections",
                len(sections) >= 6,
                f"section_count={len(sections)}",
            )
        )
    elif scenario.entrypoint == "report_reviser":
        accepted = payload.get("accepted_issue_ids") or []
        checks.append(
            _invariant(
                "revision_addresses_issue",
                "unsupported-industrial-claim" in accepted,
                f"accepted_issue_ids={accepted}",
            )
        )
    elif scenario.entrypoint == "report_verifier":
        overlay_issue_ids = payload.get("policy_overlay_issue_ids") or []
        checks.extend(
            [
                _invariant(
                    "verification_status",
                    payload.get("verification_status")
                    == scenario.expected_verification_status,
                    (
                        f"expected={scenario.expected_verification_status}; "
                        f"observed={payload.get('verification_status')}"
                    ),
                ),
                _invariant(
                    "verifier_without_policy_overlay",
                    payload.get("policy_overlay_applied") is not True,
                    (
                        "policy_overlay_applied="
                        f"{payload.get('policy_overlay_applied')}; "
                        f"policy_overlay_issue_ids={overlay_issue_ids}"
                    ),
                ),
            ]
        )
    return checks


def _entrypoint_summary(
    entrypoint: AgentReliabilityEntrypoint,
    observations: Sequence[AgentReliabilityObservation],
) -> AgentReliabilityEntrypointSummary:
    count = len(observations)
    first_pass = _count_outcome(observations, "first_pass")
    repaired = _count_outcome(observations, "llm_repaired")
    elapsed = [item.elapsed_ms for item in observations]
    return AgentReliabilityEntrypointSummary(
        entrypoint=entrypoint,
        observation_count=count,
        first_pass_count=first_pass,
        repaired_count=repaired,
        fallback_count=_count_outcome(observations, "fallback"),
        non_agentic_count=_count_outcome(observations, "non_agentic"),
        semantic_failure_count=_count_outcome(observations, "semantic_failure"),
        error_count=_count_outcome(observations, "error"),
        agentic_success_rate=_safe_rate(first_pass + repaired, count),
        first_pass_rate=_safe_rate(first_pass, count),
        p50_elapsed_ms=_percentile(elapsed, 0.50),
        p95_elapsed_ms=_percentile(elapsed, 0.95),
    )


def _revision_verification(state: TFMStateModel) -> ReportVerificationDecision:
    issue = ReportVerificationIssue(
        issue_id="unsupported-industrial-claim",
        issue_type="unsupported_claim",
        severity="high",
        claim_text="El sistema esta validado para produccion industrial.",
        reason="La evidencia disponible solo corresponde a un benchmark local.",
        evidence_refs=["report:final_report", "evaluation:limitations"],
        suggested_fix="Reformular como validacion local reproducible.",
    )
    return ReportVerificationDecision(
        decision_id=f"{state.run_id}:report_verifier:001",
        rationale="La afirmacion excede la evidencia persistida.",
        confidence=0.95,
        hypothesis=AgentHypothesis(
            kind="report_fidelity",
            statement=(
                "El informe requiere revision porque una afirmacion industrial "
                "excede la evidencia local persistida."
            ),
            scope="Fixture de revision factual del informe.",
            evidence_cutoff="Informe y limitaciones persistidas antes de revisar.",
            expected_observation=(
                "La revision elimina la afirmacion industrial y conserva la limitacion local."
            ),
            falsification_criterion=(
                "La afirmacion estaba respaldada por evidencia industrial valida o la "
                "revision no resuelve el exceso de alcance."
            ),
            evidence_refs=["report:final_report", "evaluation:limitations"],
            risk_notes=["Bloquear estilo inocuo seria una sobrecorreccion."],
        ),
        report_path=state.report_path or _expected_report_path(state),
        verification_status="needs_revision",
        summary="Debe corregirse una afirmacion industrial no soportada.",
        unsupported_claims=[issue],
        misleading_claims=[],
        missing_limitations=[],
        required_corrections=[issue.suggested_fix],
        acceptable_style_notes=[],
        evidence_refs=["report:final_report", "evaluation:limitations"],
    )


def _report_markdown_for_scenario(scenario: AgentReliabilityScenario) -> str:
    if scenario.state_profile == "cwru_report_unsafe":
        return (
            "El sistema esta listo para produccion y dispone de validacion "
            "industrial completa. Los resultados garantizan su generalizacion."
        )
    return (
        "Informe tecnico local sobre CWRU. Recall=0.95 y FPR=0.04 segun las "
        "metricas persistidas. La validacion esta limitada al benchmark local; "
        "no demuestra generalizacion ni preparacion para produccion industrial."
    )


def _nasa_online_blind_context() -> ProjectContext:
    return ProjectContext(
        dataset="nasa_ims_bearing",
        machine_type="rotating_machinery",
        signal_type="vibration",
        objective="run_to_failure_degradation",
        target_sample_rate_hz=20_000,
        main_channel="channel_1",
        label_mode="degradation",
        supervision_profile="run_to_failure_degradation",
        label_granularity="event",
        label_source="none",
        data_provenance="official",
        provenance_detection_method="official_dataset_provenance",
        trajectory_group_id="nasa_set2_bearing1",
        evaluation_group_id="nasa_set2_official_v2",
    )


def _nasa_metrics() -> MetricsReport:
    return MetricsReport(
        extra={
            "metric_families": "run_to_failure_degradation",
            "degradation_available": True,
            "degradation_confirmed_degradation_before_failure_rate": 1.0,
            "degradation_mean_persistent_lead_time_to_failure": 201600.5632,
            "degradation_mean_health_index_drop": 91.1146,
            "degradation_mean_health_monotonicity": 0.5293,
            "degradation_mean_health_robustness": 0.9820,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.7937,
        }
    )


def _expected_report_path(state: TFMStateModel) -> str:
    return f"codigo/reports/{state.project_context.dataset}/{state.run_id}/final_report.md"


def _render_reliability_report(result: AgentReliabilityResult) -> str:
    summary = result.summary
    lines = [
        f"# Fiabilidad agentica decision-only — {result.plan.plan_id}",
        "",
        "## Dictamen",
        "",
        f"- Gate: `{result.gate.verdict}`",
        f"- Detalle: {result.gate.detail}",
        f"- Bloqueos: {', '.join(result.gate.blockers) or 'ninguno'}",
        "",
        "## Resumen",
        "",
        f"- Observaciones: `{summary.observation_count}`",
        f"- First-pass: `{summary.first_pass_count}` ({summary.first_pass_rate:.2%})",
        f"- Reparadas por LLM: `{summary.repaired_count}`",
        f"- Fallbacks: `{summary.fallback_count}`",
        f"- No agenticas: `{summary.non_agentic_count}`",
        f"- Fallos semanticos: `{summary.semantic_failure_count}`",
        f"- Errores: `{summary.error_count}`",
        f"- Exito agentico: `{summary.agentic_success_rate:.2%}`",
        f"- Flujos/repeticiones completos: `{summary.flow_success_rate:.2%}`",
        f"- Cobertura de traza: `{summary.trace_coverage_rate:.2%}`",
        "",
        "## Por callable",
        "",
    ]
    for item in summary.entrypoints:
        lines.extend(
            [
                f"### {item.entrypoint}",
                "",
                (
                    f"{item.observation_count} observaciones; first-pass "
                    f"{item.first_pass_count}; reparadas {item.repaired_count}; "
                    f"fallback {item.fallback_count}; no agenticas "
                    f"{item.non_agentic_count}; fallos semanticos "
                    f"{item.semantic_failure_count}; errores {item.error_count}."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Alcance",
            "",
            "La bateria no ejecuta datasets, modelos, memoria RAG ni LangGraph. ",
            "Una reparacion JSON o de contrato sigue siendo una decision LLM; ",
            "cualquier fallback o ruta determinista bloquea el gate.",
            "",
            "## Limitacion de telemetria",
            "",
            result.manifest.trace_limitation,
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _attempt_from_error(
    *,
    attempt_index: int,
    kind: AttemptKind,
    messages: Sequence[LLMMessage],
    json_schema: dict[str, Any] | None,
    elapsed_ms: float,
    exc: Exception,
) -> AgentReliabilityAttempt:
    return AgentReliabilityAttempt(
        attempt_index=attempt_index,
        kind=kind,
        status="error",
        message_count=len(messages),
        prompt_sha256=_messages_sha256(messages),
        schema_sha256=_json_sha256(json_schema),
        elapsed_ms=elapsed_ms,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _messages_sha256(messages: Sequence[LLMMessage]) -> str:
    return _json_sha256(
        [{"role": item.role, "content": item.content} for item in messages]
    ) or hashlib.sha256(b"null").hexdigest()


def _json_sha256(payload: Any) -> str | None:
    if payload is None:
        return None
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scenario_pack_sha256(scenarios: Sequence[AgentReliabilityScenario]) -> str:
    return _json_sha256([item.model_dump(mode="json") for item in scenarios]) or "0" * 64


def _reliability_source_sha256s() -> dict[str, str]:
    paths = [
        Path("codigo/app/services/agent_reliability.py"),
        Path("codigo/app/services/llm.py"),
        Path("codigo/app/services/llm_agents.py"),
        Path("codigo/app/schemas/agent_decisions.py"),
        Path("codigo/app/agents/supervisor.py"),
        Path("codigo/app/agents/cleaner.py"),
        Path("codigo/app/agents/structurer.py"),
        Path("codigo/app/agents/modeler.py"),
        Path("codigo/app/agents/evaluator.py"),
        Path("codigo/app/agents/report_writer.py"),
        Path("codigo/app/agents/report_verifier.py"),
    ]
    return {
        path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _is_json_repair_call(messages: Sequence[LLMMessage]) -> bool:
    if not messages:
        return False
    tail = messages[-1].content.lower()
    return "respuesta anterior no era json valido" in tail


def _plain_observation_run_id(observation_id: str) -> str:
    return observation_id.replace(":", "-").replace("_", "-")


def _ensure_plain_name(value: str) -> None:
    path = Path(value)
    if not value.strip() or path.name != value or path.is_absolute():
        raise ValueError("plan_id must be a plain directory name")


def _elapsed_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000.0)


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _optional_non_empty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _invariant(
    invariant_id: str,
    passed: bool,
    detail: str,
) -> AgentReliabilityInvariant:
    return AgentReliabilityInvariant(
        invariant_id=invariant_id,
        passed=passed,
        detail=detail,
    )


def _count_outcome(
    observations: Sequence[AgentReliabilityObservation],
    outcome: AgentReliabilityOutcome,
) -> int:
    return sum(item.outcome == outcome for item in observations)


def _safe_rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
