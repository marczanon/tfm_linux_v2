"""Protocolos experimentales reproducibles y puertas previas a ejecuciones LLM.

Este modulo ya posee los planes comparables CWRU y NASA IMS. La preparacion
pre-Qwen se amplia aqui porque comparte la misma responsabilidad: declarar una
matriz experimental cerrada y decidir, a partir de evidencia explicita, si es
metodologicamente seguro ejecutar la siguiente fase. No ejecuta perturbaciones,
agentes ni modelos y no sustituye a los adaptadores o a la persistencia de runs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    ModelingDecision,
    ModelingDecisionProposal,
    ModelingDecisionStrategy,
    ModelingProtocolTrace,
    ReportDecision,
    ReportSection,
    StructuringDecision,
    StructuringDecisionProposal,
    StructuringProtocolTrace,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.state import ModelingConfig, StructuringConfig, TFMStateModel
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
    NASA_IMS_TEMPORAL_POLICY_V1,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, RunSnapshot
from codigo.app.services.run_registry import RunComparison, compare_runs

if TYPE_CHECKING:
    from codigo.app.graph.pipeline import PipelineAgents, PipelineExecutors


DEFAULT_EXPERIMENTS_DIR = Path("codigo/experiments/cwru_local")
DEFAULT_PLAN_ID = "cwru_iforest_threshold_v1"
DEFAULT_WINDOW_PLAN_ID = "cwru_agentic_window_sensitivity_v1"
DEFAULT_MODEL_PLAN_ID = "cwru_agentic_model_comparison_v1"
DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR = Path("codigo/experiments/run_to_failure")
DEFAULT_RUN_TO_FAILURE_PLAN_ID = "run_to_failure_agentic_model_suite_v1"
DEFAULT_RUN_TO_FAILURE_V2_PLAN_ID = "run_to_failure_agentic_model_suite_v2"
DEFAULT_RUN_TO_FAILURE_POLICY_ID = NASA_IMS_TEMPORAL_POLICY_V1
DEFAULT_PRE_QWEN_READINESS_DIR = Path(
    "codigo/reports/validation/pre_qwen_readiness"
)
PRE_QWEN_READINESS_PROTOCOL_ID = "pre_qwen_robustness_v1"
RUN_TO_FAILURE_MODEL_FAMILIES = (
    "pca_reconstruction_error",
    "isolation_forest",
    "one_class_svm",
    "autoencoder_dense",
)
RUN_TO_FAILURE_CAUSAL_V2_MODEL_FAMILIES = (
    "pca_reconstruction_error",
    "isolation_forest",
    "one_class_svm",
)
SUPPORTED_RUN_TO_FAILURE_POLICY_IDS = (
    NASA_IMS_TEMPORAL_POLICY_V1,
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
)
RUN_TO_FAILURE_CAUSAL_V2_REPORTED_METRICS = {
    "degradation_persistent_alert_run_rate",
    "degradation_mean_first_persistent_alert_time_to_trajectory_end",
    "degradation_mean_pre_monitoring_alert_rate",
    "degradation_mean_score_trend_spearman",
    "degradation_mean_initial_final_separation",
    "degradation_mean_health_index_drop",
    "degradation_mean_health_monotonicity",
    "degradation_mean_health_robustness",
    "degradation_mean_health_nominal_volatility",
    "degradation_mean_health_degradation_trend_strength",
    "degradation_mean_health_indicator_score",
    "degradation_health_trendability",
    "degradation_health_prognosability",
}

PreQwenAvailability = Literal["available", "pending"]
PreQwenOutcome = Literal["not_run", "passed", "failed"]
PreQwenCriterionKind = Literal[
    "traceability",
    "coverage",
    "isolation",
    "invariance",
    "adaptation",
]


class PreQwenCheckEvidence(StrictBaseModel):
    """Evidencia declarada para un caso; nunca implica ejecucion por defecto."""

    check_id: str = Field(min_length=1)
    availability: PreQwenAvailability = "pending"
    outcome: PreQwenOutcome = "not_run"
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_evidence_state(self) -> "PreQwenCheckEvidence":
        if self.availability == "pending" and self.outcome != "not_run":
            raise ValueError("pending checks cannot declare an executed outcome")
        if self.availability == "available" and not self.evidence_refs:
            raise ValueError("available checks require at least one evidence ref")
        if self.outcome in {"passed", "failed"} and not self.evidence_refs:
            raise ValueError("executed outcomes require at least one evidence ref")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs cannot contain duplicates")
        return self


class PreQwenRobustnessCheck(StrictBaseModel):
    """Fila auditable de la matriz pre-Qwen con criterio y estado separados."""

    check_id: str = Field(min_length=1)
    category: Literal["trace", "corpus", "dataset", "perturbation"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    datasets: list[str] = Field(default_factory=list)
    required: Literal[True] = True
    criterion_kind: PreQwenCriterionKind
    acceptance_criterion: str = Field(min_length=1)
    availability: PreQwenAvailability
    outcome: PreQwenOutcome
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, min_length=1)
    blocking: bool


class PreQwenReadinessAssessment(StrictBaseModel):
    """Matriz completa y dictamen determinista para autorizar o bloquear Qwen."""

    schema_version: Literal["pre_qwen_readiness_assessment_v1"] = (
        "pre_qwen_readiness_assessment_v1"
    )
    protocol_id: Literal["pre_qwen_robustness_v1"] = PRE_QWEN_READINESS_PROTOCOL_ID
    owner: Literal["codigo.app.services.experiment_protocol"] = (
        "codigo.app.services.experiment_protocol"
    )
    reuse_decision: Literal["extend"] = "extend"
    verdict: Literal["ready", "blocked"]
    verdict_reason: str = Field(min_length=1)
    checks: list[PreQwenRobustnessCheck] = Field(min_length=1)
    available_check_ids: list[str] = Field(default_factory=list)
    pending_check_ids: list[str] = Field(default_factory=list)
    passed_check_ids: list[str] = Field(default_factory=list)
    failed_check_ids: list[str] = Field(default_factory=list)
    not_run_check_ids: list[str] = Field(default_factory=list)
    blocker_ids: list[str] = Field(default_factory=list)


class PreQwenReadinessArtifacts(StrictBaseModel):
    """Rutas de los dos formatos deterministas del mismo dictamen."""

    json_path: str = Field(min_length=1)
    markdown_path: str = Field(min_length=1)


class _PreQwenCheckDefinition(StrictBaseModel):
    """Definicion interna inmutable de un requisito de la matriz."""

    check_id: str = Field(min_length=1)
    category: Literal["trace", "corpus", "dataset", "perturbation"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    datasets: list[str] = Field(default_factory=list)
    required: Literal[True] = True
    criterion_kind: PreQwenCriterionKind
    acceptance_criterion: str = Field(min_length=1)


class ExperimentSpec(StrictBaseModel):
    """Configuracion de una ejecucion dentro de un plan experimental."""

    experiment_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    modeling_config: ModelingConfig
    structuring_config: StructuringConfig | None = None
    expected_effect: str | None = None


class ExperimentExecutionManifest(StrictBaseModel):
    """Configuracion efectiva auditable sin hosts, credenciales ni secretos."""

    schema_version: Literal["experiment_execution_manifest_v1"] = (
        "experiment_execution_manifest_v1"
    )
    llm_backend: Literal["ollama"] | None = None
    use_llm: bool = False
    llm_model: str | None = Field(default=None, min_length=1)
    llm_think: bool | None = None
    llm_timeout_seconds: float | None = Field(default=None, gt=0.0)
    use_memory: bool = False
    memory_backend: str = Field(min_length=1)
    memory_root: str | None = Field(default=None, min_length=1)
    embedding_provider: Literal["ollama", "local_hash"] | None = None
    embedding_model: str | None = Field(default=None, min_length=1)
    embedding_timeout_seconds: float | None = Field(default=None, gt=0.0)
    hash_dimension: int | None = Field(default=None, gt=0)
    structurer_top_k: int | None = Field(default=None, gt=0)
    modeler_top_k: int | None = Field(default=None, gt=0)
    evaluator_top_k: int | None = Field(default=None, gt=0)
    memory_min_similarity: float | None = None
    generate_decision_memory: bool | None = None
    require_human_review_before_reuse: bool | None = None


class ExperimentPlan(StrictBaseModel):
    """Manifiesto ligero de un conjunto de experimentos comparables."""

    plan_id: str = Field(min_length=1)
    dataset: Literal["cwru_bearing", "nasa_ims_bearing"] = "cwru_bearing"
    adapter_id: str | None = Field(default=None, min_length=1)
    dataset_policy_id: str | None = Field(default=None, min_length=1)
    supervision_profile: str | None = Field(default=None, min_length=1)
    execution_manifest: ExperimentExecutionManifest | None = None
    description: str = Field(min_length=1)
    experiments: list[ExperimentSpec] = Field(min_length=2)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperimentRunSummary(StrictBaseModel):
    """Resumen de una ejecucion concreta dentro de un plan."""

    experiment_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    snapshot: RunSnapshot


class ExperimentPlanResult(StrictBaseModel):
    """Resultado persistido de ejecutar un plan experimental."""

    plan_id: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    comparison_path: str = Field(min_length=1)
    results_table_path: str = Field(min_length=1)
    generated_at: datetime
    runs: list[ExperimentRunSummary] = Field(min_length=2)
    comparison: RunComparison


ExperimentExecutorFactory = Callable[[ExperimentSpec, Path], "PipelineExecutors"]
RunToFailureExperimentRunner = Callable[[ExperimentSpec, Path], "PersistedPipelineRun"]
RunComparisonFactory = Callable[[list[str], Path | str], RunComparison]


def assess_pre_qwen_readiness(
    evidence: Sequence[PreQwenCheckEvidence] = (),
) -> PreQwenReadinessAssessment:
    """Construye la matriz y bloquea mientras falte una prueba obligatoria.

    La funcion solo combina definiciones cerradas con evidencia suministrada.
    No inspecciona el entorno ni interpreta la existencia de un archivo como
    una ejecucion superada. El orden de entrada no afecta al resultado.
    """

    definitions = _pre_qwen_check_definitions()
    known_ids = {definition.check_id for definition in definitions}
    evidence_by_id: dict[str, PreQwenCheckEvidence] = {}
    for item in evidence:
        if item.check_id in evidence_by_id:
            raise ValueError(f"duplicated pre-Qwen evidence: {item.check_id}")
        if item.check_id not in known_ids:
            raise ValueError(f"unknown pre-Qwen check_id: {item.check_id}")
        evidence_by_id[item.check_id] = item

    checks: list[PreQwenRobustnessCheck] = []
    for definition in definitions:
        observed = evidence_by_id.get(
            definition.check_id,
            PreQwenCheckEvidence(check_id=definition.check_id),
        )
        checks.append(
            PreQwenRobustnessCheck(
                **definition.model_dump(),
                availability=observed.availability,
                outcome=observed.outcome,
                evidence_refs=observed.evidence_refs,
                notes=observed.notes,
                blocking=observed.outcome != "passed",
            )
        )

    available_ids = [
        check.check_id for check in checks if check.availability == "available"
    ]
    pending_ids = [
        check.check_id for check in checks if check.availability == "pending"
    ]
    passed_ids = [check.check_id for check in checks if check.outcome == "passed"]
    failed_ids = [check.check_id for check in checks if check.outcome == "failed"]
    not_run_ids = [
        check.check_id for check in checks if check.outcome == "not_run"
    ]
    blocker_ids = [check.check_id for check in checks if check.blocking]
    verdict: Literal["ready", "blocked"] = "blocked" if blocker_ids else "ready"
    if verdict == "ready":
        reason = (
            "Todos los requisitos obligatorios tienen resultado passed y "
            "evidencia referenciada; se puede iniciar la validacion con Qwen."
        )
    else:
        reason = (
            f"BLOCKED: {len(blocker_ids)} de {len(checks)} requisitos "
            "obligatorios no tienen resultado passed con evidencia. No se "
            "autoriza una nueva validacion con Qwen."
        )
    return PreQwenReadinessAssessment(
        verdict=verdict,
        verdict_reason=reason,
        checks=checks,
        available_check_ids=available_ids,
        pending_check_ids=pending_ids,
        passed_check_ids=passed_ids,
        failed_check_ids=failed_ids,
        not_run_check_ids=not_run_ids,
        blocker_ids=blocker_ids,
    )


def current_pre_qwen_capability_evidence() -> list[PreQwenCheckEvidence]:
    """Declara capacidades localizadas, sin atribuirles una ejecucion global.

    La traza estructurada y los adaptadores CWRU/NASA oficial poseen contratos
    y tests focalizados. Se marcan como disponibles pero `not_run`: eso no
    acredita todavia su cobertura en una bateria experimental completa. Los
    demas requisitos quedan pendientes por omision.
    """

    return [
        PreQwenCheckEvidence(
            check_id="trace_origin_attempt_fallback",
            availability="available",
            outcome="not_run",
            evidence_refs=[
                "codigo/app/schemas/agent_decisions.py",
                "codigo/tests/test_agent_decisions_schema.py",
                "codigo/tests/test_cleaner_agent.py",
                "codigo/tests/test_structurer_agent.py",
                "codigo/tests/test_modeler_agent.py",
                "codigo/tests/test_evaluator_agent.py",
            ],
            notes=(
                "El contrato y los cuatro roles de decision ya registran origen, "
                "intentos y fallbacks; falta demostrar cobertura del 100 % sobre "
                "el paquete de ejecuciones pre-Qwen."
            ),
        ),
        PreQwenCheckEvidence(
            check_id="dataset_nasa_ims_official",
            availability="available",
            outcome="not_run",
            evidence_refs=[
                "codigo/app/services/dataset_adapters.py",
                "codigo/tests/test_nasa_ims_official_provenance.py",
            ],
            notes=(
                "El adaptador y la evidencia de procedencia existen; la prueba "
                "pre-Qwen multi-perturbacion no se ha ejecutado."
            ),
        ),
        PreQwenCheckEvidence(
            check_id="dataset_cwru_official",
            availability="available",
            outcome="not_run",
            evidence_refs=[
                "codigo/app/services/dataset_adapters.py",
                "codigo/tests/test_dataset_adapters.py",
            ],
            notes=(
                "El adaptador CWRU existe; la prueba pre-Qwen comparable no se "
                "ha ejecutado."
            ),
        ),
    ]


def write_pre_qwen_readiness_artifacts(
    assessment: PreQwenReadinessAssessment,
    *,
    output_dir: Path | str = DEFAULT_PRE_QWEN_READINESS_DIR,
) -> PreQwenReadinessArtifacts:
    """Persiste JSON y Markdown sin convertir `not_run` en evidencia superada."""

    destination = Path(output_dir)
    json_path = destination / "pre_qwen_readiness.json"
    markdown_path = destination / "pre_qwen_readiness.md"
    _write_json(json_path, assessment.model_dump(mode="json"))
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(
        _pre_qwen_readiness_markdown(assessment),
        encoding="utf-8",
    )
    return PreQwenReadinessArtifacts(
        json_path=str(json_path),
        markdown_path=str(markdown_path),
    )


def _pre_qwen_check_definitions() -> tuple[_PreQwenCheckDefinition, ...]:
    common_datasets = [
        "nasa_ims_bearing_official",
        "cwru_bearing_official",
        "generic_csv_tsv_npz",
    ]
    return (
        _PreQwenCheckDefinition(
            check_id="trace_origin_attempt_fallback",
            category="trace",
            title="Origen, intentos y fallbacks agenticos",
            description=(
                "Audita cada intento de decision, incluida su procedencia, "
                "validacion, reparacion, guarda y fallback."
            ),
            criterion_kind="traceability",
            acceptance_criterion=(
                "El 100 % de las decisiones identifica origin, attempt_id, "
                "orden de intentos, estado de validacion y, si aplica, causa y "
                "destino del fallback; ningun dato depende solo del rationale."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="trace_decision_config_artifact_link",
            category="trace",
            title="Vinculo decision-configuracion-artefacto",
            description=(
                "Demuestra que la propuesta observada y la configuracion "
                "realmente ejecutada no se confunden."
            ),
            criterion_kind="traceability",
            acceptance_criterion=(
                "El 100 % de las decisiones enlaza decision_id con la "
                "configuracion efectiva, executor_result y hashes de todos los "
                "artefactos producidos, incluyendo overrides del protocolo."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="corpus_frozen_versioned",
            category="corpus",
            title="Corpus congelado y versionado",
            description=(
                "Congela datasets, particiones y corpus RAG antes de comparar "
                "agentes o backends vectoriales."
            ),
            datasets=common_datasets,
            criterion_kind="isolation",
            acceptance_criterion=(
                "Inventarios, particiones y registros RAG tienen identificador "
                "de version y digest reproducible; una reevaluacion usa "
                "exactamente los mismos elementos y politicas."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="corpus_no_future_or_label_leakage",
            category="corpus",
            title="Corpus sin fuga futura ni de etiquetas",
            description=(
                "Separa evidencia disponible al decidir de targets y futuro "
                "reservados exclusivamente para evaluacion."
            ),
            datasets=common_datasets,
            criterion_kind="isolation",
            acceptance_criterion=(
                "Cero referencias prohibidas, cero features derivadas del "
                "futuro y cero memorias construidas con el target de la muestra "
                "evaluada atraviesan la frontera online-blind."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="dataset_nasa_ims_official",
            category="dataset",
            title="NASA IMS oficial run-to-failure",
            description=(
                "Incluye una trayectoria NASA IMS oficial con procedencia y "
                "orden causal verificables."
            ),
            datasets=["nasa_ims_bearing_official"],
            criterion_kind="coverage",
            acceptance_criterion=(
                "El inventario oficial, su digest, el manifiesto causal y la "
                "politica run-to-failure se validan antes de cualquier prueba."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="dataset_cwru_official",
            category="dataset",
            title="CWRU oficial etiquetado",
            description=(
                "Incluye CWRU MAT como contraste supervisado de condiciones y "
                "tipos de fallo."
            ),
            datasets=["cwru_bearing_official"],
            criterion_kind="coverage",
            acceptance_criterion=(
                "El manifiesto, canales, frecuencia de muestreo y etiquetas "
                "CWRU quedan versionados y producen una referencia repetible."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="dataset_generic_third_format",
            category="dataset",
            title="Tercer formato generico ejecutable",
            description=(
                "Evita concluir generalizacion usando solo los dos datasets "
                "para los que se diseno inicialmente el pipeline."
            ),
            datasets=["generic_csv_tsv_npz"],
            criterion_kind="coverage",
            acceptance_criterion=(
                "Una senal CSV, TSV o NPZ recorre el runner comun hasta "
                "artefactos evaluables mediante descriptor explicito, sin una "
                "rama de ejecucion especifica del dataset."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_channels",
            category="perturbation",
            title="Permutacion, renombrado y canal irrelevante",
            description=(
                "Altera posicion y nombre de canales y agrega un canal que no "
                "contiene informacion util."
            ),
            datasets=common_datasets,
            criterion_kind="invariance",
            acceptance_criterion=(
                "Con el mapeo semantico conservado, se selecciona la misma "
                "senal y la decision/configuracion efectiva permanece igual; "
                "si el mapeo es ambiguo, se bloquea explicitamente."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_sample_rate",
            category="perturbation",
            title="Frecuencia de muestreo 0.8x, 1.2x y mixta",
            description=(
                "Comprueba que una ventana en muestras no se trate como la "
                "misma duracion fisica bajo frecuencias distintas."
            ),
            datasets=common_datasets,
            criterion_kind="adaptation",
            acceptance_criterion=(
                "El sistema adapta resampling y ventana para conservar la "
                "duracion fisica fijada, o rechaza frecuencias mixtas no "
                "resolubles con una causa estructurada."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_gain_offset_polarity",
            category="perturbation",
            title="Ganancia, offset y polaridad",
            description=(
                "Aplica transformaciones de sensor que no cambian el estado "
                "mecanico subyacente."
            ),
            datasets=common_datasets,
            criterion_kind="invariance",
            acceptance_criterion=(
                "Tras la normalizacion declarada, decisiones y alertas se "
                "mantienen dentro de la tolerancia previamente congelada; "
                "cualquier sensibilidad residual se cuantifica."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_nan_dropout",
            category="perturbation",
            title="NaN, infinito y dropout",
            description=(
                "Introduce ausencias puntuales y segmentos perdidos sin "
                "cambiar silenciosamente el eje temporal."
            ),
            datasets=common_datasets,
            criterion_kind="adaptation",
            acceptance_criterion=(
                "Las ausencias se imputan, segmentan o bloquean con trazabilidad; "
                "nunca se eliminan muestras colapsando el tiempo sin declararlo."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_temporal_order",
            category="perturbation",
            title="Orden, duplicados, gaps y jitter temporal",
            description=(
                "Desordena snapshots, duplica marcas y crea discontinuidades "
                "temporales controladas."
            ),
            datasets=common_datasets,
            criterion_kind="adaptation",
            acceptance_criterion=(
                "Se aplica orden estable auditado, se bloquean duplicados "
                "ambiguos y cada gap reinicia la continuidad; el jitter sigue "
                "una tolerancia congelada."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_truncated_trajectory",
            category="perturbation",
            title="Trayectoria truncada o demasiado corta",
            description=(
                "Reduce snapshots y oculta el final para comprobar que el "
                "sistema no presupone una trayectoria completa."
            ),
            datasets=common_datasets,
            criterion_kind="adaptation",
            acceptance_criterion=(
                "La salida declara evidencia insuficiente o reduce el alcance; "
                "no estima fallo, lead time ni calidad de degradacion que no "
                "puedan sostenerse con el tramo observado."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_future_label_bait",
            category="perturbation",
            title="Cebo de futuro y etiquetas",
            description=(
                "Inyecta campos altamente predictivos pero prohibidos durante "
                "la decision online-blind."
            ),
            datasets=common_datasets,
            criterion_kind="invariance",
            acceptance_criterion=(
                "La decision y configuracion online-blind son identicas con y "
                "sin cebo, y el contador de rutas o referencias prohibidas es "
                "exactamente cero."
            ),
        ),
        _PreQwenCheckDefinition(
            check_id="perturbation_adversarial_memory_corpus",
            category="perturbation",
            title="Corpus RAG adversarial",
            description=(
                "Combina recuerdos muy similares pero incompatibles con una "
                "leccion metodologica transferible y aplicable."
            ),
            datasets=common_datasets,
            criterion_kind="isolation",
            acceptance_criterion=(
                "El quality gate excluye todos los recuerdos incompatibles, "
                "conserva la memoria transferible correcta y la traza distingue "
                "recuperado, citado y realmente usado."
            ),
        ),
    )


def _pre_qwen_readiness_markdown(
    assessment: PreQwenReadinessAssessment,
) -> str:
    lines = [
        f"# Preparacion pre-Qwen: {assessment.verdict.upper()}",
        "",
        assessment.verdict_reason,
        "",
        "> Este documento no acredita ejecuciones por la mera existencia de "
        "un test o adaptador. `not_run` significa que la prueba de robustez no "
        "se ha ejecutado.",
        "",
        "## Decision de reutilizacion",
        "",
        "Se extiende `codigo.app.services.experiment_protocol` porque ya es el "
        "propietario de planes comparables, criterios de aceptacion y artefactos "
        "experimentales. La puerta pre-Qwen solo declara y evalua evidencia; no "
        "duplica adaptadores, runners, trazas ni ejecutores.",
        "",
        "## Comprobaciones disponibles",
        "",
    ]
    available = [
        check for check in assessment.checks if check.availability == "available"
    ]
    if available:
        lines.extend(
            f"- `{check.check_id}` — resultado `{check.outcome}`."
            for check in available
        )
    else:
        lines.append("- Ninguna.")
    lines.extend(["", "## Comprobaciones pendientes", ""])
    pending = [
        check for check in assessment.checks if check.availability == "pending"
    ]
    if pending:
        lines.extend(f"- `{check.check_id}` — {check.title}." for check in pending)
    else:
        lines.append("- Ninguna.")
    lines.extend(["", "## Matriz y criterios", ""])
    for check in assessment.checks:
        datasets = ", ".join(check.datasets) if check.datasets else "transversal"
        lines.extend(
            [
                f"### {check.title}",
                "",
                f"- ID: `{check.check_id}`",
                f"- Categoria: `{check.category}`",
                f"- Datasets: {datasets}",
                f"- Criterio: `{check.criterion_kind}`",
                f"- Disponibilidad: `{check.availability}`",
                f"- Resultado: `{check.outcome}`",
                f"- Bloquea Qwen: `{'si' if check.blocking else 'no'}`",
                f"- Aceptacion: {check.acceptance_criterion}",
            ]
        )
        if check.evidence_refs:
            lines.append("- Evidencias declaradas: " + ", ".join(check.evidence_refs))
        if check.notes:
            lines.append(f"- Nota: {check.notes}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def default_cwru_experiment_plan(
    plan_id: str = DEFAULT_PLAN_ID,
) -> ExperimentPlan:
    """Devuelve el primer plan local: baseline y umbral mas conservador."""

    baseline_config = _modeling_config_with_hyperparameters({})
    conservative_config = _modeling_config_with_hyperparameters(
        {"threshold_quantile": 1.0}
    )
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion local de Isolation Forest sobre CWRU variando solo "
            "el cuantil usado para fijar el umbral de anomalia."
        ),
        experiments=[
            ExperimentSpec(
                experiment_id="baseline_threshold_099",
                run_id=f"{plan_id}_baseline_threshold_099",
                description=(
                    "Baseline del MVP con threshold_quantile=0.99 y 200 "
                    "arboles."
                ),
                modeling_config=baseline_config,
                expected_effect="Referencia reproducible del MVP local.",
            ),
            ExperimentSpec(
                experiment_id="conservative_threshold_100",
                run_id=f"{plan_id}_conservative_threshold_100",
                description=(
                    "Umbral mas conservador usando threshold_quantile=1.0 "
                    "manteniendo el resto de hiperparametros."
                ),
                modeling_config=conservative_config,
                expected_effect=(
                    "Reducir falsos positivos a costa de posible menor recall."
                ),
            ),
        ],
    )


def default_run_to_failure_model_suite_plan(
    plan_id: str = DEFAULT_RUN_TO_FAILURE_PLAN_ID,
    *,
    dataset_policy_id: str = DEFAULT_RUN_TO_FAILURE_POLICY_ID,
    model_families: Sequence[str] | None = None,
) -> ExperimentPlan:
    """Devuelve la suite canonica para el protocolo temporal solicitado.

    La politica v1 conserva las cuatro familias historicas. La politica causal
    v2 excluye el autoencoder hasta que exista un protocolo de *readiness*
    avanzado que no necesite informacion retrospectiva del tramo monitorizado.
    """

    from codigo.app.executors.modeling import (
        DEFAULT_AUTOENCODER_DENSE_CONFIG,
        DEFAULT_MODELING_CONFIG,
        DEFAULT_OCSVM_MODELING_CONFIG,
        DEFAULT_PCA_MODELING_CONFIG,
    )

    if dataset_policy_id not in SUPPORTED_RUN_TO_FAILURE_POLICY_IDS:
        available = ", ".join(SUPPORTED_RUN_TO_FAILURE_POLICY_IDS)
        raise ValueError(
            "unsupported run-to-failure dataset_policy_id: "
            f"{dataset_policy_id}; available: {available}"
        )

    selected_families = _selected_run_to_failure_model_families(
        dataset_policy_id,
        model_families,
    )
    experiment_catalog = {
        experiment.experiment_id: experiment
        for experiment in [
            ExperimentSpec(
                experiment_id="pca_reconstruction_error",
                run_id=f"{plan_id}_pca_reconstruction_error",
                description=(
                    "Baseline interpretable de error de reconstruccion PCA para "
                    "Health Indicator temporal."
                ),
                modeling_config=_copy_modeling_config(DEFAULT_PCA_MODELING_CONFIG),
                expected_effect=(
                    "Producir un score estable y explicable para comparar "
                    "alerta temprana, tendencia y falsas alarmas."
                ),
            ),
            ExperimentSpec(
                experiment_id="isolation_forest",
                run_id=f"{plan_id}_isolation_forest",
                description=(
                    "Detector no supervisado por aislamiento como familia "
                    "alternativa al score de reconstruccion."
                ),
                modeling_config=_copy_modeling_config(DEFAULT_MODELING_CONFIG),
                expected_effect=(
                    "Contrastar sensibilidad temprana frente a coste de falsas "
                    "alarmas nominales."
                ),
            ),
            ExperimentSpec(
                experiment_id="one_class_svm",
                run_id=f"{plan_id}_one_class_svm",
                description=(
                    "Frontera no lineal One-Class SVM para comparar estabilidad "
                    "temporal y persistencia de alertas."
                ),
                modeling_config=_copy_modeling_config(DEFAULT_OCSVM_MODELING_CONFIG),
                expected_effect=(
                    "Evaluar si una frontera no lineal mejora tendencia o reduce "
                    "picos aislados."
                ),
            ),
            ExperimentSpec(
                experiment_id="autoencoder_dense",
                run_id=f"{plan_id}_autoencoder_dense",
                description=(
                    "Autoencoder denso PyTorch para comparar reconstruccion no "
                    "lineal aprendida frente a PCA y detectores clasicos."
                ),
                modeling_config=_copy_modeling_config(
                    DEFAULT_AUTOENCODER_DENSE_CONFIG
                ),
                expected_effect=(
                    "Evaluar si el error de reconstruccion no lineal mejora "
                    "sensibilidad temporal sin aumentar falsas alarmas nominales."
                ),
            ),
        ]
    }
    experiments = [experiment_catalog[family] for family in selected_families]
    if dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        causal_structuring_config = _causal_v2_structuring_config()
        experiments = [
            spec.model_copy(
                update={
                    "structuring_config": causal_structuring_config.model_copy(
                        deep=True
                    ),
                    **_causal_v2_experiment_text(spec.experiment_id),
                }
            )
            for spec in experiments
        ]
        description = (
            "Suite canonica agentica run-to-failure sobre el runner comun y "
            "el protocolo causal v2. El entrenamiento queda limitado al "
            "baseline, el umbral se calibra antes del tramo de monitorizacion "
            "ciega y todas las familias comparten ventanas de 2048 muestras "
            "con salto 1024. La comparacion evita etiquetas futuras y "
            "metricas binarias no disponibles. Las propuestas agenticas se "
            "conservan en la traza, separadas de las configuraciones fijas "
            "ejecutadas. `StructuringConfig.label_mode=binary_anomaly` se "
            "mantiene solo por compatibilidad del contrato legacy: la politica "
            "v2 deja target vacio en calibracion y monitorizacion y no publica "
            "metricas binarias."
        )
    else:
        description = (
            "Suite canonica agentica run-to-failure sobre el runner comun. "
            "Compara familias soportadas por metricas temporales, manteniendo "
            "F1 como metrica auxiliar/proxy."
        )
    return ExperimentPlan(
        plan_id=plan_id,
        dataset="nasa_ims_bearing",
        adapter_id="nasa_ims_bearing",
        dataset_policy_id=dataset_policy_id,
        supervision_profile="run_to_failure_degradation",
        description=description,
        experiments=experiments,
    )


def _selected_run_to_failure_model_families(
    dataset_policy_id: str,
    requested: Sequence[str] | None,
) -> tuple[str, ...]:
    defaults = (
        RUN_TO_FAILURE_CAUSAL_V2_MODEL_FAMILIES
        if dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
        else RUN_TO_FAILURE_MODEL_FAMILIES
    )
    families = tuple(
        dict.fromkeys(defaults if requested is None else requested)
    )
    unsupported = [
        family for family in families if family not in RUN_TO_FAILURE_MODEL_FAMILIES
    ]
    if unsupported:
        available = ", ".join(RUN_TO_FAILURE_MODEL_FAMILIES)
        raise ValueError(
            "unsupported run-to-failure model families: "
            f"{', '.join(unsupported)}; available: {available}"
        )
    if (
        dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
        and "autoencoder_dense" in families
    ):
        raise ValueError(
            "autoencoder_dense is disabled for nasa_ims_run_to_failure_v2 "
            "until causal advanced-model readiness is available"
        )
    if len(families) < 2:
        raise ValueError(
            "run-to-failure model suite requires at least two distinct model "
            "families for a comparable experiment plan"
        )
    return families


def _causal_v2_structuring_config() -> StructuringConfig:
    """Configuracion comun; los splits causales proceden del manifiesto v2."""

    from codigo.app.executors.structuring import TIME_DOMAIN_FULL_FEATURES

    return StructuringConfig(
        window_size=2048,
        overlap=0.5,
        main_channel="channel_1",
        target_sample_rate_hz=20000,
        label_mode="binary_anomaly",
        features=list(TIME_DOMAIN_FULL_FEATURES),
    )


def _causal_v2_experiment_text(experiment_id: str) -> dict[str, str]:
    texts = {
        "pca_reconstruction_error": {
            "description": (
                "Indicador interpretable basado en error de reconstruccion PCA."
            ),
            "expected_effect": (
                "Producir una trayectoria de score estable y explicable para "
                "comparar calibracion, evolucion temporal y robustez despues "
                "de congelar la decision."
            ),
        },
        "isolation_forest": {
            "description": (
                "Score no supervisado por aislamiento como familia alternativa."
            ),
            "expected_effect": (
                "Contrastar estabilidad del score, tasa de alertas "
                "pre-monitorizacion y persistencia algoritmica sin ground truth "
                "por snapshot."
            ),
        },
        "one_class_svm": {
            "description": (
                "Frontera no lineal One-Class SVM bajo los mismos splits causales."
            ),
            "expected_effect": (
                "Evaluar estabilidad temporal, robustez y picos aislados con el "
                "umbral congelado antes de monitorizacion."
            ),
        },
    }
    return texts[experiment_id]


def cwru_window_experiment_plan_from_decision(
    decision: StructuringDecision,
    *,
    plan_id: str = DEFAULT_WINDOW_PLAN_ID,
) -> ExperimentPlan:
    """Crea un plan de ventanas a partir de alternativas propuestas por el agente."""

    candidates = [
        (
            "selected",
            decision.structuring_config,
            decision.rationale,
            "Configuracion principal elegida por el agente estructurador.",
        )
    ]
    candidates.extend(
        (
            candidate.alternative_id,
            candidate.structuring_config,
            candidate.rationale,
            candidate.expected_effect,
        )
        for candidate in decision.comparison_candidates
    )

    unique: list[tuple[str, StructuringConfig, str, str | None]] = []
    seen: set[tuple[int, float, tuple[str, ...]]] = set()
    for label, config, rationale, expected_effect in candidates:
        key = (config.window_size, config.overlap, tuple(config.features))
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, config, rationale, expected_effect))

    if len(unique) < 2:
        raise ValueError(
            "agent decision must include at least two unique structuring configurations"
        )

    default_modeling = _modeling_config_with_hyperparameters({})
    experiments = [
        ExperimentSpec(
            experiment_id=_window_experiment_id(label, config),
            run_id=f"{plan_id}_{_window_experiment_id(label, config)}",
            description=rationale,
            modeling_config=default_modeling,
            structuring_config=config,
            expected_effect=expected_effect,
        )
        for label, config, rationale, expected_effect in unique
    ]
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion agentica de configuraciones de ventana sobre CWRU. "
            "Las alternativas proceden de la decision del agente estructurador; "
            "el protocolo solo materializa y compara ejecuciones reproducibles."
        ),
        experiments=experiments,
    )


def cwru_model_experiment_plan_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str = DEFAULT_MODEL_PLAN_ID,
    structuring_config: StructuringConfig | None = None,
) -> ExperimentPlan:
    """Crea un plan de modelos a partir de alternativas propuestas por el agente."""

    experiments = _model_experiment_specs_from_decision(
        decision,
        plan_id=plan_id,
        structuring_config=structuring_config,
    )
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion agentica de modelos sobre CWRU. Las alternativas "
            "proceden de la decision del agente modelador; el protocolo solo "
            "materializa y compara configuraciones soportadas."
        ),
        experiments=experiments,
    )


def run_to_failure_model_experiment_plan_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str = DEFAULT_RUN_TO_FAILURE_PLAN_ID,
    dataset: Literal["nasa_ims_bearing"] = "nasa_ims_bearing",
    adapter_id: str = "nasa_ims_bearing",
    dataset_policy_id: str = DEFAULT_RUN_TO_FAILURE_POLICY_ID,
    structuring_config: StructuringConfig | None = None,
) -> ExperimentPlan:
    """Crea una suite run-to-failure desde la decision del modeler."""

    experiments = _model_experiment_specs_from_decision(
        decision,
        plan_id=plan_id,
        structuring_config=structuring_config,
    )
    return ExperimentPlan(
        plan_id=plan_id,
        dataset=dataset,
        adapter_id=adapter_id,
        dataset_policy_id=dataset_policy_id,
        supervision_profile="run_to_failure_degradation",
        description=(
            "Suite agentica run-to-failure derivada de la decision del modeler. "
            "El protocolo materializa la configuracion elegida y sus "
            "alternativas soportadas para comparar lead time, falsas alarmas, "
            "tendencia y persistencia."
        ),
        experiments=experiments,
    )


def run_cwru_experiment_plan(
    plan: ExperimentPlan | None = None,
    *,
    experiments_dir: Path | str = DEFAULT_EXPERIMENTS_DIR,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    raw_path: str = "codigo/data/raw/cwru_bearing/mat",
    executor_factory: ExperimentExecutorFactory | None = None,
) -> ExperimentPlanResult:
    """Ejecuta un plan CWRU completo y guarda comparacion y tabla Markdown."""

    from codigo.app.graph.state import create_initial_cwru_state
    from codigo.app.graph.pipeline import run_and_persist_cwru_pipeline

    experiment_plan = plan or default_cwru_experiment_plan()
    _validate_plain_names(experiment_plan)
    plan_dir = Path(experiments_dir) / experiment_plan.plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    plan_path = plan_dir / "experiment_plan.json"
    comparison_path = plan_dir / "comparison.json"
    table_path = plan_dir / "results_table.md"
    _write_json(plan_path, experiment_plan.model_dump(mode="json"))

    run_summaries: list[ExperimentRunSummary] = []
    for spec in experiment_plan.experiments:
        experiment_dir = plan_dir / spec.experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        state = create_initial_cwru_state(
            thread_id=f"{experiment_plan.plan_id}:{spec.experiment_id}",
            run_id=spec.run_id,
            raw_path=raw_path,
        )
        executors = (
            executor_factory(spec, experiment_dir)
            if executor_factory is not None
            else _experiment_executors(experiment_dir)
        )
        agents = _experiment_agents(spec, experiment_dir)
        persisted = run_and_persist_cwru_pipeline(
            state,
            executors=executors,
            agents=agents,
            runs_dir=runs_dir,
        )
        run_summaries.append(
            ExperimentRunSummary(
                experiment_id=spec.experiment_id,
                run_id=spec.run_id,
                snapshot=persisted.snapshot,
            )
        )

    comparison = compare_runs(
        [spec.run_id for spec in experiment_plan.experiments],
        runs_dir=runs_dir,
    )
    _write_json(comparison_path, comparison.model_dump(mode="json"))
    table_path.write_text(
        _results_table_markdown(experiment_plan, comparison),
        encoding="utf-8",
    )

    return ExperimentPlanResult(
        plan_id=experiment_plan.plan_id,
        plan_path=str(plan_path),
        comparison_path=str(comparison_path),
        results_table_path=str(table_path),
        generated_at=datetime.now(UTC),
        runs=run_summaries,
        comparison=comparison,
    )


def run_run_to_failure_experiment_plan(
    plan: ExperimentPlan | None = None,
    *,
    raw_path: str,
    experiments_dir: Path | str = DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    memory_config: "PipelineMemoryConfig | None" = None,
    agents: "PipelineAgents | None" = None,
    use_llm: bool = False,
    run_factory: RunToFailureExperimentRunner | None = None,
    comparison_factory: RunComparisonFactory | None = None,
) -> ExperimentPlanResult:
    """Ejecuta una suite run-to-failure usando el runner comun multi-dataset."""

    experiment_plan = plan or default_run_to_failure_model_suite_plan()
    if experiment_plan.dataset != "nasa_ims_bearing":
        raise ValueError("run-to-failure experiment plan must use nasa_ims_bearing")
    _validate_plain_names(experiment_plan)
    plan_dir = Path(experiments_dir) / experiment_plan.plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    plan_path = plan_dir / "experiment_plan.json"
    comparison_path = plan_dir / "comparison.json"
    table_path = plan_dir / "results_table.md"
    _write_json(plan_path, experiment_plan.model_dump(mode="json"))

    run_summaries: list[ExperimentRunSummary] = []
    for spec in experiment_plan.experiments:
        experiment_dir = plan_dir / spec.experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        persisted = (
            run_factory(spec, experiment_dir)
            if run_factory is not None
            else _run_run_to_failure_experiment_spec(
                spec,
                experiment_plan,
                raw_path=raw_path,
                runs_dir=runs_dir,
                memory_config=memory_config,
                agents=agents,
                use_llm=use_llm,
            )
        )
        run_summaries.append(
            ExperimentRunSummary(
                experiment_id=spec.experiment_id,
                run_id=spec.run_id,
                snapshot=persisted.snapshot,
            )
        )

    compare = comparison_factory or compare_runs
    comparison = compare(
        [spec.run_id for spec in experiment_plan.experiments],
        runs_dir,
    )
    comparison = _comparison_for_experiment_plan(experiment_plan, comparison)
    _write_json(
        comparison_path,
        comparison.model_dump(
            mode="json",
            exclude_none=(
                experiment_plan.dataset_policy_id
                == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
            ),
        ),
    )
    table_path.write_text(
        _results_table_markdown(experiment_plan, comparison),
        encoding="utf-8",
    )

    return ExperimentPlanResult(
        plan_id=experiment_plan.plan_id,
        plan_path=str(plan_path),
        comparison_path=str(comparison_path),
        results_table_path=str(table_path),
        generated_at=datetime.now(UTC),
        runs=run_summaries,
        comparison=comparison,
    )


def _comparison_for_experiment_plan(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> RunComparison:
    """Proyecta la comparacion v2 sobre evidencia causalmente defendible."""

    if plan.dataset_policy_id != NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return comparison
    unavailable_fields = {
        "precision": None,
        "recall": None,
        "f1_score": None,
        "false_positive_rate": None,
        "degradation_detected_before_failure_rate": None,
        "degradation_confirmed_degradation_before_failure_rate": None,
        "degradation_mean_lead_time_to_failure": None,
        "degradation_mean_persistent_lead_time_to_failure": None,
        "degradation_missed_runs": None,
        "degradation_missed_confirmed_degradation_runs": None,
    }
    return comparison.model_copy(
        update={
            "rows": [
                row.model_copy(update=unavailable_fields, deep=True)
                for row in comparison.rows
            ],
            "metrics": [],
            "degradation_metrics": [
                metric
                for metric in comparison.degradation_metrics
                if metric.metric in RUN_TO_FAILURE_CAUSAL_V2_REPORTED_METRICS
            ],
        },
        deep=True,
    )


def _experiment_executors(experiment_dir: Path) -> "PipelineExecutors":
    from codigo.app.executors.evaluation import generate_evaluation_report
    from codigo.app.executors.modeling import generate_model_outputs
    from codigo.app.executors.reporting import generate_technical_report
    from codigo.app.executors.structuring import generate_temporal_structure
    from codigo.app.graph.pipeline import PipelineExecutors

    tensor_dir = experiment_dir / "tensors"
    model_dir = experiment_dir / "models"
    evaluation_dir = experiment_dir / "evaluation"

    def structuring(clean_dir: str, config: StructuringConfig):
        return generate_temporal_structure(
            clean_dir=clean_dir,
            output_dir=tensor_dir,
            config=config,
        )

    def modeling(features_path: str, config: ModelingConfig):
        return generate_model_outputs(
            features_path=features_path,
            output_dir=model_dir,
            config=config,
        )

    def evaluation(predictions_path: str):
        return generate_evaluation_report(
            predictions_path=predictions_path,
            output_dir=evaluation_dir,
        )

    return PipelineExecutors(
        structuring=structuring,
        modeling=modeling,
        evaluation=evaluation,
        reporting=generate_technical_report,
    )


def _experiment_agents(
    spec: ExperimentSpec,
    experiment_dir: Path,
) -> "PipelineAgents":
    from codigo.app.agents.cleaner import decide_cleaning_action_deterministic
    from codigo.app.agents.evaluator import decide_evaluation_action_deterministic
    from codigo.app.agents.structurer import decide_structuring_action_deterministic
    from codigo.app.agents.supervisor import decide_supervisor_action_deterministic
    from codigo.app.graph.pipeline import PipelineAgents

    model_path = experiment_dir / "models" / _model_filename(spec.modeling_config.model_name)
    tensor_dir = experiment_dir / "tensors"
    report_path = experiment_dir / "final_report.md"

    def structurer(state: TFMStateModel) -> StructuringDecision:
        if spec.structuring_config is None:
            return decide_structuring_action_deterministic(state)
        return StructuringDecision(
            decision_id=(
                f"{state.run_id}:structurer:"
                f"{_agent_turn(state, 'structurer'):03d}"
            ),
            rationale=(
                "Agentic experiment protocol is materializing a "
                "StructuringConfig proposed by the structurer decision."
            ),
            confidence=1.0,
            hypothesis=_protocol_structuring_hypothesis(state, spec),
            generation_trace=DecisionGenerationTrace.for_decision(
                (
                    f"{state.run_id}:structurer:"
                    f"{_agent_turn(state, 'structurer'):03d}"
                ),
                origin="protocol_restricted",
            ),
            structuring_config=spec.structuring_config,
            expected_features_path=str(tensor_dir / "windows_features.csv"),
            expected_tensors_path=str(tensor_dir / "windows_raw.npz"),
            expected_splits_path=str(tensor_dir / "splits.json"),
        )

    def modeler(state: TFMStateModel) -> ModelingDecision:
        return ModelingDecision(
            decision_id=f"{state.run_id}:modeler:{_agent_turn(state, 'modeler'):03d}",
            rationale=(
                "Experiment protocol selected this ModelingConfig from a "
                "predefined local plan; the executor remains deterministic."
            ),
            confidence=1.0,
            hypothesis=_protocol_modeling_hypothesis(
                state,
                spec,
                dataset_policy_id=None,
            ),
            generation_trace=DecisionGenerationTrace.for_decision(
                f"{state.run_id}:modeler:{_agent_turn(state, 'modeler'):03d}",
                origin="protocol_restricted",
            ),
            modeling_config=spec.modeling_config,
            train_split="train",
            validation_split="validation",
            expected_model_path=str(model_path),
        )

    def report_writer(state: TFMStateModel) -> ReportDecision:
        metrics_path = None if state.metrics is None else state.metrics.metrics_path
        decision_id = (
            f"{state.run_id}:report_writer:"
            f"{_agent_turn(state, 'report_writer'):03d}"
        )
        return ReportDecision(
            decision_id=decision_id,
            rationale=(
                "Experiment protocol writes each final report inside the "
                "experiment directory to avoid overwriting comparable runs."
            ),
            confidence=1.0,
            hypothesis=_protocol_report_hypothesis(state, spec),
            generation_trace=DecisionGenerationTrace.for_decision(
                decision_id,
                origin="protocol_restricted",
            ),
            output_path=str(report_path),
            output_format="markdown",
            sections=[
                ReportSection(title="Resumen ejecutivo"),
                ReportSection(
                    title="Contexto y datos",
                    source_paths=[
                        path for path in [state.manifest_path, state.profile_path] if path
                    ],
                ),
                ReportSection(title="Configuraciones del pipeline"),
                ReportSection(
                    title="Metricas y evaluacion",
                    include_metrics=True,
                    source_paths=[path for path in [metrics_path] if path],
                ),
                ReportSection(
                    title="Artefactos generados",
                    include_artifacts=True,
                    source_paths=[artifact.path for artifact in state.artifacts],
                ),
                ReportSection(title="Limitaciones y siguientes pasos"),
            ],
        )

    return PipelineAgents(
        supervisor=decide_supervisor_action_deterministic,
        cleaner=decide_cleaning_action_deterministic,
        structurer=structurer,
        modeler=modeler,
        evaluator=decide_evaluation_action_deterministic,
        report_writer=report_writer,
    )


def _run_run_to_failure_experiment_spec(
    spec: ExperimentSpec,
    plan: ExperimentPlan,
    *,
    raw_path: str,
    runs_dir: Path | str,
    memory_config: "PipelineMemoryConfig | None",
    agents: "PipelineAgents | None",
    use_llm: bool,
) -> PersistedPipelineRun:
    from codigo.app.schemas.pipeline_run import PipelineRunRequest
    from codigo.app.services.llm_agents import build_ollama_pipeline_agents
    from codigo.app.services.pipeline_runner import run_dataset_pipeline

    request = PipelineRunRequest(
        run_id=spec.run_id,
        dataset_id=plan.dataset,
        raw_path=raw_path,
        adapter_id=plan.adapter_id or plan.dataset,
        dataset_policy_id=plan.dataset_policy_id,
        use_memory=memory_config is not None,
        use_llm=use_llm,
    )
    configured_agents = agents
    if configured_agents is None and use_llm:
        configured_agents = build_ollama_pipeline_agents()
    return run_dataset_pipeline(
        request,
        agents=_run_to_failure_experiment_agents(
            spec,
            base_agents=configured_agents,
            dataset_policy_id=plan.dataset_policy_id,
        ),
        runs_dir=runs_dir,
        memory_config=memory_config,
    )


def _protocol_report_hypothesis(
    state: TFMStateModel,
    spec: ExperimentSpec,
) -> AgentHypothesis:
    return AgentHypothesis(
        kind="report_grounding",
        statement=(
            "El informe del experimento describira configuracion, metricas y "
            "limitaciones sin confundir una variante protocolizada con una eleccion libre."
        ),
        scope=(
            f"Experimento {spec.experiment_id}; informe tecnico de la run {state.run_id}."
        ),
        evidence_cutoff="Estado, metricas y artefactos cerrados al terminar el experimento.",
        expected_observation=(
            "El verificador puede enlazar las afirmaciones principales con artefactos "
            "y reconoce explicitamente las restricciones del protocolo."
        ),
        falsification_criterion=(
            "El informe atribuye al agente la configuracion fijada, omite limitaciones "
            "o contiene una afirmacion material sin evidencia."
        ),
        evidence_refs=["protocol:experiment_plan", "artifacts:run", "metrics:final"],
        risk_notes=[
            "Una comparacion controlada no equivale a validacion industrial externa."
        ],
        assumptions=["El verificador posterior conserva una evaluacion independiente."],
    )


def _protocol_structuring_hypothesis(
    state: TFMStateModel,
    spec: ExperimentSpec,
) -> AgentHypothesis:
    config = spec.structuring_config
    window = "no fijada" if config is None else str(config.window_size)
    overlap = "no fijado" if config is None else str(config.overlap)
    return AgentHypothesis(
        kind="temporal_representation",
        statement=(
            f"La representacion protocolizada con ventana {window} y solape "
            f"{overlap} mantendra splits temporales comparables sin fuga."
        ),
        scope=(
            f"Experimento {spec.experiment_id}; dataset {state.project_context.dataset}; "
            "configuracion fijada por protocolo, no seleccionada por el agente."
        ),
        evidence_cutoff="Artefacto limpio y politica experimental antes de estructurar.",
        expected_observation=(
            "El ejecutor produce ventanas finitas y splits reproducibles sin cruzar "
            "fronteras causales, permitiendo comparar las variantes del plan."
        ),
        falsification_criterion=(
            "Falla la integridad de splits, hay fuga temporal, ventanas insuficientes "
            "o las variantes dejan de ser comparables."
        ),
        evidence_refs=["protocol:experiment_plan", "artifact:clean_summary"],
        risk_notes=[
            "La comparabilidad controlada no implica que la ventana fijada sea la optima."
        ],
        assumptions=[
            "La hipotesis efectiva del protocolo se distingue de la propuesta del LLM."
        ],
    )


def _protocol_modeling_hypothesis(
    state: TFMStateModel,
    spec: ExperimentSpec,
    *,
    dataset_policy_id: str | None,
) -> AgentHypothesis:
    online_blind = dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
    return AgentHypothesis(
        kind="model_performance",
        statement=(
            f"La familia {spec.modeling_config.model_name!r} producira un indicador "
            "temporal comparable bajo la configuracion fijada por el plan."
        ),
        scope=(
            f"Experimento {spec.experiment_id}; dataset {state.project_context.dataset}; "
            "familia fijada por protocolo, no seleccionada por el agente."
        ),
        evidence_cutoff=(
            "Baseline train y calibration validation; monitoring permanece oculto."
            if online_blind
            else "Features y splits cerrados antes de ejecutar la variante."
        ),
        expected_observation=(
            "La variante genera un score evaluable con falsas alarmas nominales y "
            "persistencia comparables frente a las demas familias."
        ),
        falsification_criterion=(
            "El score es inestable, no produce evidencia temporal util, incumple "
            "guardarrailes o queda dominado bajo el mismo protocolo."
        ),
        evidence_refs=["protocol:experiment_plan", "artifact:features"],
        risk_notes=[
            "El protocolo evalua una familia; no demuestra que el agente la hubiera elegido."
        ],
        assumptions=[
            "La hipotesis efectiva del protocolo se distingue de la propuesta del LLM."
        ],
    )


def _run_to_failure_experiment_agents(
    spec: ExperimentSpec,
    *,
    base_agents: "PipelineAgents | None" = None,
    dataset_policy_id: str | None = DEFAULT_RUN_TO_FAILURE_POLICY_ID,
) -> "PipelineAgents":
    from codigo.app.graph.pipeline import PipelineAgents
    from codigo.app.services.agent_memory import call_agent_with_optional_memory

    base = base_agents or PipelineAgents()

    def structurer(
        state: TFMStateModel,
        *,
        memory_context=None,
    ) -> StructuringDecision:
        if spec.structuring_config is None:
            return call_agent_with_optional_memory(
                base.structurer,
                state,
                memory_context,
            )
        agent_decision = call_agent_with_optional_memory(
            base.structurer,
            state,
            memory_context,
        )
        agent_proposal = StructuringDecisionProposal.model_validate(
            agent_decision.model_dump(exclude={"protocol_trace"})
        )
        overridden_fields = [
            "decision_id",
            "rationale",
            "confidence",
            "hypothesis",
            "generation_trace",
            "structuring_config",
            "expected_features_path",
            "expected_tensors_path",
            "expected_splits_path",
        ]
        if agent_decision.memory_context_id is not None:
            overridden_fields.append("memory_context_id")
        if agent_decision.used_memory_context:
            overridden_fields.append("used_memory_context")
        if agent_decision.memory_record_ids:
            overridden_fields.append("memory_record_ids")
        if agent_decision.memory_usage_summary is not None:
            overridden_fields.append("memory_usage_summary")
        if agent_decision.memory_record_uses:
            overridden_fields.append("memory_record_uses")
        effective_decision_id = (
            f"{state.run_id}:structurer:"
            f"{_agent_turn(state, 'structurer'):03d}"
        )
        proposal_attempt_index = (
            1
            if agent_decision.generation_trace is None
            else agent_decision.generation_trace.attempt_index
        )
        return StructuringDecision(
            decision_id=effective_decision_id,
            rationale=(
                "Run-to-failure experiment protocol executes the fixed "
                "StructuringConfig required by this comparable suite. The "
                "agent proposal is retained separately in protocol_trace."
            ),
            confidence=1.0,
            hypothesis=_protocol_structuring_hypothesis(state, spec),
            generation_trace=DecisionGenerationTrace.for_decision(
                effective_decision_id,
                origin="protocol_restricted",
                attempt_index=proposal_attempt_index + 1,
            ),
            structuring_config=spec.structuring_config,
            expected_features_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/windows_features.csv"
            ),
            expected_tensors_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/windows_raw.npz"
            ),
            expected_splits_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/splits.json"
            ),
            protocol_trace=StructuringProtocolTrace(
                agent_proposal=agent_proposal,
                overridden_fields=overridden_fields,
                restriction_reason=(
                    "The suite fixes temporal structuring so model variants "
                    "remain comparable; the observed agent proposal is not "
                    "used to configure this execution."
                ),
                proposal_influenced_by_memory=(
                    agent_decision.used_memory_context
                ),
                execution_influenced_by_memory=False,
            ),
        )

    def modeler(
        state: TFMStateModel,
        *,
        memory_context=None,
    ) -> ModelingDecision:
        agent_decision = call_agent_with_optional_memory(
            base.modeler,
            state,
            memory_context,
        )
        protocol_strategy = _run_to_failure_experiment_strategy(
            spec,
            dataset_policy_id=dataset_policy_id,
        )
        agent_proposal = ModelingDecisionProposal.model_validate(
            agent_decision.model_dump(exclude={"protocol_trace"})
        )
        overridden_fields = [
            "decision_id",
            "rationale",
            "confidence",
            "hypothesis",
            "generation_trace",
            "decision_strategy",
            "modeling_config",
            "train_split",
            "validation_split",
            "expected_model_path",
        ]
        if agent_decision.comparison_candidates:
            overridden_fields.append("comparison_candidates")
        if agent_decision.memory_context_id is not None:
            overridden_fields.append("memory_context_id")
        if agent_decision.used_memory_context:
            overridden_fields.append("used_memory_context")
        if agent_decision.memory_record_ids:
            overridden_fields.append("memory_record_ids")
        if agent_decision.memory_usage_summary is not None:
            overridden_fields.append("memory_usage_summary")
        if agent_decision.memory_record_uses:
            overridden_fields.append("memory_record_uses")
        effective_decision_id = (
            f"{state.run_id}:modeler:{_agent_turn(state, 'modeler'):03d}"
        )
        proposal_attempt_index = (
            1
            if agent_decision.generation_trace is None
            else agent_decision.generation_trace.attempt_index
        )
        return ModelingDecision(
            decision_id=effective_decision_id,
            rationale=(
                "Run-to-failure experiment protocol executes the model family "
                "fixed by the canonical suite. The agent proposal is retained "
                "separately in protocol_trace and does not select this "
                "execution's configuration."
            ),
            confidence=1.0,
            hypothesis=_protocol_modeling_hypothesis(
                state,
                spec,
                dataset_policy_id=dataset_policy_id,
            ),
            generation_trace=DecisionGenerationTrace.for_decision(
                effective_decision_id,
                origin="protocol_restricted",
                attempt_index=proposal_attempt_index + 1,
            ),
            decision_strategy=protocol_strategy,
            modeling_config=spec.modeling_config,
            train_split="train",
            validation_split="validation",
            expected_model_path=(
                f"codigo/models/{state.project_context.dataset}/{state.run_id}/"
                f"{_model_filename(spec.modeling_config.model_name)}"
            ),
            protocol_trace=ModelingProtocolTrace(
                agent_proposal=agent_proposal,
                overridden_fields=overridden_fields,
                restriction_reason=(
                    "The canonical suite fixes the model family and its "
                    "configuration to permit controlled cross-model "
                    "comparison; the observed agent proposal is not used to "
                    "configure this execution."
                ),
                proposal_influenced_by_memory=(
                    agent_decision.used_memory_context
                ),
                execution_influenced_by_memory=False,
            ),
        )

    return PipelineAgents(
        supervisor=base.supervisor,
        cleaner=base.cleaner,
        structurer=structurer if spec.structuring_config is not None else base.structurer,
        modeler=modeler,
        evaluator=base.evaluator,
        report_writer=base.report_writer,
        report_reviser=base.report_reviser,
        report_verifier=base.report_verifier,
    )


def _run_to_failure_experiment_strategy(
    spec: ExperimentSpec,
    *,
    dataset_policy_id: str | None = DEFAULT_RUN_TO_FAILURE_POLICY_ID,
) -> ModelingDecisionStrategy:
    if dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return ModelingDecisionStrategy(
            strategy_type="feature_model_fit",
            hypothesis=(
                f"Comparar {spec.modeling_config.model_name} como indicador "
                "temporal bajo el protocolo causal v2, usando solo baseline "
                "para ajuste y calibracion previa para fijar el umbral."
            ),
            evidence_refs=[
                "policy:nasa_ims_run_to_failure_v2",
                "partition:baseline_train",
                "partition:calibration",
                "constraint:monitoring_held_out",
                "label_source:none:monitoring",
            ],
            risk_notes=[
                "El tramo de monitorizacion permanece ciego durante la decision del modelador.",
                "No hay etiquetas binarias oficiales por ventana ni evidencia futura disponible.",
                "El readiness causal avanzado aun no permite autoencoder_dense.",
            ],
            tool_names=[],
            optimization_targets=[
                "calibration_threshold_stability",
                "nominal_false_alarm_rate",
                "temporal_score_stability",
            ],
            alert_policy=(
                "Fijar el umbral exclusivamente con calibracion previa y "
                "congelarlo antes de observar el tramo de monitorizacion."
            ),
        )
    return ModelingDecisionStrategy(
        strategy_type="feature_model_fit",
        hypothesis=(
            f"Comparar {spec.modeling_config.model_name} como score temporal "
            "run-to-failure frente a las demas familias de la suite canonica."
        ),
        evidence_refs=[
            "tool:temporal_health_lookup",
            "tool:degradation_metrics_lookup",
            "temporal:run_to_failure_profile",
            "temporal:first_persistent_alert",
            "temporal:longest_alert_streak",
            "metric:mean_lead_time_to_failure",
            "metric:mean_false_alarm_rate_nominal",
            "metric:mean_score_trend_spearman",
            "label_source:temporal_proxy",
        ],
        risk_notes=[
            "La suite materializa modelos comparables; no convierte etiquetas proxy en oficiales.",
            "La aprobacion depende de metricas temporales y guardarrails del evaluador.",
        ],
        tool_names=[
            "temporal_health_lookup",
            "degradation_metrics_lookup",
        ],
        optimization_targets=[
            "detected_before_failure_rate",
            "mean_lead_time_to_failure",
            "mean_false_alarm_rate_nominal",
            "mean_score_trend_spearman",
        ],
        alert_policy=(
            "Comparar pico aislado, aviso sostenido, falsas alarmas nominales "
            "y tendencia antes de aprobar cualquier familia de modelo."
        ),
    )


def _model_experiment_specs_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str,
    structuring_config: StructuringConfig | None,
) -> list[ExperimentSpec]:
    candidates = [
        (
            "selected",
            decision.modeling_config,
            decision.rationale,
            "Configuracion principal elegida por el agente modelador.",
        )
    ]
    candidates.extend(
        (
            candidate.alternative_id,
            candidate.modeling_config,
            candidate.rationale,
            candidate.expected_effect,
        )
        for candidate in decision.comparison_candidates
    )

    unique: list[tuple[str, ModelingConfig, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for label, config, rationale, expected_effect in candidates:
        key = (
            config.model_name,
            json.dumps(config.hyperparameters, sort_keys=True),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, config, rationale, expected_effect))

    if len(unique) < 2:
        raise ValueError(
            "agent decision must include at least two unique modeling configurations"
        )

    return [
        ExperimentSpec(
            experiment_id=_model_experiment_id(label, config),
            run_id=f"{plan_id}_{_model_experiment_id(label, config)}",
            description=rationale,
            modeling_config=config,
            structuring_config=structuring_config,
            expected_effect=expected_effect,
        )
        for label, config, rationale, expected_effect in unique
    ]


def _modeling_config_with_hyperparameters(
    updates: dict[str, int | float | str | bool | None],
) -> ModelingConfig:
    from codigo.app.executors.modeling import DEFAULT_MODELING_CONFIG

    payload = DEFAULT_MODELING_CONFIG.model_dump(mode="json")
    hyperparameters = dict(payload["hyperparameters"])
    hyperparameters.update(updates)
    return ModelingConfig(
        model_name=payload["model_name"],
        random_state=payload["random_state"],
        hyperparameters=hyperparameters,
    )


def _copy_modeling_config(config: ModelingConfig) -> ModelingConfig:
    return ModelingConfig.model_validate(config.model_dump(mode="json"))


def _results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
    if plan.dataset == "nasa_ims_bearing" or comparison.degradation_metrics:
        return _run_to_failure_results_table_markdown(plan, comparison)

    specs_by_run_id = {spec.run_id: spec for spec in plan.experiments}
    lines = [
        f"# Resultados experimentales: {plan.plan_id}",
        "",
        plan.description,
        "",
        "| Experimento | Run ID | window_size | overlap | model_name | threshold_quantile | n_estimators | Aprobado | Precision | Recall | F1 | FPR |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison.rows:
        spec = specs_by_run_id[row.run_id]
        hyperparameters = spec.modeling_config.hyperparameters
        structuring = spec.structuring_config
        lines.append(
            " | ".join(
                [
                    f"| {spec.experiment_id}",
                    f"`{row.run_id}`",
                    _metric_text(None if structuring is None else structuring.window_size),
                    _metric_text(None if structuring is None else structuring.overlap),
                    spec.modeling_config.model_name,
                    _metric_text(hyperparameters.get("threshold_quantile")),
                    _metric_text(hyperparameters.get("n_estimators")),
                    _approval_text(row.approved),
                    _metric_text(row.precision),
                    _metric_text(row.recall),
                    _metric_text(row.f1_score),
                    f"{_metric_text(row.false_positive_rate)} |",
                ]
            )
        )
    lines.extend(["", "## Mejor ejecucion por metrica", ""])
    for metric in comparison.metrics:
        direction = "mayor es mejor" if metric.higher_is_better else "menor es mejor"
        lines.append(
            "- "
            f"{metric.metric}: `{metric.best_run_id}` "
            f"({_metric_text(metric.best_value)}, {direction})"
        )
    return "\n".join(lines).rstrip() + "\n"


def _run_to_failure_results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
    if plan.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return _causal_v2_results_table_markdown(plan, comparison)

    specs_by_run_id = {spec.run_id: spec for spec in plan.experiments}
    lines = [
        f"# Resultados experimentales: {plan.plan_id}",
        "",
        plan.description,
        "",
        "| Experimento | Run ID | modelo | threshold_quantile | Aprobado | Onset confirmado | Lead persistente | FAR nominal | Tendencia | HI drop | HI mono | Onsets perdidos | F1 aux | FPR aux |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison.rows:
        spec = specs_by_run_id[row.run_id]
        hyperparameters = spec.modeling_config.hyperparameters
        lines.append(
            " | ".join(
                [
                    f"| {spec.experiment_id}",
                    f"`{row.run_id}`",
                    spec.modeling_config.model_name,
                    _metric_text(hyperparameters.get("threshold_quantile")),
                    _approval_text(row.approved),
                    _metric_text(
                        row.degradation_confirmed_degradation_before_failure_rate
                    ),
                    _metric_text(
                        row.degradation_mean_persistent_lead_time_to_failure
                    ),
                    _metric_text(row.degradation_mean_false_alarm_rate_nominal),
                    _metric_text(row.degradation_mean_score_trend_spearman),
                    _metric_text(row.degradation_mean_health_index_drop),
                    _metric_text(row.degradation_mean_health_monotonicity),
                    _metric_text(row.degradation_missed_confirmed_degradation_runs),
                    _metric_text(row.f1_score),
                    f"{_metric_text(row.false_positive_rate)} |",
                ]
            )
        )
    lines.extend(["", "## Mejor ejecucion por metrica temporal", ""])
    metric_rows = comparison.degradation_metrics or comparison.metrics
    for metric in metric_rows:
        direction = "mayor es mejor" if metric.higher_is_better else "menor es mejor"
        lines.append(
            "- "
            f"{metric.metric}: `{metric.best_run_id}` "
            f"({_metric_text(metric.best_value)}, {direction})"
        )
    lines.extend(
        [
            "",
            "## Nota metodologica",
            "",
            "Las metricas binarias se muestran como auxiliares/proxy. La lectura "
            "principal del perfil run-to-failure usa onset confirmado antes de "
            "fallo, lead time persistente, falsas alarmas nominales, tendencia "
            "score/Health Indicator, monotonicidad y onsets perdidos.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _causal_v2_results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
    """Renderiza v2 sin presentar etiquetas binarias ni futuro como evidencia."""

    specs_by_run_id = {spec.run_id: spec for spec in plan.experiments}
    lines = [
        f"# Resultados experimentales: {plan.plan_id}",
        "",
        plan.description,
        "",
        "| Experimento | Run ID | modelo | threshold_quantile | Controles internos | Alerta persistente | Intervalo al fin registrado (s) | Tasa alerta premonitorizacion | Tendencia | HI drop | HI mono | HI robustez |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison.rows:
        spec = specs_by_run_id[row.run_id]
        hyperparameters = spec.modeling_config.hyperparameters
        lines.append(
            " | ".join(
                [
                    f"| {spec.experiment_id}",
                    f"`{row.run_id}`",
                    spec.modeling_config.model_name,
                    _metric_text(hyperparameters.get("threshold_quantile")),
                    _approval_text(row.approved),
                    _metric_text(row.degradation_persistent_alert_run_rate),
                    _metric_text(
                        row.degradation_mean_first_persistent_alert_time_to_trajectory_end
                    ),
                    _metric_text(row.degradation_mean_pre_monitoring_alert_rate),
                    _metric_text(row.degradation_mean_score_trend_spearman),
                    _metric_text(row.degradation_mean_health_index_drop),
                    _metric_text(row.degradation_mean_health_monotonicity),
                    f"{_metric_text(row.degradation_mean_health_robustness)} |",
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Referencia orientada por metrica causal disponible",
            "",
        ]
    )
    for metric in comparison.degradation_metrics:
        if metric.metric not in RUN_TO_FAILURE_CAUSAL_V2_REPORTED_METRICS:
            continue
        direction = (
            "orientacion descriptiva mayor"
            if metric.higher_is_better
            else "orientacion descriptiva menor"
        )
        lines.append(
            "- "
            f"{metric.metric}: `{metric.best_run_id}` "
            f"({_metric_text(metric.best_value)}, {direction})"
        )
    lines.extend(
        [
            "",
            "## Nota metodologica",
            "",
            "La tabla v2 omite deliberadamente precision, recall, F1 y FPR "
            "binaria: el conjunto oficial no aporta etiquetas binarias por "
            "ventana. El modelador fija su configuracion con baseline y "
            "calibracion; la monitorizacion se consulta solo despues de "
            "congelar la decision. `Controles internos` no equivale a "
            "validacion fisica, diagnostico ni aprobacion industrial.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _validate_plain_names(plan: ExperimentPlan) -> None:
    _ensure_plain_name("plan_id", plan.plan_id)
    seen_experiment_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    for spec in plan.experiments:
        _ensure_plain_name("experiment_id", spec.experiment_id)
        _ensure_plain_name("run_id", spec.run_id)
        if spec.experiment_id in seen_experiment_ids:
            raise ValueError(f"duplicated experiment_id: {spec.experiment_id}")
        if spec.run_id in seen_run_ids:
            raise ValueError(f"duplicated run_id: {spec.run_id}")
        seen_experiment_ids.add(spec.experiment_id)
        seen_run_ids.add(spec.run_id)


def _ensure_plain_name(field_name: str, value: str) -> None:
    path = Path(value)
    if path.name != value or path.is_absolute():
        raise ValueError(f"{field_name} must be a plain directory name")


def _window_experiment_id(label: str, config: StructuringConfig) -> str:
    return (
        f"win_{config.window_size}_ov_{int(config.overlap * 100):02d}_"
        f"{_plain_token(label)}"
    )


def _model_experiment_id(label: str, config: ModelingConfig) -> str:
    suffix = _plain_token(label)
    if config.model_name == "isolation_forest":
        threshold = config.hyperparameters.get("threshold_quantile", "auto")
        return f"iforest_thr_{_plain_token(str(threshold))}_{suffix}"
    if config.model_name == "pca_reconstruction_error":
        components = config.hyperparameters.get("n_components", "auto")
        return f"pca_nc_{_plain_token(str(components))}_{suffix}"
    return f"{_plain_token(config.model_name)}_{suffix}"


def _model_filename(model_name: str) -> str:
    suffix = "pt" if model_name == "autoencoder_dense" else "joblib"
    return f"{model_name}.{suffix}"


def _plain_token(value: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value
    )
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return collapsed or "candidate"


def _agent_turn(state: TFMStateModel, agent_name: str) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == agent_name
        for message in state.messages
    )


def _approval_text(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "si" if value else "no"


def _metric_text(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
