"""Renderizado reproducible de figuras desde artefactos canonicos validados.

Este modulo no recalcula metricas del TFM. Su unica responsabilidad es
clasificar los registros ya presentes en el informe canonico de indexacion y
materializar una figura vectorial junto con su manifiesto de procedencia.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
from pydantic import Field, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.services.agent_reliability import (
    AgentReliabilityEntrypoint,
    AgentReliabilityObservation,
    AgentReliabilityOutcome,
    AgentReliabilitySummary,
)
from codigo.app.schemas.agent_decisions import AgentName
from codigo.app.schemas.monitoring_replay import MONITORING_REVIEW_ROLES
from codigo.app.services.monitoring_review_reliability import (
    DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
    MonitoringReviewReliabilityOutcome,
    MonitoringReviewReliabilityResult,
    MonitoringReviewReliabilityVerdict,
    load_published_monitoring_review_reliability,
)
from codigo.app.services.reasoning_memory_index import ReasoningMemoryIndexResult


DEFAULT_MEMORY_INDEX_REPORT = Path(
    "codigo/reports/reasoning_memory/reasoning_memory_index_report.json"
)
DEFAULT_VALIDATION_FIGURES_DIR = Path("codigo/reports/validation_figures")
DEFAULT_MEMORY_CORPUS_FIGURE_NAME = "memory_corpus_governance"
DEFAULT_RUN_TRAJECTORY_FIGURE_NAME = "nasa_ims_official_set2_v2_pca_trajectory"
DEFAULT_AGENT_RELIABILITY_FIGURE_NAME = "agent_decision_reliability"
DEFAULT_MONITORING_REVIEW_RELIABILITY_FIGURE_NAME = (
    "monitoring_review_reliability_gate"
)
DEFAULT_OFFICIAL_RUN_TRAJECTORY = Path(
    "codigo/reports/nasa_ims_bearing/"
    "nasa-ims-official-set2-v2-pca-002/evaluation/snapshot_trajectory.csv"
)
DEFAULT_OFFICIAL_RUN_METRICS = Path(
    "codigo/reports/nasa_ims_bearing/"
    "nasa-ims-official-set2-v2-pca-002/evaluation/metrics.json"
)

MemoryCorpusCategoryId = Literal[
    "reviewed_reusable",
    "quarantined_candidates",
    "non_retrievable_audits",
]

CATEGORY_ORDER: tuple[MemoryCorpusCategoryId, ...] = (
    "reviewed_reusable",
    "quarantined_candidates",
    "non_retrievable_audits",
)

CATEGORY_LABELS: dict[MemoryCorpusCategoryId, str] = {
    "reviewed_reusable": "Revisados y reutilizables",
    "quarantined_candidates": "Candidatos en cuarentena",
    "non_retrievable_audits": "Auditorías no recuperables",
}

CATEGORY_COLORS: dict[MemoryCorpusCategoryId, str] = {
    "reviewed_reusable": "#2A9D8F",
    "quarantined_candidates": "#E9A23B",
    "non_retrievable_audits": "#577590",
}

ValidationFigureInputRole = Literal[
    "snapshot_trajectory",
    "evaluation_metrics",
]
TemporalPartitionId = Literal[
    "baseline_train",
    "calibration",
    "monitoring",
]

TEMPORAL_PARTITION_ORDER: tuple[TemporalPartitionId, ...] = (
    "baseline_train",
    "calibration",
    "monitoring",
)
TEMPORAL_PARTITION_LABELS: dict[TemporalPartitionId, str] = {
    "baseline_train": "Base",
    "calibration": "Calibración",
    "monitoring": "Monitorización",
}
TEMPORAL_PARTITION_COLORS: dict[TemporalPartitionId, str] = {
    "baseline_train": "#DCEAF5",
    "calibration": "#E9E2F3",
    "monitoring": "#F7E8D0",
}

RUN_TRAJECTORY_REQUIRED_COLUMNS = frozenset(
    {
        "run_id",
        "split",
        "label",
        "target",
        "label_source",
        "label_granularity",
        "relative_life",
        "temporal_partition",
        "threshold",
        "predicted_anomaly",
        "snapshot_id",
        "temporal_unit",
        "snapshot_aggregation_policy_id",
        "n_windows",
        "n_alerted_windows",
        "window_alert_fraction",
        "anomaly_score_median",
        "anomaly_score_p90",
        "temporal_gap_policy_id",
        "gap_detected",
        "cadence_matches_expected",
        "health_index_smoothed",
        "health_policy_id",
        "alert_policy_id",
        "health_indicator_policy_id",
    }
)

_PARTITION_CLASSIFICATION = {
    "baseline_train": {
        "split": "train",
        "label": "normal",
        "target": 0.0,
        "label_source": "temporal_proxy",
        "label_granularity": "proxy_temporal",
    },
    "calibration": {
        "split": "validation",
        "label": "unknown",
        "target": None,
        "label_source": "none",
        "label_granularity": "none",
    },
    "monitoring": {
        "split": "test",
        "label": "unknown",
        "target": None,
        "label_source": "none",
        "label_granularity": "none",
    },
}

_BINARY_METRIC_KEYS = frozenset(
    {
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
        "pr_auc",
        "confusion_matrix",
    }
)

AgentReliabilityFigureInputRole = Literal[
    "agent_reliability_summary",
    "agent_reliability_observations",
]
AgentReliabilityFigureOutputRole = Literal["vector_pdf", "web_png"]

AGENT_RELIABILITY_OUTCOME_ORDER: tuple[AgentReliabilityOutcome, ...] = (
    "first_pass",
    "llm_repaired",
    "fallback",
    "semantic_failure",
    "non_agentic",
    "error",
)
AGENT_RELIABILITY_OUTCOME_LABELS: dict[AgentReliabilityOutcome, str] = {
    "first_pass": "Primera respuesta",
    "llm_repaired": "Reparación LLM",
    "fallback": "Fallback determinista",
    "semantic_failure": "Fallo semántico",
    "non_agentic": "Ruta no agéntica",
    "error": "Error",
}
AGENT_RELIABILITY_OUTCOME_COLORS: dict[AgentReliabilityOutcome, str] = {
    "first_pass": "#2A9D8F",
    "llm_repaired": "#457B9D",
    "fallback": "#E9A23B",
    "semantic_failure": "#D1495B",
    "non_agentic": "#7B2CBF",
    "error": "#495057",
}
AGENT_RELIABILITY_ENTRYPOINT_ORDER: tuple[AgentReliabilityEntrypoint, ...] = (
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "modeler_retry",
    "evaluator",
    "report_writer",
    "report_reviser",
    "report_verifier",
)
AGENT_RELIABILITY_ENTRYPOINT_LABELS: dict[AgentReliabilityEntrypoint, str] = {
    "supervisor": "Supervisor",
    "cleaner": "Limpiador",
    "structurer": "Estructurador",
    "modeler": "Modelador",
    "modeler_retry": "Reintento de modelado",
    "evaluator": "Evaluador",
    "report_writer": "Redactor",
    "report_reviser": "Revisión del informe",
    "report_verifier": "Verificador del informe",
}

AGENT_RELIABILITY_INTERPRETATION_LIMIT = (
    "Banco cerrado decision-only: no representa una tasa universal ni "
    "confirma o refuta las hipótesis científicas de los agentes."
)

MonitoringReviewReliabilityFigureInputRole = Literal[
    "published_current",
    "published_result",
]
MonitoringReviewReliabilityCoverageId = Literal[
    "hypothesis_structure",
    "causal_grounding",
    "trace_binding",
]

MONITORING_REVIEW_OUTCOME_ORDER: tuple[
    MonitoringReviewReliabilityOutcome, ...
] = (
    "first_pass",
    "llm_repaired",
    "fallback",
    "non_agentic",
    "error",
)
MONITORING_REVIEW_OUTCOME_LABELS: dict[
    MonitoringReviewReliabilityOutcome, str
] = {
    "first_pass": "Primera respuesta",
    "llm_repaired": "Reparación contractual",
    "fallback": "Fallback",
    "non_agentic": "No agéntica",
    "error": "Error",
}
MONITORING_REVIEW_OUTCOME_SHORT_LABELS: dict[
    MonitoringReviewReliabilityOutcome, str
] = {
    "first_pass": "P",
    "llm_repaired": "R",
    "fallback": "F",
    "non_agentic": "N",
    "error": "E",
}
MONITORING_REVIEW_OUTCOME_COLORS: dict[
    MonitoringReviewReliabilityOutcome, str
] = {
    "first_pass": "#2A9D8F",
    "llm_repaired": "#457B9D",
    "fallback": "#E9A23B",
    "non_agentic": "#7B2CBF",
    "error": "#495057",
}
MONITORING_REVIEW_COVERAGE_LABELS: dict[
    MonitoringReviewReliabilityCoverageId, str
] = {
    "hypothesis_structure": "Hipótesis estructurada",
    "causal_grounding": "Evidencia causal",
    "trace_binding": "Trigger → decisión → resultado",
}
MONITORING_REVIEW_RELIABILITY_INTERPRETATION_LIMIT = (
    "Gate cerrado sobre tres replays NASA P3: evalúa trazabilidad contractual, "
    "no la verdad física de las hipótesis ni un rendimiento industrial universal."
)


class ValidationFigureCategory(StrictBaseModel):
    """Categoria disjunta incluida en una figura de validacion."""

    category_id: MemoryCorpusCategoryId
    label: str = Field(min_length=1)
    count: int = Field(ge=0)
    record_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_count(self) -> "ValidationFigureCategory":
        if self.count != len(self.record_ids):
            raise ValueError("category count must match record_ids length")
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("category record_ids cannot contain duplicates")
        return self


class ValidationFigureManifest(StrictBaseModel):
    """Manifiesto reproducible de una figura derivada de evidencia canonica."""

    schema_version: Literal["tfm.validation_figure_manifest.v1"] = (
        "tfm.validation_figure_manifest.v1"
    )
    renderer_id: Literal["memory_corpus_governance_v1"] = (
        "memory_corpus_governance_v1"
    )
    figure_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    source_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    source_size_bytes: int = Field(ge=0)
    source_record_count: int = Field(ge=0)
    classified_record_count: int = Field(ge=0)
    categories: list[ValidationFigureCategory] = Field(
        min_length=3,
        max_length=3,
    )
    output_path: str = Field(min_length=1)
    output_format: Literal["pdf"] = "pdf"
    output_media_type: Literal["application/pdf"] = "application/pdf"
    output_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_complete_classification(self) -> "ValidationFigureManifest":
        category_ids = [category.category_id for category in self.categories]
        if category_ids != list(CATEGORY_ORDER):
            raise ValueError("manifest categories must use the canonical order")
        category_total = sum(category.count for category in self.categories)
        if category_total != self.classified_record_count:
            raise ValueError("category counts must sum classified_record_count")
        if self.classified_record_count != self.source_record_count:
            raise ValueError("all source records must be classified")
        record_ids = [
            record_id
            for category in self.categories
            for record_id in category.record_ids
        ]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("records cannot appear in more than one category")
        return self


class ValidationFigureArtifacts(StrictBaseModel):
    """Artefactos escritos por el renderer de figuras de validacion."""

    pdf_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest: ValidationFigureManifest


class AgentReliabilityFigureInput(StrictBaseModel):
    """Entrada canónica ligada por hash a la figura decision-only."""

    input_role: AgentReliabilityFigureInputRole
    path: str = Field(min_length=1)
    sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    size_bytes: int = Field(ge=0)
    media_type: Literal["application/json", "application/x-ndjson"]

    @model_validator(mode="after")
    def validate_role_media_type(self) -> "AgentReliabilityFigureInput":
        expected = {
            "agent_reliability_summary": "application/json",
            "agent_reliability_observations": "application/x-ndjson",
        }[self.input_role]
        if self.media_type != expected:
            raise ValueError("agent reliability input role and media type differ")
        return self


class AgentReliabilityFigureOutput(StrictBaseModel):
    """Salida renderizada y ligada por hash al manifiesto."""

    output_role: AgentReliabilityFigureOutputRole
    path: str = Field(min_length=1)
    output_format: Literal["pdf", "png"]
    media_type: Literal["application/pdf", "image/png"]
    sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_role_format(self) -> "AgentReliabilityFigureOutput":
        expected = {
            "vector_pdf": ("pdf", "application/pdf"),
            "web_png": ("png", "image/png"),
        }[self.output_role]
        if (self.output_format, self.media_type) != expected:
            raise ValueError("agent reliability output role and format differ")
        return self


class AgentReliabilityFigureManifest(StrictBaseModel):
    """Procedencia y métricas publicadas por la figura decision-only."""

    schema_version: Literal["tfm.agent_reliability_figure_manifest.v1"] = (
        "tfm.agent_reliability_figure_manifest.v1"
    )
    renderer_id: Literal["agent_reliability_stacked_bars_v1"] = (
        "agent_reliability_stacked_bars_v1"
    )
    figure_id: str = Field(min_length=1)
    plan_dir: str = Field(min_length=1)
    benchmark_scope: Literal["closed_decision_only"] = "closed_decision_only"
    interpretation_limit: Literal[
        "Banco cerrado decision-only: no representa una tasa universal ni "
        "confirma o refuta las hipótesis científicas de los agentes."
    ] = AGENT_RELIABILITY_INTERPRETATION_LIMIT
    inputs: list[AgentReliabilityFigureInput] = Field(min_length=2, max_length=2)
    metrics: AgentReliabilitySummary
    rendered_outcomes: list[AgentReliabilityOutcome] = Field(min_length=3)
    outputs: list[AgentReliabilityFigureOutput] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_canonical_order(self) -> "AgentReliabilityFigureManifest":
        if [item.input_role for item in self.inputs] != [
            "agent_reliability_summary",
            "agent_reliability_observations",
        ]:
            raise ValueError("agent reliability inputs must use canonical order")
        if [item.output_role for item in self.outputs] != [
            "vector_pdf",
            "web_png",
        ]:
            raise ValueError("agent reliability outputs must use canonical order")
        expected_outcomes = _visible_agent_reliability_outcomes(self.metrics)
        if self.rendered_outcomes != expected_outcomes:
            raise ValueError("rendered outcomes do not match published metrics")
        return self


class AgentReliabilityFigureArtifacts(StrictBaseModel):
    """PDF, PNG web y manifiesto de la figura decision-only."""

    pdf_path: str = Field(min_length=1)
    png_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest: AgentReliabilityFigureManifest


class MonitoringReviewReliabilityFigureInput(StrictBaseModel):
    """Puntero publicado y resultado consumidos tras verificar sus hashes."""

    input_role: MonitoringReviewReliabilityFigureInputRole
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: Literal["application/json"] = "application/json"


class MonitoringReviewReliabilityRoleMetrics(StrictBaseModel):
    """Recuentos exhaustivos de un rol en los doce contextos observados."""

    agent_name: AgentName
    observation_count: int = Field(ge=0)
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    error_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_exhaustive_outcomes(
        self,
    ) -> "MonitoringReviewReliabilityRoleMetrics":
        total = (
            self.first_pass_count
            + self.repaired_count
            + self.fallback_count
            + self.non_agentic_count
            + self.error_count
        )
        if total != self.observation_count:
            raise ValueError("role outcome counts must be exhaustive")
        return self


class MonitoringReviewReliabilityMatrixCell(StrictBaseModel):
    """Una celda contexto por repetición; mantiene visibles los siete roles."""

    context_id: str = Field(min_length=1)
    context_ordinal: int = Field(ge=1, le=4)
    trigger_type: str = Field(min_length=1)
    condition_start_cursor: int = Field(ge=0)
    cutoff_cursor: int = Field(ge=0)
    repetition: int = Field(ge=1, le=3)
    observation_count: int = Field(ge=0)
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    claims_scope_failure_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_exhaustive_outcomes(
        self,
    ) -> "MonitoringReviewReliabilityMatrixCell":
        total = (
            self.first_pass_count
            + self.repaired_count
            + self.fallback_count
            + self.non_agentic_count
            + self.error_count
        )
        if total != self.observation_count:
            raise ValueError("matrix cell outcomes must be exhaustive")
        if self.claims_scope_failure_count > self.observation_count:
            raise ValueError("scope failures cannot exceed cell observations")
        return self


class MonitoringReviewReliabilityCoverage(StrictBaseModel):
    """Cobertura contractual publicada; no es una puntuación compuesta."""

    coverage_id: MonitoringReviewReliabilityCoverageId
    label: str = Field(min_length=1)
    passed_count: int = Field(ge=0)
    observation_count: int = Field(gt=0)
    rate: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_rate(self) -> "MonitoringReviewReliabilityCoverage":
        if self.passed_count > self.observation_count:
            raise ValueError("coverage count cannot exceed observations")
        if not math.isclose(
            self.rate,
            self.passed_count / self.observation_count,
            abs_tol=1e-12,
        ):
            raise ValueError("coverage rate does not match its exact count")
        return self


class MonitoringReviewReliabilityFigureMetrics(StrictBaseModel):
    """Proyección visual cerrada del resultado publicado."""

    plan_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    verdict: MonitoringReviewReliabilityVerdict
    blockers: tuple[str, ...] = ()
    observation_count: int = Field(gt=0)
    child_run_count: int = Field(gt=0)
    claims_scoped_count: int = Field(ge=0)
    claims_scoped_rate: float = Field(ge=0.0, le=1.0)
    roles: tuple[MonitoringReviewReliabilityRoleMetrics, ...]
    matrix: tuple[MonitoringReviewReliabilityMatrixCell, ...]
    coverages: tuple[MonitoringReviewReliabilityCoverage, ...]

    @model_validator(mode="after")
    def validate_closed_projection(
        self,
    ) -> "MonitoringReviewReliabilityFigureMetrics":
        if tuple(item.agent_name for item in self.roles) != MONITORING_REVIEW_ROLES:
            raise ValueError("figure roles must use the seven canonical roles")
        if len(self.matrix) != 12:
            raise ValueError("figure matrix must contain four contexts by three runs")
        expected_cells = {
            (context_ordinal, repetition)
            for context_ordinal in range(1, 5)
            for repetition in range(1, 4)
        }
        actual_cells = {
            (item.context_ordinal, item.repetition) for item in self.matrix
        }
        if actual_cells != expected_cells:
            raise ValueError("figure matrix does not cover the closed 4x3 pack")
        coverage_ids = tuple(item.coverage_id for item in self.coverages)
        if coverage_ids != (
            "hypothesis_structure",
            "causal_grounding",
            "trace_binding",
        ):
            raise ValueError("figure must expose the three canonical coverages")
        if sum(item.observation_count for item in self.roles) != self.observation_count:
            raise ValueError("role totals do not match figure observation count")
        if sum(item.observation_count for item in self.matrix) != self.observation_count:
            raise ValueError("matrix totals do not match figure observation count")
        if self.claims_scoped_count > self.observation_count or not math.isclose(
            self.claims_scoped_rate,
            self.claims_scoped_count / self.observation_count,
            abs_tol=1e-12,
        ):
            raise ValueError("claims scope rate does not match its exact count")
        if self.verdict == "passed" and self.blockers:
            raise ValueError("passed gate cannot declare blockers")
        if self.verdict == "blocked" and not self.blockers:
            raise ValueError("blocked gate must declare its blockers")
        return self


class MonitoringReviewReliabilityFigureManifest(StrictBaseModel):
    """Procedencia verificable de la figura del gate NASA P3."""

    schema_version: Literal[
        "tfm.monitoring_review_reliability_figure_manifest.v1"
    ] = "tfm.monitoring_review_reliability_figure_manifest.v1"
    renderer_id: Literal["monitoring_review_reliability_gate_v1"] = (
        "monitoring_review_reliability_gate_v1"
    )
    figure_id: str = Field(min_length=1)
    publication_root: str = Field(min_length=1)
    benchmark_scope: Literal["closed_nasa_p3_monitoring_review"] = (
        "closed_nasa_p3_monitoring_review"
    )
    interpretation_limit: Literal[
        "Gate cerrado sobre tres replays NASA P3: evalúa trazabilidad contractual, "
        "no la verdad física de las hipótesis ni un rendimiento industrial universal."
    ] = MONITORING_REVIEW_RELIABILITY_INTERPRETATION_LIMIT
    inputs: tuple[MonitoringReviewReliabilityFigureInput, ...]
    metrics: MonitoringReviewReliabilityFigureMetrics
    outputs: tuple[AgentReliabilityFigureOutput, ...]

    @model_validator(mode="after")
    def validate_canonical_order(
        self,
    ) -> "MonitoringReviewReliabilityFigureManifest":
        if tuple(item.input_role for item in self.inputs) != (
            "published_current",
            "published_result",
        ):
            raise ValueError("monitoring gate inputs must use canonical order")
        if tuple(item.output_role for item in self.outputs) != (
            "vector_pdf",
            "web_png",
        ):
            raise ValueError("monitoring gate outputs must use canonical order")
        return self


class MonitoringReviewReliabilityFigureArtifacts(StrictBaseModel):
    """PDF, PNG y manifiesto derivados del puntero publicado."""

    pdf_path: str = Field(min_length=1)
    png_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest: MonitoringReviewReliabilityFigureManifest


class RunTrajectoryValidationProfile(StrictBaseModel):
    """Invariantes declaradas para una trayectoria longitudinal concreta."""

    profile_id: str = Field(min_length=1)
    expected_run_id: str = Field(min_length=1)
    expected_snapshot_count: int = Field(gt=0)
    expected_partition_counts: dict[TemporalPartitionId, int]
    expected_temporal_unit: Literal["snapshot"] = "snapshot"
    expected_detected_gaps: int = Field(ge=0)
    expected_cadence_intervals: int = Field(ge=0)
    expected_cadence_matches: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_expected_counts(self) -> "RunTrajectoryValidationProfile":
        if set(self.expected_partition_counts) != set(TEMPORAL_PARTITION_ORDER):
            raise ValueError("validation profile must declare all v2 partitions")
        if any(count <= 0 for count in self.expected_partition_counts.values()):
            raise ValueError("validation profile partition counts must be positive")
        if sum(self.expected_partition_counts.values()) != self.expected_snapshot_count:
            raise ValueError("partition counts must sum expected_snapshot_count")
        if self.expected_cadence_intervals != self.expected_snapshot_count - 1:
            raise ValueError(
                "expected_cadence_intervals must equal expected_snapshot_count - 1"
            )
        if self.expected_cadence_matches > self.expected_cadence_intervals:
            raise ValueError(
                "expected_cadence_matches cannot exceed cadence intervals"
            )
        return self


OFFICIAL_NASA_IMS_SET2_V2_PCA_PROFILE = RunTrajectoryValidationProfile(
    profile_id="nasa_ims_official_set2_v2_pca_trajectory_v1",
    expected_run_id="set_2",
    expected_snapshot_count=984,
    expected_partition_counts={
        "baseline_train": 197,
        "calibration": 98,
        "monitoring": 689,
    },
    expected_detected_gaps=0,
    expected_cadence_intervals=983,
    expected_cadence_matches=983,
)


class RunTrajectoryFigureInput(StrictBaseModel):
    """Entrada clasificada y ligada por hash a una figura longitudinal."""

    input_role: ValidationFigureInputRole
    path: str = Field(min_length=1)
    sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    size_bytes: int = Field(ge=0)
    media_type: Literal["text/csv", "application/json"]

    @model_validator(mode="after")
    def validate_role_media_type(self) -> "RunTrajectoryFigureInput":
        expected_media_type = {
            "snapshot_trajectory": "text/csv",
            "evaluation_metrics": "application/json",
        }[self.input_role]
        if self.media_type != expected_media_type:
            raise ValueError("input role and media type are inconsistent")
        return self


class RunTrajectoryValidationSummary(StrictBaseModel):
    """Resumen estructural consumido por la figura, no metricas recalculadas."""

    run_id: str = Field(min_length=1)
    snapshot_count: int = Field(gt=0)
    partition_counts: dict[TemporalPartitionId, int]
    temporal_unit: Literal["snapshot"] = "snapshot"
    unique_threshold: float = Field(gt=0)
    detected_gaps: int = Field(ge=0)
    cadence_intervals: int = Field(ge=0)
    cadence_matches: int = Field(ge=0)
    binary_metrics_available: Literal[False] = False
    first_persistent_alert_snapshot_id: str = Field(min_length=1)
    first_persistent_alert_index: int = Field(ge=0)
    first_persistent_alert_relative_life: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_partition_total(self) -> "RunTrajectoryValidationSummary":
        if set(self.partition_counts) != set(TEMPORAL_PARTITION_ORDER):
            raise ValueError("summary must contain all temporal partitions")
        if sum(self.partition_counts.values()) != self.snapshot_count:
            raise ValueError("summary partition counts must sum snapshot_count")
        if self.first_persistent_alert_index >= self.snapshot_count:
            raise ValueError("persistent alert index lies outside the trajectory")
        return self


class RunTrajectoryFigureManifest(StrictBaseModel):
    """Procedencia completa de la figura cientifica longitudinal."""

    schema_version: Literal["tfm.run_trajectory_figure_manifest.v1"] = (
        "tfm.run_trajectory_figure_manifest.v1"
    )
    renderer_id: Literal["run_trajectory_scientific_v1"] = (
        "run_trajectory_scientific_v1"
    )
    figure_id: str = Field(min_length=1)
    validation_profile: RunTrajectoryValidationProfile
    inputs: list[RunTrajectoryFigureInput] = Field(min_length=2, max_length=2)
    validation_summary: RunTrajectoryValidationSummary
    score_transform: Literal["log10(score/threshold)"] = (
        "log10(score/threshold)"
    )
    output_path: str = Field(min_length=1)
    output_format: Literal["pdf"] = "pdf"
    output_media_type: Literal["application/pdf"] = "application/pdf"
    output_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_input_roles(self) -> "RunTrajectoryFigureManifest":
        roles = [item.input_role for item in self.inputs]
        if roles != ["snapshot_trajectory", "evaluation_metrics"]:
            raise ValueError("figure inputs must use the canonical role order")
        if self.validation_summary.snapshot_count != (
            self.validation_profile.expected_snapshot_count
        ):
            raise ValueError("summary and validation profile snapshot counts differ")
        if self.validation_summary.partition_counts != (
            self.validation_profile.expected_partition_counts
        ):
            raise ValueError("summary and validation profile partitions differ")
        return self


class RunTrajectoryFigureArtifacts(StrictBaseModel):
    """Artefactos escritos para una trayectoria longitudinal validada."""

    pdf_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest: RunTrajectoryFigureManifest


@dataclass(frozen=True)
class _TrajectoryRow:
    run_id: str
    snapshot_id: str
    relative_life: float
    temporal_partition: TemporalPartitionId
    split: str
    label: str
    target: float | None
    label_source: str
    label_granularity: str
    temporal_unit: str
    threshold: float
    predicted_anomaly: int
    n_windows: int
    n_alerted_windows: int
    window_alert_fraction: float
    anomaly_score_median: float
    anomaly_score_p90: float
    health_index_smoothed: float
    gap_detected: bool
    cadence_matches_expected: bool | None
    snapshot_aggregation_policy_id: str
    temporal_gap_policy_id: str
    health_policy_id: str
    alert_policy_id: str
    health_indicator_policy_id: str


@dataclass(frozen=True)
class _PartitionSpan:
    partition_id: TemporalPartitionId
    start_index: int
    end_index: int
    count: int


@dataclass(frozen=True)
class _RunTrajectoryPlotData:
    rows: tuple[_TrajectoryRow, ...]
    partition_spans: tuple[_PartitionSpan, ...]
    summary: RunTrajectoryValidationSummary


def classify_run_trajectory_figure_input(
    content: bytes,
) -> ValidationFigureInputRole:
    """Clasifica una entrada por su contrato interno, no por su nombre."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("validation figure input must be UTF-8 text") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and {
        "binary_metric_context",
        "degradation_metrics",
    }.issubset(payload):
        return "evaluation_metrics"

    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is not None and RUN_TRAJECTORY_REQUIRED_COLUMNS.issubset(header):
        return "snapshot_trajectory"
    raise ValueError("input does not match a canonical run trajectory contract")


def render_run_trajectory_figure(
    *,
    snapshot_trajectory_path: str | Path = DEFAULT_OFFICIAL_RUN_TRAJECTORY,
    metrics_path: str | Path = DEFAULT_OFFICIAL_RUN_METRICS,
    output_dir: str | Path = DEFAULT_VALIDATION_FIGURES_DIR,
    figure_name: str = DEFAULT_RUN_TRAJECTORY_FIGURE_NAME,
    validation_profile: RunTrajectoryValidationProfile | None = None,
) -> RunTrajectoryFigureArtifacts:
    """Renderiza evidencia longitudinal ya calculada y validada por contrato."""

    profile = validation_profile or OFFICIAL_NASA_IMS_SET2_V2_PCA_PROFILE
    trajectory_path = Path(snapshot_trajectory_path)
    metrics_report_path = Path(metrics_path)
    trajectory_bytes = trajectory_path.read_bytes()
    metrics_bytes = metrics_report_path.read_bytes()
    _require_input_role(
        trajectory_bytes,
        expected_role="snapshot_trajectory",
        path=trajectory_path,
    )
    _require_input_role(
        metrics_bytes,
        expected_role="evaluation_metrics",
        path=metrics_report_path,
    )

    rows = _load_trajectory_rows(trajectory_bytes)
    metrics = _load_metrics_payload(metrics_bytes)
    plot_data = _validate_run_trajectory_contract(
        rows=rows,
        metrics=metrics,
        trajectory_path=trajectory_path,
        metrics_path=metrics_report_path,
        profile=profile,
    )

    target_dir = Path(output_dir)
    safe_figure_name = _plain_figure_name(figure_name)
    pdf_path = target_dir / f"{safe_figure_name}.pdf"
    manifest_path = target_dir / f"{safe_figure_name}.manifest.json"
    target_dir.mkdir(parents=True, exist_ok=True)
    _render_run_trajectory_pdf(plot_data=plot_data, output_path=pdf_path)

    manifest = RunTrajectoryFigureManifest(
        figure_id=safe_figure_name,
        validation_profile=profile,
        inputs=[
            RunTrajectoryFigureInput(
                input_role="snapshot_trajectory",
                path=trajectory_path.as_posix(),
                sha256=_sha256_bytes(trajectory_bytes),
                size_bytes=len(trajectory_bytes),
                media_type="text/csv",
            ),
            RunTrajectoryFigureInput(
                input_role="evaluation_metrics",
                path=metrics_report_path.as_posix(),
                sha256=_sha256_bytes(metrics_bytes),
                size_bytes=len(metrics_bytes),
                media_type="application/json",
            ),
        ],
        validation_summary=plot_data.summary,
        output_path=pdf_path.as_posix(),
        output_sha256=_sha256_bytes(pdf_path.read_bytes()),
    )
    _write_json_atomic(manifest_path, manifest.model_dump(mode="json"))
    return RunTrajectoryFigureArtifacts(
        pdf_path=pdf_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        manifest=manifest,
    )


def render_memory_corpus_governance_figure(
    *,
    source_report_path: str | Path = DEFAULT_MEMORY_INDEX_REPORT,
    output_dir: str | Path = DEFAULT_VALIDATION_FIGURES_DIR,
    figure_name: str = DEFAULT_MEMORY_CORPUS_FIGURE_NAME,
) -> ValidationFigureArtifacts:
    """Renderiza la composicion gobernada del corpus sin recalcular metricas."""

    source_path = Path(source_report_path)
    source_bytes = source_path.read_bytes()
    source_sha256 = _sha256_bytes(source_bytes)
    try:
        report = ReasoningMemoryIndexResult.model_validate_json(source_bytes)
    except ValueError as exc:
        raise ValueError(
            f"invalid reasoning memory index report: {source_path}"
        ) from exc

    categories = classify_memory_corpus_records(report)
    target_dir = Path(output_dir)
    safe_figure_name = _plain_figure_name(figure_name)
    pdf_path = target_dir / f"{safe_figure_name}.pdf"
    manifest_path = target_dir / f"{safe_figure_name}.manifest.json"
    target_dir.mkdir(parents=True, exist_ok=True)

    _render_memory_corpus_pdf(
        categories=categories,
        total_records=len(report.indexed_records),
        output_path=pdf_path,
    )
    output_sha256 = _sha256_bytes(pdf_path.read_bytes())
    manifest = ValidationFigureManifest(
        figure_id=safe_figure_name,
        source_path=source_path.as_posix(),
        source_sha256=source_sha256,
        source_size_bytes=len(source_bytes),
        source_record_count=len(report.indexed_records),
        classified_record_count=sum(category.count for category in categories),
        categories=categories,
        output_path=pdf_path.as_posix(),
        output_sha256=output_sha256,
    )
    _write_json_atomic(manifest_path, manifest.model_dump(mode="json"))
    return ValidationFigureArtifacts(
        pdf_path=pdf_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        manifest=manifest,
    )


def render_agent_reliability_figure(
    *,
    plan_dir: str | Path,
    output_dir: str | Path = DEFAULT_VALIDATION_FIGURES_DIR,
    figure_name: str = DEFAULT_AGENT_RELIABILITY_FIGURE_NAME,
) -> AgentReliabilityFigureArtifacts:
    """Renderiza la fiabilidad por entrypoint desde un pack decision-only.

    ``summary.json`` conserva las métricas publicadas. ``observations.jsonl``
    no se usa para estimar una tasa nueva: se valida contra esos recuentos para
    evitar representar un resumen desalineado con sus observaciones.
    """

    source_dir = Path(plan_dir)
    if not source_dir.is_dir():
        raise ValueError(f"agent reliability plan directory not found: {source_dir}")
    summary_path = source_dir / "summary.json"
    observations_path = source_dir / "observations.jsonl"
    summary_bytes = summary_path.read_bytes()
    observations_bytes = observations_path.read_bytes()
    summary = _load_agent_reliability_summary(summary_bytes, path=summary_path)
    observations = _load_agent_reliability_observations(
        observations_bytes,
        path=observations_path,
    )
    _validate_agent_reliability_figure_sources(
        summary=summary,
        observations=observations,
    )

    target_dir = Path(output_dir)
    safe_figure_name = _plain_figure_name(figure_name)
    pdf_path = target_dir / f"{safe_figure_name}.pdf"
    png_path = target_dir / f"{safe_figure_name}.png"
    manifest_path = target_dir / f"{safe_figure_name}.manifest.json"
    target_dir.mkdir(parents=True, exist_ok=True)
    rendered_outcomes = _visible_agent_reliability_outcomes(summary)
    _render_agent_reliability_outputs(
        summary=summary,
        rendered_outcomes=rendered_outcomes,
        pdf_path=pdf_path,
        png_path=png_path,
    )

    pdf_bytes = pdf_path.read_bytes()
    png_bytes = png_path.read_bytes()
    manifest = AgentReliabilityFigureManifest(
        figure_id=safe_figure_name,
        plan_dir=source_dir.as_posix(),
        inputs=[
            AgentReliabilityFigureInput(
                input_role="agent_reliability_summary",
                path=summary_path.as_posix(),
                sha256=_sha256_bytes(summary_bytes),
                size_bytes=len(summary_bytes),
                media_type="application/json",
            ),
            AgentReliabilityFigureInput(
                input_role="agent_reliability_observations",
                path=observations_path.as_posix(),
                sha256=_sha256_bytes(observations_bytes),
                size_bytes=len(observations_bytes),
                media_type="application/x-ndjson",
            ),
        ],
        metrics=summary,
        rendered_outcomes=rendered_outcomes,
        outputs=[
            AgentReliabilityFigureOutput(
                output_role="vector_pdf",
                path=pdf_path.as_posix(),
                output_format="pdf",
                media_type="application/pdf",
                sha256=_sha256_bytes(pdf_bytes),
                size_bytes=len(pdf_bytes),
            ),
            AgentReliabilityFigureOutput(
                output_role="web_png",
                path=png_path.as_posix(),
                output_format="png",
                media_type="image/png",
                sha256=_sha256_bytes(png_bytes),
                size_bytes=len(png_bytes),
            ),
        ],
    )
    _write_json_atomic(manifest_path, manifest.model_dump(mode="json"))
    return AgentReliabilityFigureArtifacts(
        pdf_path=pdf_path.as_posix(),
        png_path=png_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        manifest=manifest,
    )


def render_monitoring_review_reliability_figure(
    *,
    publication_root: str | Path = (
        DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR
    ),
    output_dir: str | Path = DEFAULT_VALIDATION_FIGURES_DIR,
    figure_name: str = DEFAULT_MONITORING_REVIEW_RELIABILITY_FIGURE_NAME,
) -> MonitoringReviewReliabilityFigureArtifacts:
    """Renderiza únicamente el gate señalado por ``current.json`` validado.

    El loader canónico comprueba el puntero, ``result.json`` y todos los hashes
    de artefactos antes de que la figura derive un solo recuento.
    """

    root = Path(publication_root).resolve()
    current_path = root / "current.json"
    current_bytes = current_path.read_bytes()
    result = load_published_monitoring_review_reliability(output_root=root)
    try:
        current_payload = json.loads(current_bytes)
        result_ref = current_payload["result_ref"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("published monitoring gate pointer is malformed") from exc
    if not isinstance(result_ref, str) or not result_ref.strip():
        raise ValueError("published monitoring gate result_ref is invalid")
    result_path = (root / result_ref).resolve()
    try:
        result_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("published monitoring gate result escapes its root") from exc
    result_bytes = result_path.read_bytes()
    metrics = _monitoring_review_reliability_figure_metrics(result)

    target_dir = Path(output_dir)
    safe_figure_name = _plain_figure_name(figure_name)
    pdf_path = target_dir / f"{safe_figure_name}.pdf"
    png_path = target_dir / f"{safe_figure_name}.png"
    manifest_path = target_dir / f"{safe_figure_name}.manifest.json"
    target_dir.mkdir(parents=True, exist_ok=True)
    _render_monitoring_review_reliability_outputs(
        metrics=metrics,
        pdf_path=pdf_path,
        png_path=png_path,
    )

    pdf_bytes = pdf_path.read_bytes()
    png_bytes = png_path.read_bytes()
    manifest = MonitoringReviewReliabilityFigureManifest(
        figure_id=safe_figure_name,
        publication_root=root.as_posix(),
        inputs=(
            MonitoringReviewReliabilityFigureInput(
                input_role="published_current",
                path=current_path.as_posix(),
                sha256=_sha256_bytes(current_bytes),
                size_bytes=len(current_bytes),
            ),
            MonitoringReviewReliabilityFigureInput(
                input_role="published_result",
                path=result_path.as_posix(),
                sha256=_sha256_bytes(result_bytes),
                size_bytes=len(result_bytes),
            ),
        ),
        metrics=metrics,
        outputs=(
            AgentReliabilityFigureOutput(
                output_role="vector_pdf",
                path=pdf_path.as_posix(),
                output_format="pdf",
                media_type="application/pdf",
                sha256=_sha256_bytes(pdf_bytes),
                size_bytes=len(pdf_bytes),
            ),
            AgentReliabilityFigureOutput(
                output_role="web_png",
                path=png_path.as_posix(),
                output_format="png",
                media_type="image/png",
                sha256=_sha256_bytes(png_bytes),
                size_bytes=len(png_bytes),
            ),
        ),
    )
    _write_json_atomic(manifest_path, manifest.model_dump(mode="json"))
    return MonitoringReviewReliabilityFigureArtifacts(
        pdf_path=pdf_path.as_posix(),
        png_path=png_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        manifest=manifest,
    )


def classify_memory_corpus_records(
    report: ReasoningMemoryIndexResult,
) -> list[ValidationFigureCategory]:
    """Clasifica cada registro una sola vez usando estados ya persistidos."""

    record_ids = [record.memory_record_id for record in report.indexed_records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("indexed_records contains duplicate memory_record_id values")

    quarantined_paths = _unique_path_keys(
        report.quarantined_memory_candidates,
        field_name="quarantined_memory_candidates",
    )
    audit_paths = _unique_path_keys(
        report.indexed_memory_usage_audits,
        field_name="indexed_memory_usage_audits",
    )
    overlap = quarantined_paths & audit_paths
    if overlap:
        raise ValueError(
            "candidate and audit source lists overlap: "
            + ", ".join(sorted(overlap))
        )

    classified: dict[MemoryCorpusCategoryId, list[str]] = {
        category_id: [] for category_id in CATEGORY_ORDER
    }
    sources_seen: dict[str, list[str]] = {}
    unclassified: list[str] = []

    for record in report.indexed_records:
        source_key = _optional_path_key(record.source_path)
        if source_key is not None:
            sources_seen.setdefault(source_key, []).append(record.memory_record_id)
        is_quarantined_candidate = source_key in quarantined_paths
        is_listed_audit = source_key in audit_paths
        is_audit_record = record.source_type == "memory_usage_audit"

        if is_listed_audit != is_audit_record:
            raise ValueError(
                "audit record/list mismatch for memory_record_id="
                f"{record.memory_record_id}"
            )
        if is_quarantined_candidate and record.reusable_as_context:
            raise ValueError(
                "quarantined candidate cannot be reusable: "
                f"{record.memory_record_id}"
            )
        if is_audit_record and record.reusable_as_context:
            raise ValueError(
                "memory usage audit cannot be retrievable: "
                f"{record.memory_record_id}"
            )

        if record.reusable_as_context:
            category_id: MemoryCorpusCategoryId = "reviewed_reusable"
        elif is_quarantined_candidate:
            category_id = "quarantined_candidates"
        elif is_audit_record:
            category_id = "non_retrievable_audits"
        else:
            unclassified.append(record.memory_record_id)
            continue
        classified[category_id].append(record.memory_record_id)

    _validate_listed_sources(
        quarantined_paths,
        sources_seen,
        field_name="quarantined_memory_candidates",
    )
    _validate_listed_sources(
        audit_paths,
        sources_seen,
        field_name="indexed_memory_usage_audits",
    )
    if unclassified:
        raise ValueError(
            "unclassified memory records: " + ", ".join(sorted(unclassified))
        )

    categories = [
        ValidationFigureCategory(
            category_id=category_id,
            label=CATEGORY_LABELS[category_id],
            count=len(classified[category_id]),
            record_ids=sorted(classified[category_id]),
        )
        for category_id in CATEGORY_ORDER
    ]
    classified_total = sum(category.count for category in categories)
    if classified_total != len(report.indexed_records):
        raise ValueError(
            "category counts do not sum the indexed record total: "
            f"{classified_total} != {len(report.indexed_records)}"
        )
    return categories


def _require_input_role(
    content: bytes,
    *,
    expected_role: ValidationFigureInputRole,
    path: Path,
) -> None:
    actual_role = classify_run_trajectory_figure_input(content)
    if actual_role != expected_role:
        raise ValueError(
            f"input role mismatch for {path}: {actual_role} != {expected_role}"
        )


def _load_trajectory_rows(content: bytes) -> tuple[_TrajectoryRow, ...]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = set(reader.fieldnames or [])
    missing_columns = sorted(RUN_TRAJECTORY_REQUIRED_COLUMNS - fieldnames)
    if missing_columns:
        raise ValueError(
            "snapshot trajectory is missing required columns: "
            + ", ".join(missing_columns)
        )

    rows: list[_TrajectoryRow] = []
    for line_number, raw in enumerate(reader, start=2):
        partition_value = _required_csv_text(
            raw,
            "temporal_partition",
            line_number=line_number,
        )
        if partition_value not in TEMPORAL_PARTITION_ORDER:
            raise ValueError(
                f"invalid temporal_partition at CSV line {line_number}: "
                f"{partition_value}"
            )
        row = _TrajectoryRow(
            run_id=_required_csv_text(raw, "run_id", line_number=line_number),
            snapshot_id=_required_csv_text(
                raw,
                "snapshot_id",
                line_number=line_number,
            ),
            relative_life=_required_csv_float(
                raw,
                "relative_life",
                line_number=line_number,
            ),
            temporal_partition=partition_value,
            split=_required_csv_text(raw, "split", line_number=line_number),
            label=_required_csv_text(raw, "label", line_number=line_number),
            target=_optional_csv_float(
                raw,
                "target",
                line_number=line_number,
            ),
            label_source=_required_csv_text(
                raw,
                "label_source",
                line_number=line_number,
            ),
            label_granularity=_required_csv_text(
                raw,
                "label_granularity",
                line_number=line_number,
            ),
            temporal_unit=_required_csv_text(
                raw,
                "temporal_unit",
                line_number=line_number,
            ),
            threshold=_required_csv_float(
                raw,
                "threshold",
                line_number=line_number,
            ),
            predicted_anomaly=_required_csv_int(
                raw,
                "predicted_anomaly",
                line_number=line_number,
            ),
            n_windows=_required_csv_int(
                raw,
                "n_windows",
                line_number=line_number,
            ),
            n_alerted_windows=_required_csv_int(
                raw,
                "n_alerted_windows",
                line_number=line_number,
            ),
            window_alert_fraction=_required_csv_float(
                raw,
                "window_alert_fraction",
                line_number=line_number,
            ),
            anomaly_score_median=_required_csv_float(
                raw,
                "anomaly_score_median",
                line_number=line_number,
            ),
            anomaly_score_p90=_required_csv_float(
                raw,
                "anomaly_score_p90",
                line_number=line_number,
            ),
            health_index_smoothed=_required_csv_float(
                raw,
                "health_index_smoothed",
                line_number=line_number,
            ),
            gap_detected=_required_csv_bool(
                raw,
                "gap_detected",
                line_number=line_number,
            ),
            cadence_matches_expected=_optional_csv_bool(
                raw,
                "cadence_matches_expected",
                line_number=line_number,
            ),
            snapshot_aggregation_policy_id=_required_csv_text(
                raw,
                "snapshot_aggregation_policy_id",
                line_number=line_number,
            ),
            temporal_gap_policy_id=_required_csv_text(
                raw,
                "temporal_gap_policy_id",
                line_number=line_number,
            ),
            health_policy_id=_required_csv_text(
                raw,
                "health_policy_id",
                line_number=line_number,
            ),
            alert_policy_id=_required_csv_text(
                raw,
                "alert_policy_id",
                line_number=line_number,
            ),
            health_indicator_policy_id=_required_csv_text(
                raw,
                "health_indicator_policy_id",
                line_number=line_number,
            ),
        )
        _validate_trajectory_row(row, line_number=line_number)
        rows.append(row)
    if not rows:
        raise ValueError("snapshot trajectory cannot be empty")
    return tuple(rows)


def _validate_trajectory_row(row: _TrajectoryRow, *, line_number: int) -> None:
    if not 0.0 <= row.relative_life <= 1.0:
        raise ValueError(f"relative_life outside [0, 1] at CSV line {line_number}")
    if row.threshold <= 0.0:
        raise ValueError(f"threshold must be positive at CSV line {line_number}")
    if row.anomaly_score_median <= 0.0 or row.anomaly_score_p90 <= 0.0:
        raise ValueError(
            f"score columns must be positive for logarithmic display at CSV line "
            f"{line_number}"
        )
    if row.anomaly_score_p90 < row.anomaly_score_median:
        raise ValueError(
            f"anomaly_score_p90 is below the median at CSV line {line_number}"
        )
    if row.predicted_anomaly not in {0, 1}:
        raise ValueError(
            f"predicted_anomaly must be binary at CSV line {line_number}"
        )
    if row.n_windows <= 0:
        raise ValueError(f"n_windows must be positive at CSV line {line_number}")
    if not 0 <= row.n_alerted_windows <= row.n_windows:
        raise ValueError(
            f"n_alerted_windows is inconsistent at CSV line {line_number}"
        )
    expected_fraction = row.n_alerted_windows / row.n_windows
    if not math.isclose(
        row.window_alert_fraction,
        expected_fraction,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"window_alert_fraction is inconsistent at CSV line {line_number}"
        )
    if not 0.0 <= row.health_index_smoothed <= 100.0:
        raise ValueError(
            f"health_index_smoothed outside [0, 100] at CSV line {line_number}"
        )


def _load_metrics_payload(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("evaluation metrics must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("evaluation metrics root must be a JSON object")
    return payload


def _validate_run_trajectory_contract(
    *,
    rows: tuple[_TrajectoryRow, ...],
    metrics: dict[str, Any],
    trajectory_path: Path,
    metrics_path: Path,
    profile: RunTrajectoryValidationProfile,
) -> _RunTrajectoryPlotData:
    if len(rows) != profile.expected_snapshot_count:
        raise ValueError(
            "snapshot count does not match validation profile: "
            f"{len(rows)} != {profile.expected_snapshot_count}"
        )
    snapshot_ids = [row.snapshot_id for row in rows]
    if len(snapshot_ids) != len(set(snapshot_ids)):
        raise ValueError("snapshot trajectory contains duplicate snapshot_id values")

    run_ids = {row.run_id for row in rows}
    if run_ids != {profile.expected_run_id}:
        raise ValueError(
            f"run_id values do not match profile: {sorted(run_ids)}"
        )
    temporal_units = {row.temporal_unit for row in rows}
    if temporal_units != {profile.expected_temporal_unit}:
        raise ValueError(
            "trajectory temporal unit must be snapshot: "
            f"{sorted(temporal_units)}"
        )

    _validate_v2_partition_classification(rows)
    partition_counts = Counter(row.temporal_partition for row in rows)
    actual_partition_counts = {
        partition_id: partition_counts[partition_id]
        for partition_id in TEMPORAL_PARTITION_ORDER
    }
    if actual_partition_counts != profile.expected_partition_counts:
        raise ValueError(
            "partition counts do not match validation profile: "
            f"{actual_partition_counts} != {profile.expected_partition_counts}"
        )
    partition_spans = _partition_spans(rows)

    thresholds = {row.threshold for row in rows}
    if len(thresholds) != 1:
        raise ValueError(
            f"trajectory must contain exactly one threshold, found {len(thresholds)}"
        )
    unique_threshold = next(iter(thresholds))
    detected_gaps = sum(row.gap_detected for row in rows)
    cadence_intervals = sum(
        row.cadence_matches_expected is not None for row in rows
    )
    cadence_matches = sum(
        row.cadence_matches_expected is True for row in rows
    )
    if detected_gaps != profile.expected_detected_gaps:
        raise ValueError(
            f"detected gap count mismatch: {detected_gaps} != "
            f"{profile.expected_detected_gaps}"
        )
    if cadence_intervals != profile.expected_cadence_intervals:
        raise ValueError(
            f"cadence interval count mismatch: {cadence_intervals} != "
            f"{profile.expected_cadence_intervals}"
        )
    if cadence_matches != profile.expected_cadence_matches:
        raise ValueError(
            f"cadence match count mismatch: {cadence_matches} != "
            f"{profile.expected_cadence_matches}"
        )
    if rows[0].cadence_matches_expected is not None:
        raise ValueError("first snapshot must not declare a cadence comparison")
    if any(row.cadence_matches_expected is None for row in rows[1:]):
        raise ValueError("every non-initial snapshot must declare cadence status")

    marker_id, marker_relative_life, alert_fraction_threshold = (
        _validate_metrics_contract(
            metrics=metrics,
            rows=rows,
            trajectory_path=trajectory_path,
            metrics_path=metrics_path,
            profile=profile,
            partition_counts=actual_partition_counts,
            detected_gaps=detected_gaps,
            cadence_intervals=cadence_intervals,
            cadence_matches=cadence_matches,
        )
    )
    for row in rows:
        expected_alert = int(
            row.window_alert_fraction >= alert_fraction_threshold
        )
        if row.predicted_anomaly != expected_alert:
            raise ValueError(
                "predicted_anomaly is inconsistent with the canonical snapshot "
                f"alert policy for {row.snapshot_id}"
            )

    marker_indexes = [
        index for index, row in enumerate(rows) if row.snapshot_id == marker_id
    ]
    if len(marker_indexes) != 1:
        raise ValueError(
            "first persistent alert snapshot must occur exactly once in trajectory"
        )
    marker_index = marker_indexes[0]
    if not math.isclose(
        rows[marker_index].relative_life,
        marker_relative_life,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "first persistent alert relative life differs between CSV and metrics"
        )

    summary = RunTrajectoryValidationSummary(
        run_id=profile.expected_run_id,
        snapshot_count=len(rows),
        partition_counts=actual_partition_counts,
        unique_threshold=unique_threshold,
        detected_gaps=detected_gaps,
        cadence_intervals=cadence_intervals,
        cadence_matches=cadence_matches,
        first_persistent_alert_snapshot_id=marker_id,
        first_persistent_alert_index=marker_index,
        first_persistent_alert_relative_life=marker_relative_life,
    )
    return _RunTrajectoryPlotData(
        rows=rows,
        partition_spans=partition_spans,
        summary=summary,
    )


def _validate_v2_partition_classification(
    rows: tuple[_TrajectoryRow, ...],
) -> None:
    for row in rows:
        expected = _PARTITION_CLASSIFICATION[row.temporal_partition]
        actual_text = {
            "split": row.split,
            "label": row.label,
            "label_source": row.label_source,
            "label_granularity": row.label_granularity,
        }
        for field_name, value in actual_text.items():
            if value != expected[field_name]:
                raise ValueError(
                    "v2 partition classification mismatch for "
                    f"{row.snapshot_id}: {field_name}={value}"
                )
        expected_target = expected["target"]
        if row.target != expected_target:
            raise ValueError(
                "v2 partition classification mismatch for "
                f"{row.snapshot_id}: target={row.target}"
            )


def _partition_spans(
    rows: tuple[_TrajectoryRow, ...],
) -> tuple[_PartitionSpan, ...]:
    spans: list[_PartitionSpan] = []
    current_partition = rows[0].temporal_partition
    start_index = 0
    seen: set[TemporalPartitionId] = set()
    for index, row in enumerate(rows[1:], start=1):
        if row.temporal_partition == current_partition:
            continue
        if current_partition in seen:
            raise ValueError("temporal partitions must be contiguous")
        seen.add(current_partition)
        spans.append(
            _PartitionSpan(
                partition_id=current_partition,
                start_index=start_index,
                end_index=index - 1,
                count=index - start_index,
            )
        )
        current_partition = row.temporal_partition
        start_index = index
    if current_partition in seen:
        raise ValueError("temporal partitions must be contiguous")
    spans.append(
        _PartitionSpan(
            partition_id=current_partition,
            start_index=start_index,
            end_index=len(rows) - 1,
            count=len(rows) - start_index,
        )
    )
    if tuple(span.partition_id for span in spans) != TEMPORAL_PARTITION_ORDER:
        raise ValueError("temporal partitions must follow the causal v2 order")
    return tuple(spans)


def _validate_metrics_contract(
    *,
    metrics: dict[str, Any],
    rows: tuple[_TrajectoryRow, ...],
    trajectory_path: Path,
    metrics_path: Path,
    profile: RunTrajectoryValidationProfile,
    partition_counts: dict[TemporalPartitionId, int],
    detected_gaps: int,
    cadence_intervals: int,
    cadence_matches: int,
) -> tuple[str, float, float]:
    if metrics.get("metric_families") != ["run_to_failure_degradation"]:
        raise ValueError("metrics must expose only run_to_failure_degradation")
    _validate_declared_path(
        metrics.get("metrics_path"),
        actual_path=metrics_path,
        field_name="metrics_path",
    )

    binary_context = _required_mapping(
        metrics,
        "binary_metric_context",
        context="metrics",
    )
    if binary_context.get("available") is not False:
        raise ValueError("binary metrics must be explicitly unavailable")
    if binary_context.get("target_interpretation") != "not_ground_truth":
        raise ValueError("monitoring target interpretation must be not_ground_truth")
    if binary_context.get("temporal_partitions") != list(
        TEMPORAL_PARTITION_ORDER
    ):
        raise ValueError("binary metric context does not declare v2 partitions")

    primary_metrics = _required_mapping(
        metrics,
        "primary_metrics",
        context="metrics",
    )
    _validate_binary_metrics_unavailable(primary_metrics, context="primary_metrics")
    split_metrics = _required_mapping(
        metrics,
        "metrics_by_split",
        context="metrics",
    )
    for split_name in ("train", "validation", "test"):
        split_payload = _required_mapping(
            split_metrics,
            split_name,
            context="metrics_by_split",
        )
        _validate_binary_metrics_unavailable(
            split_payload,
            context=f"metrics_by_split.{split_name}",
        )

    degradation = _required_mapping(
        metrics,
        "degradation_metrics",
        context="metrics",
    )
    _require_exact(degradation, "available", True, context="degradation_metrics")
    _require_exact(
        degradation,
        "metric_type",
        "run_to_failure_degradation",
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "temporal_unit",
        profile.expected_temporal_unit,
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "binary_metrics_unit",
        "window",
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "n_snapshots",
        profile.expected_snapshot_count,
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "n_detected_gaps",
        detected_gaps,
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "n_cadence_intervals",
        cadence_intervals,
        context="degradation_metrics",
    )
    _require_exact(
        degradation,
        "n_cadence_matches",
        cadence_matches,
        context="degradation_metrics",
    )
    _validate_declared_path(
        degradation.get("snapshot_trajectory_path"),
        actual_path=trajectory_path,
        field_name="degradation_metrics.snapshot_trajectory_path",
    )

    n_windows = sum(row.n_windows for row in rows)
    _require_exact(
        degradation,
        "n_windows",
        n_windows,
        context="degradation_metrics",
    )
    _require_exact(metrics, "n_predictions", n_windows, context="metrics")

    aggregation_policy = _required_mapping(
        degradation,
        "snapshot_aggregation_policy",
        context="degradation_metrics",
    )
    _require_exact(
        aggregation_policy,
        "score_aggregation",
        "median",
        context="snapshot_aggregation_policy",
    )
    _require_exact(
        aggregation_policy,
        "score_p90_quantile",
        0.9,
        context="snapshot_aggregation_policy",
    )
    alert_fraction_threshold = _required_metric_float(
        degradation,
        "snapshot_alert_fraction_threshold",
        context="degradation_metrics",
    )
    _require_exact(
        aggregation_policy,
        "alert_fraction_threshold",
        alert_fraction_threshold,
        context="snapshot_aggregation_policy",
    )
    _require_exact(
        aggregation_policy,
        "alert_threshold_operator",
        "greater_than_or_equal",
        context="snapshot_aggregation_policy",
    )
    if not 0.0 <= alert_fraction_threshold <= 1.0:
        raise ValueError("snapshot alert fraction threshold lies outside [0, 1]")

    policy_fields = (
        ("snapshot_aggregation_policy_id", "snapshot_aggregation_policy_id"),
        ("temporal_gap_policy_id", "temporal_gap_policy_id"),
        ("health_policy_id", "health_policy_id"),
        ("alert_policy_id", "alert_policy_id"),
        ("health_indicator_policy_id", "health_indicator_policy_id"),
    )
    for metric_field, row_field in policy_fields:
        metric_policy_id = degradation.get(metric_field)
        row_policy_ids = {getattr(row, row_field) for row in rows}
        if row_policy_ids != {metric_policy_id}:
            raise ValueError(
                f"{metric_field} differs between trajectory and metrics"
            )

    run_metrics = degradation.get("run_metrics")
    if not isinstance(run_metrics, list) or len(run_metrics) != 1:
        raise ValueError("degradation_metrics.run_metrics must contain one run")
    run_metric = run_metrics[0]
    if not isinstance(run_metric, dict):
        raise ValueError("degradation run metric must be a JSON object")
    _require_exact(
        run_metric,
        "run_id",
        profile.expected_run_id,
        context="degradation_metrics.run_metrics[0]",
    )
    _require_exact(
        run_metric,
        "temporal_unit",
        "snapshot",
        context="degradation_metrics.run_metrics[0]",
    )
    _require_exact(
        run_metric,
        "n_snapshots",
        profile.expected_snapshot_count,
        context="degradation_metrics.run_metrics[0]",
    )
    _require_exact(
        run_metric,
        "n_detected_gaps",
        detected_gaps,
        context="degradation_metrics.run_metrics[0]",
    )
    _require_exact(
        run_metric,
        "false_alarm_reference",
        "causal_v2_pre_monitoring_partitions",
        context="degradation_metrics.run_metrics[0]",
    )
    expected_pre_monitoring = (
        partition_counts["baseline_train"] + partition_counts["calibration"]
    )
    _require_exact(
        run_metric,
        "false_alarm_reference_snapshots",
        expected_pre_monitoring,
        context="degradation_metrics.run_metrics[0]",
    )
    marker_id = _required_metric_text(
        run_metric,
        "first_persistent_alert_snapshot_id",
        context="degradation_metrics.run_metrics[0]",
    )
    marker_relative_life = _required_metric_float(
        run_metric,
        "first_persistent_alert_relative_life",
        context="degradation_metrics.run_metrics[0]",
    )
    if not 0.0 <= marker_relative_life <= 1.0:
        raise ValueError("persistent alert relative life lies outside [0, 1]")
    return marker_id, marker_relative_life, alert_fraction_threshold


def _validate_binary_metrics_unavailable(
    payload: dict[str, Any],
    *,
    context: str,
) -> None:
    if payload.get("binary_metrics_available") is not False:
        raise ValueError(f"{context}.binary_metrics_available must be false")
    published = sorted(_BINARY_METRIC_KEYS & set(payload))
    if published:
        raise ValueError(
            f"{context} publishes unavailable binary metrics: "
            + ", ".join(published)
        )


def _render_run_trajectory_pdf(
    *,
    plot_data: _RunTrajectoryPlotData,
    output_path: Path,
) -> None:
    rows = plot_data.rows
    positions = list(range(len(rows)))
    threshold = plot_data.summary.unique_threshold
    median_ratios = [
        math.log10(row.anomaly_score_median / threshold) for row in rows
    ]
    p90_ratios = [
        math.log10(row.anomaly_score_p90 / threshold) for row in rows
    ]
    health_values = [row.health_index_smoothed for row in rows]
    alert_fractions = [row.window_alert_fraction for row in rows]
    marker_index = plot_data.summary.first_persistent_alert_index
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    fixed_date = datetime(2000, 1, 1, tzinfo=UTC)
    metadata = {
        "Title": "Evolución run-to-failure NASA IMS Set 2 con PCA",
        "Author": "TFM multiagente",
        "Subject": "Trayectoria longitudinal canónica por snapshot",
        "Keywords": "NASA IMS, run-to-failure, PCA, Health Index",
        "Creator": "tfm.validation_figures.run_trajectory_scientific_v1",
        "Producer": "Matplotlib",
        "CreationDate": fixed_date,
        "ModDate": fixed_date,
    }

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 9.5,
            "legend.fontsize": 8.5,
            "pdf.fonttype": 42,
        }
    ):
        figure, (score_axis, health_axis) = plt.subplots(
            2,
            1,
            figsize=(10.2, 7.2),
            sharex=True,
            constrained_layout=True,
            gridspec_kw={"height_ratios": [1.0, 1.05]},
        )
        try:
            _shade_temporal_partitions(
                score_axis,
                plot_data.partition_spans,
                total_snapshots=len(rows),
                show_labels=True,
            )
            _shade_temporal_partitions(
                health_axis,
                plot_data.partition_spans,
                total_snapshots=len(rows),
                show_labels=False,
            )

            score_axis.plot(
                positions,
                median_ratios,
                color="#24557A",
                linewidth=1.35,
                label="Mediana",
                zorder=3,
            )
            score_axis.plot(
                positions,
                p90_ratios,
                color="#C66B2B",
                linewidth=1.05,
                alpha=0.9,
                label="Percentil 90",
                zorder=2,
            )
            score_axis.axhline(
                0.0,
                color="#20262E",
                linewidth=1.0,
                linestyle="--",
                label="Umbral",
                zorder=4,
            )
            score_axis.axvline(
                marker_index,
                color="#A33B3B",
                linewidth=1.1,
                linestyle=":",
                zorder=5,
            )
            score_axis.set_ylabel(r"$\log_{10}(score/umbral)$")
            score_axis.set_title(
                "(a) Score de reconstrucción PCA normalizado",
                loc="left",
                fontweight="bold",
                pad=12,
            )
            score_axis.legend(loc="upper left", ncols=3, frameon=False)

            health_line = health_axis.plot(
                positions,
                health_values,
                color="#227C70",
                linewidth=1.5,
                label="Health Index suavizado",
                zorder=3,
            )[0]
            health_axis.set_ylim(0.0, 100.0)
            health_axis.set_ylabel("Health Index (0–100)", color="#1E675E")
            health_axis.tick_params(axis="y", colors="#1E675E")
            health_axis.axvline(
                marker_index,
                color="#A33B3B",
                linewidth=1.1,
                linestyle=":",
                zorder=5,
            )
            health_axis.scatter(
                [marker_index],
                [health_values[marker_index]],
                s=34,
                facecolor="white",
                edgecolor="#A33B3B",
                linewidth=1.3,
                zorder=6,
            )

            alert_axis = health_axis.twinx()
            alert_line = alert_axis.plot(
                positions,
                alert_fractions,
                color="#B85B25",
                linewidth=1.1,
                alpha=0.9,
                label="Fracción de ventanas en alerta",
                zorder=2,
            )[0]
            alert_axis.set_ylim(0.0, 1.0)
            alert_axis.set_ylabel("Fracción en alerta (0–1)", color="#9A4D20")
            alert_axis.tick_params(axis="y", colors="#9A4D20")
            relative_life_percent = (
                100.0 * plot_data.summary.first_persistent_alert_relative_life
            )
            marker_label = (
                "Alerta algorítmica persistente\n"
                f"snapshot {marker_index + 1}; trayectoria "
                f"{relative_life_percent:.1f} %"
            )
            health_axis.annotate(
                marker_label,
                xy=(marker_index, health_values[marker_index]),
                xytext=(14, 17),
                textcoords="offset points",
                color="#7F2929",
                fontsize=8.5,
                arrowprops={
                    "arrowstyle": "-",
                    "color": "#A33B3B",
                    "linewidth": 0.8,
                },
                bbox={
                    "boxstyle": "round,pad=0.25",
                    "facecolor": "white",
                    "edgecolor": "#D3A0A0",
                    "alpha": 0.9,
                },
                zorder=7,
            )
            health_axis.set_title(
                "(b) Indicador de salud y ventanas en alerta",
                loc="left",
                fontweight="bold",
                pad=10,
            )
            health_axis.legend(
                [health_line, alert_line],
                [health_line.get_label(), alert_line.get_label()],
                loc="upper right",
                frameon=False,
            )
            health_axis.set_xlabel("Snapshot del ensayo run-to-failure")

            for axis in (score_axis, health_axis):
                axis.set_xlim(-0.5, len(rows) - 0.5)
                axis.grid(
                    axis="y",
                    color="#CDD3D8",
                    linewidth=0.7,
                    alpha=0.75,
                )
                axis.set_axisbelow(True)
                axis.spines["top"].set_visible(False)
                axis.spines["right"].set_visible(False)
                axis.spines["left"].set_color("#8D969F")
                axis.spines["bottom"].set_color("#8D969F")
            health_axis.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=9))
            alert_axis.spines["top"].set_visible(False)
            alert_axis.spines["right"].set_color("#B85B25")

            figure.suptitle(
                "Evolución longitudinal NASA IMS Set 2 — PCA",
                x=0.01,
                ha="left",
                fontsize=15,
                fontweight="bold",
            )
            figure.savefig(
                temporary_path,
                format="pdf",
                bbox_inches="tight",
                metadata=metadata,
            )
        finally:
            plt.close(figure)
    temporary_path.replace(output_path)


def _shade_temporal_partitions(
    axis: Any,
    spans: tuple[_PartitionSpan, ...],
    *,
    total_snapshots: int,
    show_labels: bool,
) -> None:
    for span in spans:
        axis.axvspan(
            span.start_index - 0.5,
            span.end_index + 0.5,
            color=TEMPORAL_PARTITION_COLORS[span.partition_id],
            alpha=0.48,
            linewidth=0.0,
            zorder=0,
        )
        if span.start_index > 0:
            axis.axvline(
                span.start_index - 0.5,
                color="#9AA3AC",
                linewidth=0.7,
                zorder=1,
            )
        if show_labels:
            midpoint = (span.start_index + span.end_index) / 2
            percentage = 100.0 * span.count / total_snapshots
            axis.text(
                midpoint,
                0.88,
                f"{TEMPORAL_PARTITION_LABELS[span.partition_id]} "
                f"({percentage:.0f} %)",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                color="#4B5563",
                fontsize=8.2,
                fontweight="bold",
                zorder=6,
            )


def _required_csv_text(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> str:
    value = row.get(field_name)
    text = "" if value is None else value.strip()
    if not text:
        raise ValueError(
            f"missing {field_name} at snapshot trajectory line {line_number}"
        )
    return text


def _required_csv_float(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> float:
    value = _optional_csv_float(row, field_name, line_number=line_number)
    if value is None:
        raise ValueError(
            f"missing {field_name} at snapshot trajectory line {line_number}"
        )
    return value


def _optional_csv_float(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> float | None:
    raw_value = row.get(field_name)
    text = "" if raw_value is None else raw_value.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(
            f"invalid {field_name} at snapshot trajectory line {line_number}"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            f"non-finite {field_name} at snapshot trajectory line {line_number}"
        )
    return value


def _required_csv_int(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> int:
    raw_value = _required_csv_text(row, field_name, line_number=line_number)
    try:
        numeric = float(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"invalid {field_name} at snapshot trajectory line {line_number}"
        ) from exc
    if not numeric.is_integer():
        raise ValueError(
            f"non-integer {field_name} at snapshot trajectory line {line_number}"
        )
    return int(numeric)


def _required_csv_bool(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> bool:
    value = _optional_csv_bool(row, field_name, line_number=line_number)
    if value is None:
        raise ValueError(
            f"missing {field_name} at snapshot trajectory line {line_number}"
        )
    return value


def _optional_csv_bool(
    row: dict[str, str | None],
    field_name: str,
    *,
    line_number: int,
) -> bool | None:
    raw_value = row.get(field_name)
    text = "" if raw_value is None else raw_value.strip().lower()
    if not text:
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(
        f"invalid {field_name} at snapshot trajectory line {line_number}"
    )


def _required_mapping(
    payload: dict[str, Any],
    field_name: str,
    *,
    context: str,
) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{context}.{field_name} must be a JSON object")
    return value


def _require_exact(
    payload: dict[str, Any],
    field_name: str,
    expected: Any,
    *,
    context: str,
) -> None:
    actual = payload.get(field_name)
    if actual != expected:
        raise ValueError(
            f"{context}.{field_name} mismatch: {actual!r} != {expected!r}"
        )


def _required_metric_text(
    payload: dict[str, Any],
    field_name: str,
    *,
    context: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{field_name} must be non-empty text")
    return value.strip()


def _required_metric_float(
    payload: dict[str, Any],
    field_name: str,
    *,
    context: str,
) -> float:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context}.{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{context}.{field_name} must be finite")
    return result


def _monitoring_review_reliability_figure_metrics(
    result: MonitoringReviewReliabilityResult,
) -> MonitoringReviewReliabilityFigureMetrics:
    """Valida resumen y observaciones antes de proyectar recuentos visuales."""

    observations = result.observations
    summary = result.summary
    if not observations:
        raise ValueError("published monitoring gate has no observations")
    observation_ids = [item.observation_id for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("published monitoring gate contains duplicate observations")
    if summary.observation_count != len(observations):
        raise ValueError("published monitoring gate observation count is inconsistent")

    global_counts = Counter(item.outcome for item in observations)
    declared_counts = {
        "first_pass": summary.first_pass_count,
        "llm_repaired": summary.repaired_count,
        "fallback": summary.fallback_count,
        "non_agentic": summary.non_agentic_count,
        "error": summary.error_count,
    }
    for outcome in MONITORING_REVIEW_OUTCOME_ORDER:
        if global_counts[outcome] != declared_counts[outcome]:
            raise ValueError(
                "published monitoring gate outcome count mismatch for "
                f"{outcome}"
            )
    if sum(declared_counts.values()) != len(observations):
        raise ValueError("published monitoring gate outcomes are not exhaustive")

    expected_contexts = {
        item.context_id: item for item in result.plan.expected_contexts
    }
    expected_identity = {
        (repetition, context.context_id, role)
        for repetition in range(1, result.plan.repetitions + 1)
        for context in result.plan.expected_contexts
        for role in result.plan.expected_roles
    }
    observed_identity = {
        (item.repetition, item.context_id, item.agent_name)
        for item in observations
    }
    if not observed_identity.issubset(expected_identity):
        raise ValueError("published monitoring gate contains observations off plan")
    for item in observations:
        context = expected_contexts[item.context_id]
        if (
            item.context_ordinal != context.ordinal
            or item.trigger_type != context.trigger_type
            or item.condition_start_cursor != context.condition_start_cursor
            or item.cutoff_cursor != context.cutoff_cursor
        ):
            raise ValueError("published monitoring gate context binding changed")

    roles: list[MonitoringReviewReliabilityRoleMetrics] = []
    for role in MONITORING_REVIEW_ROLES:
        role_counts = Counter(
            item.outcome for item in observations if item.agent_name == role
        )
        roles.append(
            MonitoringReviewReliabilityRoleMetrics(
                agent_name=role,
                observation_count=sum(role_counts.values()),
                first_pass_count=role_counts["first_pass"],
                repaired_count=role_counts["llm_repaired"],
                fallback_count=role_counts["fallback"],
                non_agentic_count=role_counts["non_agentic"],
                error_count=role_counts["error"],
            )
        )

    matrix: list[MonitoringReviewReliabilityMatrixCell] = []
    for context in result.plan.expected_contexts:
        for repetition in range(1, result.plan.repetitions + 1):
            selected = [
                item
                for item in observations
                if item.context_id == context.context_id
                and item.repetition == repetition
            ]
            counts = Counter(item.outcome for item in selected)
            matrix.append(
                MonitoringReviewReliabilityMatrixCell(
                    context_id=context.context_id,
                    context_ordinal=context.ordinal,
                    trigger_type=context.trigger_type,
                    condition_start_cursor=context.condition_start_cursor,
                    cutoff_cursor=context.cutoff_cursor,
                    repetition=repetition,
                    observation_count=len(selected),
                    first_pass_count=counts["first_pass"],
                    repaired_count=counts["llm_repaired"],
                    fallback_count=counts["fallback"],
                    non_agentic_count=counts["non_agentic"],
                    error_count=counts["error"],
                    claims_scope_failure_count=sum(
                        not item.checks.claims_scoped for item in selected
                    ),
                )
            )

    coverage_specs = (
        (
            "hypothesis_structure",
            "hypothesis_structural_valid",
            summary.hypothesis_structural_rate,
        ),
        ("causal_grounding", "grounding_valid", summary.grounding_rate),
        ("trace_binding", "binding_valid", summary.binding_rate),
    )
    coverages: list[MonitoringReviewReliabilityCoverage] = []
    for coverage_id, check_field, declared_rate in coverage_specs:
        passed_count = sum(
            bool(getattr(item.checks, check_field)) for item in observations
        )
        observed_rate = passed_count / len(observations)
        if not math.isclose(declared_rate, observed_rate, abs_tol=1e-12):
            raise ValueError(
                f"published monitoring gate coverage mismatch for {coverage_id}"
            )
        coverages.append(
            MonitoringReviewReliabilityCoverage(
                coverage_id=coverage_id,
                label=MONITORING_REVIEW_COVERAGE_LABELS[coverage_id],
                passed_count=passed_count,
                observation_count=len(observations),
                rate=declared_rate,
            )
        )

    claims_scoped_count = sum(
        item.checks.claims_scoped for item in observations
    )
    if not math.isclose(
        summary.claims_scoped_rate,
        claims_scoped_count / len(observations),
        abs_tol=1e-12,
    ):
        raise ValueError("published monitoring gate claims scope rate is inconsistent")
    if summary.child_run_count != len(
        {item.child_run_id for item in observations}
    ):
        raise ValueError("published monitoring gate child run count is inconsistent")

    return MonitoringReviewReliabilityFigureMetrics(
        plan_id=result.plan.plan_id,
        model=result.manifest.llm_config.model,
        verdict=result.gate.verdict,
        blockers=result.gate.blockers,
        observation_count=len(observations),
        child_run_count=summary.child_run_count,
        claims_scoped_count=claims_scoped_count,
        claims_scoped_rate=summary.claims_scoped_rate,
        roles=tuple(roles),
        matrix=tuple(matrix),
        coverages=tuple(coverages),
    )


def _validate_declared_path(
    value: Any,
    *,
    actual_path: Path,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must declare a source path")
    declared = Path(value).expanduser().resolve(strict=False)
    actual = actual_path.expanduser().resolve(strict=False)
    if declared != actual:
        raise ValueError(
            f"{field_name} does not identify the supplied artifact: "
            f"{declared} != {actual}"
        )


def _load_agent_reliability_summary(
    content: bytes,
    *,
    path: Path,
) -> AgentReliabilitySummary:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid agent reliability summary JSON: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise ValueError(f"agent reliability summary object missing in: {path}")
    try:
        return AgentReliabilitySummary.model_validate(payload["summary"])
    except ValueError as exc:
        raise ValueError(f"invalid agent reliability summary contract: {path}") from exc


def _load_agent_reliability_observations(
    content: bytes,
    *,
    path: Path,
) -> tuple[AgentReliabilityObservation, ...]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"agent reliability observations must be UTF-8: {path}"
        ) from exc
    observations: list[AgentReliabilityObservation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            observation = AgentReliabilityObservation.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(
                "invalid agent reliability observation at "
                f"{path}:{line_number}"
            ) from exc
        observations.append(observation)
    if not observations:
        raise ValueError("agent reliability observations cannot be empty")
    return tuple(observations)


def _validate_agent_reliability_figure_sources(
    *,
    summary: AgentReliabilitySummary,
    observations: tuple[AgentReliabilityObservation, ...],
) -> None:
    observation_ids = [item.observation_id for item in observations]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("agent reliability observations contain duplicate ids")
    if summary.observation_count != len(observations):
        raise ValueError(
            "agent reliability observation count mismatch: "
            f"summary={summary.observation_count}, jsonl={len(observations)}"
        )

    actual_global = Counter(item.outcome for item in observations)
    declared_global = _agent_reliability_outcome_counts(summary)
    if sum(declared_global.values()) != summary.observation_count:
        raise ValueError("agent reliability global outcome counts are not exhaustive")
    for outcome in AGENT_RELIABILITY_OUTCOME_ORDER:
        if declared_global[outcome] != actual_global[outcome]:
            raise ValueError(
                "agent reliability outcome count mismatch for "
                f"{outcome}: summary={declared_global[outcome]}, "
                f"jsonl={actual_global[outcome]}"
            )

    declared_by_entrypoint = {
        item.entrypoint: item for item in summary.entrypoints
    }
    if len(declared_by_entrypoint) != len(summary.entrypoints):
        raise ValueError("agent reliability summary contains duplicate entrypoints")
    observed_entrypoints = {item.entrypoint for item in observations}
    if set(declared_by_entrypoint) != observed_entrypoints:
        raise ValueError(
            "agent reliability entrypoint mismatch between summary and jsonl"
        )

    for entrypoint in AGENT_RELIABILITY_ENTRYPOINT_ORDER:
        declared = declared_by_entrypoint.get(entrypoint)
        if declared is None:
            continue
        entrypoint_observations = [
            item for item in observations if item.entrypoint == entrypoint
        ]
        actual_counts = Counter(item.outcome for item in entrypoint_observations)
        declared_counts = _agent_reliability_outcome_counts(declared)
        if declared.observation_count != len(entrypoint_observations):
            raise ValueError(
                "agent reliability entrypoint observation count mismatch for "
                f"{entrypoint}"
            )
        if sum(declared_counts.values()) != declared.observation_count:
            raise ValueError(
                "agent reliability entrypoint outcome counts are not exhaustive "
                f"for {entrypoint}"
            )
        for outcome in AGENT_RELIABILITY_OUTCOME_ORDER:
            if declared_counts[outcome] != actual_counts[outcome]:
                raise ValueError(
                    "agent reliability entrypoint outcome mismatch for "
                    f"{entrypoint}/{outcome}"
                )
        expected_entrypoint_first_pass_rate = (
            declared.first_pass_count / declared.observation_count
        )
        expected_entrypoint_agentic_rate = (
            declared.first_pass_count + declared.repaired_count
        ) / declared.observation_count
        if not math.isclose(
            declared.first_pass_rate,
            expected_entrypoint_first_pass_rate,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "agent reliability entrypoint first-pass rate is inconsistent "
                f"for {entrypoint}"
            )
        if not math.isclose(
            declared.agentic_success_rate,
            expected_entrypoint_agentic_rate,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "agent reliability entrypoint agentic rate is inconsistent "
                f"for {entrypoint}"
            )

    expected_first_pass_rate = summary.first_pass_count / summary.observation_count
    expected_agentic_rate = (
        summary.first_pass_count + summary.repaired_count
    ) / summary.observation_count
    if not math.isclose(
        summary.first_pass_rate,
        expected_first_pass_rate,
        abs_tol=1e-12,
    ):
        raise ValueError("agent reliability global first-pass rate is inconsistent")
    if not math.isclose(
        summary.agentic_success_rate,
        expected_agentic_rate,
        abs_tol=1e-12,
    ):
        raise ValueError("agent reliability global agentic rate is inconsistent")


def _agent_reliability_outcome_counts(
    summary: Any,
) -> dict[AgentReliabilityOutcome, int]:
    return {
        "first_pass": summary.first_pass_count,
        "llm_repaired": summary.repaired_count,
        "fallback": summary.fallback_count,
        "semantic_failure": summary.semantic_failure_count,
        "non_agentic": summary.non_agentic_count,
        "error": summary.error_count,
    }


def _visible_agent_reliability_outcomes(
    summary: AgentReliabilitySummary,
) -> list[AgentReliabilityOutcome]:
    counts = _agent_reliability_outcome_counts(summary)
    always_visible: tuple[AgentReliabilityOutcome, ...] = (
        "first_pass",
        "llm_repaired",
        "fallback",
    )
    exceptional = tuple(
        outcome
        for outcome in AGENT_RELIABILITY_OUTCOME_ORDER[3:]
        if counts[outcome] > 0
    )
    return [*always_visible, *exceptional]


def _render_agent_reliability_outputs(
    *,
    summary: AgentReliabilitySummary,
    rendered_outcomes: list[AgentReliabilityOutcome],
    pdf_path: Path,
    png_path: Path,
) -> None:
    by_entrypoint = {item.entrypoint: item for item in summary.entrypoints}
    entrypoints = [
        entrypoint
        for entrypoint in AGENT_RELIABILITY_ENTRYPOINT_ORDER
        if entrypoint in by_entrypoint
    ]
    positions = list(range(len(entrypoints)))
    labels = [AGENT_RELIABILITY_ENTRYPOINT_LABELS[item] for item in entrypoints]
    totals = [by_entrypoint[item].observation_count for item in entrypoints]
    maximum_total = max(totals, default=1)
    axis_max = max(1.0, maximum_total * 1.16)
    figure_height = max(5.4, 0.58 * len(entrypoints) + 3.2)
    temporary_pdf_path = pdf_path.with_name(f".{pdf_path.name}.tmp")
    temporary_png_path = png_path.with_name(f".{png_path.name}.tmp")
    fixed_date = datetime(2000, 1, 1, tzinfo=UTC)
    pdf_metadata = {
        "Title": "Fiabilidad por punto de decisión agéntico",
        "Author": "TFM multiagente",
        "Subject": "Banco cerrado decision-only por entrypoint",
        "Keywords": "agentes, LLM, decision-only, fallback, trazabilidad",
        "Creator": "tfm.validation_figures.agent_reliability_stacked_bars_v1",
        "Producer": "Matplotlib",
        "CreationDate": fixed_date,
        "ModDate": fixed_date,
    }
    png_metadata = {
        "Title": "Fiabilidad por punto de decisión agéntico",
        "Author": "TFM multiagente",
        "Description": AGENT_RELIABILITY_INTERPRETATION_LIMIT,
        "Software": "tfm.validation_figures.agent_reliability_stacked_bars_v1",
    }

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.titlesize": 14,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "pdf.fonttype": 42,
        }
    ):
        figure, axis = plt.subplots(figsize=(10.6, figure_height))
        try:
            figure.subplots_adjust(
                left=0.24,
                right=0.97,
                top=0.76,
                bottom=0.18,
            )
            left_offsets = [0] * len(entrypoints)
            for outcome in rendered_outcomes:
                values = [
                    _agent_reliability_outcome_counts(by_entrypoint[item])[outcome]
                    for item in entrypoints
                ]
                bars = axis.barh(
                    positions,
                    values,
                    left=left_offsets,
                    height=0.62,
                    color=AGENT_RELIABILITY_OUTCOME_COLORS[outcome],
                    label=AGENT_RELIABILITY_OUTCOME_LABELS[outcome],
                )
                label_color = "#111827" if outcome == "fallback" else "#FFFFFF"
                for bar, value in zip(bars, values, strict=True):
                    if value <= 0:
                        continue
                    axis.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        str(value),
                        ha="center",
                        va="center",
                        color=label_color,
                        fontsize=9,
                        fontweight="bold",
                    )
                left_offsets = [
                    left + value
                    for left, value in zip(left_offsets, values, strict=True)
                ]

            axis.set_yticks(positions, labels)
            axis.invert_yaxis()
            axis.set_xlim(0, axis_max)
            axis.xaxis.set_major_locator(MaxNLocator(integer=True, min_n_ticks=3))
            axis.set_xlabel("Número de decisiones observadas")
            axis.grid(axis="x", color="#D1D5DB", linewidth=0.8, alpha=0.7)
            axis.set_axisbelow(True)
            for spine in ("top", "right", "left"):
                axis.spines[spine].set_visible(False)
            axis.spines["bottom"].set_color("#9CA3AF")
            axis.tick_params(axis="y", length=0, pad=9)
            axis.tick_params(axis="x", colors="#4B5563")
            for position, total in zip(positions, totals, strict=True):
                axis.text(
                    total + axis_max * 0.015,
                    position,
                    f"n={total}",
                    ha="left",
                    va="center",
                    color="#4B5563",
                    fontsize=8.5,
                )

            figure.suptitle(
                "Fiabilidad por punto de decisión agéntico",
                x=0.02,
                y=0.965,
                ha="left",
                fontweight="bold",
                fontsize=15,
            )
            figure.text(
                0.02,
                0.915,
                f"Banco cerrado decision-only · {summary.observation_count} "
                f"observaciones · {len(entrypoints)} entrypoints",
                ha="left",
                va="top",
                color="#4B5563",
                fontsize=9.5,
            )
            axis.legend(
                loc="lower left",
                bbox_to_anchor=(0.0, 1.025),
                frameon=False,
                ncol=min(3, len(rendered_outcomes)),
                borderaxespad=0,
            )
            figure.text(
                0.02,
                0.035,
                "Alcance: banco cerrado decision-only; compara únicamente estas "
                "decisiones y esta configuración.\n"
                "No es una tasa universal ni confirma o refuta las hipótesis "
                "científicas de los agentes.",
                ha="left",
                va="bottom",
                color="#374151",
                fontsize=8.8,
            )

            figure.savefig(
                temporary_pdf_path,
                format="pdf",
                bbox_inches="tight",
                metadata=pdf_metadata,
            )
            figure.savefig(
                temporary_png_path,
                format="png",
                dpi=180,
                bbox_inches="tight",
                facecolor="white",
                metadata=png_metadata,
            )
        finally:
            plt.close(figure)
    temporary_pdf_path.replace(pdf_path)
    temporary_png_path.replace(png_path)


def _render_monitoring_review_reliability_outputs(
    *,
    metrics: MonitoringReviewReliabilityFigureMetrics,
    pdf_path: Path,
    png_path: Path,
) -> None:
    temporary_pdf_path = pdf_path.with_name(f".{pdf_path.name}.tmp")
    temporary_png_path = png_path.with_name(f".{png_path.name}.tmp")
    fixed_date = datetime(2000, 1, 1, tzinfo=UTC)
    pdf_metadata = {
        "Title": "Gate multiagente de monitorización NASA P3",
        "Author": "TFM multiagente",
        "Subject": "Tres replays, cuatro triggers y siete roles",
        "Keywords": "NASA, monitorización, agentes, gate, trazabilidad",
        "Creator": "tfm.validation_figures.monitoring_review_reliability_gate_v1",
        "Producer": "Matplotlib",
        "CreationDate": fixed_date,
        "ModDate": fixed_date,
    }
    png_metadata = {
        "Title": "Gate multiagente de monitorización NASA P3",
        "Author": "TFM multiagente",
        "Description": MONITORING_REVIEW_RELIABILITY_INTERPRETATION_LIMIT,
        "Software": (
            "tfm.validation_figures.monitoring_review_reliability_gate_v1"
        ),
    }
    role_outcomes: list[MonitoringReviewReliabilityOutcome] = [
        "first_pass",
        "llm_repaired",
        "fallback",
    ]
    if any(item.non_agentic_count for item in metrics.roles):
        role_outcomes.append("non_agentic")
    role_outcomes.append("error")

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.labelsize": 9,
            "legend.fontsize": 7.8,
            "pdf.fonttype": 42,
        }
    ):
        figure = plt.figure(figsize=(12.8, 8.0), facecolor="white")
        grid = figure.add_gridspec(
            2,
            2,
            height_ratios=(3.2, 1.25),
            width_ratios=(1.08, 1.0),
        )
        roles_axis = figure.add_subplot(grid[0, 0])
        matrix_axis = figure.add_subplot(grid[0, 1])
        coverage_axis = figure.add_subplot(grid[1, :])
        try:
            figure.subplots_adjust(
                left=0.17,
                right=0.98,
                top=0.755,
                bottom=0.13,
                hspace=0.55,
                wspace=0.38,
            )
            _draw_monitoring_review_role_bars(
                roles_axis,
                roles=metrics.roles,
                outcomes=role_outcomes,
            )
            _draw_monitoring_review_matrix(matrix_axis, matrix=metrics.matrix)
            _draw_monitoring_review_coverages(
                coverage_axis,
                coverages=metrics.coverages,
            )

            verdict_label = (
                "GATE SUPERADO"
                if metrics.verdict == "passed"
                else "GATE BLOQUEADO"
            )
            verdict_color = (
                "#1F7A68" if metrics.verdict == "passed" else "#B42318"
            )
            verdict_fill = (
                "#DDF4EC" if metrics.verdict == "passed" else "#FDE7E3"
            )
            figure.suptitle(
                "Revisión multiagente de monitorización · NASA P3",
                x=0.02,
                y=0.975,
                ha="left",
                fontweight="bold",
                fontsize=16,
            )
            figure.text(
                0.98,
                0.968,
                verdict_label,
                ha="right",
                va="top",
                color=verdict_color,
                fontsize=10,
                fontweight="bold",
                bbox={
                    "boxstyle": "round,pad=0.42",
                    "facecolor": verdict_fill,
                    "edgecolor": verdict_color,
                    "linewidth": 1.1,
                },
            )
            figure.text(
                0.02,
                0.925,
                f"{metrics.child_run_count} hijas · {metrics.observation_count} "
                f"decisiones · {metrics.model} · memoria OFF · política no aplicada",
                ha="left",
                va="top",
                color="#4B5563",
                fontsize=9.5,
            )
            if metrics.verdict == "blocked":
                status_text = _monitoring_review_blocked_status(metrics)
            else:
                status_text = (
                    "Los criterios prerregistrados se cumplen; el resultado no "
                    "confirma la verdad física de las hipótesis."
                )
            figure.text(
                0.02,
                0.885,
                status_text,
                ha="left",
                va="top",
                color=(
                    verdict_color if metrics.verdict == "blocked" else "#374151"
                ),
                fontsize=9,
                fontweight=("bold" if metrics.verdict == "blocked" else "normal"),
            )
            figure.text(
                0.02,
                0.025,
                "Alcance: tres replays del mismo escenario NASA P3. Las barras y "
                "coberturas son recuentos contractuales; no son un score global ni "
                "miden veracidad física o generalización industrial.",
                ha="left",
                va="bottom",
                color="#374151",
                fontsize=8.3,
            )

            figure.savefig(
                temporary_pdf_path,
                format="pdf",
                bbox_inches="tight",
                metadata=pdf_metadata,
            )
            figure.savefig(
                temporary_png_path,
                format="png",
                dpi=180,
                bbox_inches="tight",
                facecolor="white",
                metadata=png_metadata,
            )
        finally:
            plt.close(figure)
    temporary_pdf_path.replace(pdf_path)
    temporary_png_path.replace(png_path)


def _draw_monitoring_review_role_bars(
    axis: Any,
    *,
    roles: tuple[MonitoringReviewReliabilityRoleMetrics, ...],
    outcomes: list[MonitoringReviewReliabilityOutcome],
) -> None:
    positions = list(range(len(roles)))
    labels = [AGENT_RELIABILITY_ENTRYPOINT_LABELS[item.agent_name] for item in roles]
    totals = [item.observation_count for item in roles]
    left_offsets = [0] * len(roles)
    for outcome in outcomes:
        values = [
            _monitoring_review_role_outcome_counts(item)[outcome] for item in roles
        ]
        bars = axis.barh(
            positions,
            values,
            left=left_offsets,
            height=0.58,
            color=MONITORING_REVIEW_OUTCOME_COLORS[outcome],
            label=MONITORING_REVIEW_OUTCOME_LABELS[outcome],
        )
        for bar, value in zip(bars, values, strict=True):
            if value <= 0:
                continue
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_y() + bar.get_height() / 2,
                str(value),
                ha="center",
                va="center",
                color="#111827" if outcome == "fallback" else "#FFFFFF",
                fontsize=8.5,
                fontweight="bold",
            )
        left_offsets = [
            left + value for left, value in zip(left_offsets, values, strict=True)
        ]
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlim(0, max(totals, default=1) * 1.08)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True, min_n_ticks=4))
    axis.set_xlabel("Decisiones por rol")
    axis.set_title("1 · Resultado de los siete roles", loc="left", fontweight="bold")
    axis.grid(axis="x", color="#D1D5DB", linewidth=0.8, alpha=0.65)
    axis.set_axisbelow(True)
    axis.tick_params(axis="y", length=0, pad=7)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    axis.spines["bottom"].set_color("#9CA3AF")
    axis.legend(
        loc="lower left",
        bbox_to_anchor=(0.0, 1.075),
        frameon=False,
        ncol=min(4, len(outcomes)),
        borderaxespad=0,
    )


def _draw_monitoring_review_matrix(
    axis: Any,
    *,
    matrix: tuple[MonitoringReviewReliabilityMatrixCell, ...],
) -> None:
    by_cell = {
        (item.context_ordinal, item.repetition): item for item in matrix
    }
    context_rows = [by_cell[(ordinal, 1)] for ordinal in range(1, 5)]
    for row_index, context in enumerate(context_rows):
        for repetition in range(1, 4):
            cell = by_cell[(context.context_ordinal, repetition)]
            edgecolor = "#B42318" if cell.claims_scope_failure_count else "#FFFFFF"
            axis.add_patch(
                Rectangle(
                    (repetition - 1 + 0.04, row_index + 0.06),
                    0.92,
                    0.88,
                    facecolor=_monitoring_review_matrix_color(cell),
                    edgecolor=edgecolor,
                    linewidth=2.0 if cell.claims_scope_failure_count else 1.0,
                )
            )
            fragments = [
                f"{count}{MONITORING_REVIEW_OUTCOME_SHORT_LABELS[outcome]}"
                for outcome, count in _monitoring_review_matrix_outcomes(cell)
                if count
            ]
            axis.text(
                repetition - 0.5,
                row_index + 0.40,
                " · ".join(fragments) if fragments else "0",
                ha="center",
                va="center",
                color="#111827",
                fontsize=9,
                fontweight="bold",
            )
            if cell.claims_scope_failure_count:
                axis.text(
                    repetition - 0.5,
                    row_index + 0.71,
                    f"alcance: {cell.claims_scope_failure_count}",
                    ha="center",
                    va="center",
                    color="#B42318",
                    fontsize=7.5,
                    fontweight="bold",
                )
    axis.set_xlim(0, 3)
    axis.set_ylim(4, 0)
    axis.set_xticks((0.5, 1.5, 2.5), ("Replay 1", "Replay 2", "Replay 3"))
    axis.xaxis.tick_top()
    axis.set_yticks(
        tuple(index + 0.5 for index in range(4)),
        tuple(_monitoring_review_context_label(item) for item in context_rows),
    )
    axis.tick_params(axis="both", length=0, pad=7)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.set_title(
        "2 · Matriz de triggers × replays",
        loc="left",
        fontweight="bold",
        pad=32,
    )
    axis.text(
        0.0,
        -0.13,
        "P primera · R reparación · F fallback · N no agéntica · E error",
        transform=axis.transAxes,
        ha="left",
        va="top",
        color="#4B5563",
        fontsize=7.7,
    )


def _draw_monitoring_review_coverages(
    axis: Any,
    *,
    coverages: tuple[MonitoringReviewReliabilityCoverage, ...],
) -> None:
    positions = tuple(reversed(range(len(coverages))))
    rates = [100.0 * item.rate for item in coverages]
    axis.barh(positions, [100.0] * len(coverages), color="#E5E7EB", height=0.48)
    bars = axis.barh(
        positions,
        rates,
        color=["#2A9D8F" if item.rate == 1.0 else "#D97706" for item in coverages],
        height=0.48,
    )
    axis.set_yticks(positions, [item.label for item in coverages])
    axis.set_xlim(0, 108)
    axis.set_xticks((0, 25, 50, 75, 100), ("0", "25", "50", "75", "100 %"))
    axis.set_title(
        "3 · Cobertura contractual (no veracidad física)",
        loc="left",
        fontweight="bold",
        pad=10,
    )
    axis.grid(axis="x", color="#D1D5DB", linewidth=0.8, alpha=0.6)
    axis.set_axisbelow(True)
    axis.tick_params(axis="y", length=0, pad=8)
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    axis.spines["bottom"].set_color("#9CA3AF")
    for bar, item in zip(bars, coverages, strict=True):
        axis.text(
            102.0,
            bar.get_y() + bar.get_height() / 2,
            f"{item.passed_count}/{item.observation_count}",
            ha="left",
            va="center",
            color="#111827",
            fontsize=8.3,
            fontweight="bold",
        )


def _monitoring_review_role_outcome_counts(
    metrics: MonitoringReviewReliabilityRoleMetrics,
) -> dict[MonitoringReviewReliabilityOutcome, int]:
    return {
        "first_pass": metrics.first_pass_count,
        "llm_repaired": metrics.repaired_count,
        "fallback": metrics.fallback_count,
        "non_agentic": metrics.non_agentic_count,
        "error": metrics.error_count,
    }


def _monitoring_review_blocked_status(
    metrics: MonitoringReviewReliabilityFigureMetrics,
) -> str:
    """Resume blockers publicados sin presentar una causa que ya cumple."""

    descriptions: list[str] = []
    if any(item.startswith("resolved_child_run_count:") for item in metrics.blockers):
        descriptions.append("11/12 runs resueltas")
    fallback_count = sum(item.fallback_count for item in metrics.roles)
    if any(item.startswith("fallback_count:") for item in metrics.blockers):
        descriptions.append(f"{fallback_count} fallbacks")
    if any(item.startswith("llm_origin_rate:") for item in metrics.blockers):
        descriptions.append("origen LLM incompleto")
    if any(item.startswith("claims_scoped_rate:") for item in metrics.blockers):
        descriptions.append(
            "alcance prudente "
            f"{metrics.claims_scoped_count}/{metrics.observation_count}"
        )
    if not descriptions:
        descriptions.append(f"{len(metrics.blockers)} criterios incumplidos")
    return (
        "Bloqueo contractual: "
        + " · ".join(descriptions)
        + ". No autoriza la siguiente fase."
    )


def _monitoring_review_matrix_outcomes(
    cell: MonitoringReviewReliabilityMatrixCell,
) -> tuple[tuple[MonitoringReviewReliabilityOutcome, int], ...]:
    return (
        ("first_pass", cell.first_pass_count),
        ("llm_repaired", cell.repaired_count),
        ("fallback", cell.fallback_count),
        ("non_agentic", cell.non_agentic_count),
        ("error", cell.error_count),
    )


def _monitoring_review_matrix_color(
    cell: MonitoringReviewReliabilityMatrixCell,
) -> str:
    if cell.error_count or cell.non_agentic_count:
        return "#F8D7DA"
    if cell.fallback_count:
        return "#FCE8C3"
    if cell.repaired_count:
        return "#DDEAF4"
    if cell.first_pass_count:
        return "#DDF4EC"
    return "#F3F4F6"


def _monitoring_review_context_label(
    cell: MonitoringReviewReliabilityMatrixCell,
) -> str:
    labels = {
        "state_transition": "Transición",
        "persistent_alert": "Persistencia",
        "session_close": "Cierre",
    }
    interval = (
        str(cell.cutoff_cursor)
        if cell.condition_start_cursor == cell.cutoff_cursor
        else f"{cell.condition_start_cursor}→{cell.cutoff_cursor}"
    )
    return f"{labels.get(cell.trigger_type, cell.trigger_type)} · {interval}"


def _render_memory_corpus_pdf(
    *,
    categories: list[ValidationFigureCategory],
    total_records: int,
    output_path: Path,
) -> None:
    labels = [category.label for category in categories]
    counts = [category.count for category in categories]
    colors = [CATEGORY_COLORS[category.category_id] for category in categories]
    max_count = max(counts, default=0)
    axis_max = max(1.0, max_count * 1.28)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    fixed_date = datetime(2000, 1, 1, tzinfo=UTC)
    metadata = {
        "Title": "Gobernanza del corpus de memoria RAG",
        "Author": "TFM multiagente",
        "Subject": "Clasificación canónica del corpus de memoria",
        "Keywords": "RAG, memoria, gobernanza, validacion",
        "Creator": "tfm.validation_figures.memory_corpus_governance_v1",
        "Producer": "Matplotlib",
        "CreationDate": fixed_date,
        "ModDate": fixed_date,
    }

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.labelsize": 10,
            "pdf.fonttype": 42,
        }
    ):
        figure, axis = plt.subplots(figsize=(8.2, 4.2), constrained_layout=True)
        try:
            positions = list(range(len(categories)))
            bars = axis.barh(positions, counts, color=colors, height=0.58)
            axis.set_yticks(positions, labels)
            axis.invert_yaxis()
            axis.set_xlim(0, axis_max)
            axis.xaxis.set_major_locator(MaxNLocator(integer=True, min_n_ticks=3))
            axis.set_xlabel("Número de registros")
            axis.set_title(
                "Gobernanza del corpus de memoria RAG",
                loc="left",
                pad=20,
                fontweight="bold",
            )
            axis.text(
                0,
                1.03,
                "Clasificación completa y disjunta del índice canónico "
                f"(n={total_records})",
                transform=axis.transAxes,
                color="#4B5563",
                fontsize=9,
            )
            axis.grid(axis="x", color="#D1D5DB", linewidth=0.8, alpha=0.7)
            axis.set_axisbelow(True)
            for spine in ("top", "right", "left"):
                axis.spines[spine].set_visible(False)
            axis.spines["bottom"].set_color("#9CA3AF")
            axis.tick_params(axis="y", length=0, pad=9)
            axis.tick_params(axis="x", colors="#4B5563")

            for bar, count in zip(bars, counts, strict=True):
                percentage = (
                    0.0 if total_records == 0 else 100.0 * count / total_records
                )
                axis.text(
                    min(axis_max * 0.97, count + axis_max * 0.025),
                    bar.get_y() + bar.get_height() / 2,
                    f"{count}  ({percentage:.1f} %)",
                    va="center",
                    ha="left",
                    color="#111827",
                    fontweight="bold",
                    fontsize=9,
                )

            figure.savefig(
                temporary_path,
                format="pdf",
                bbox_inches="tight",
                metadata=metadata,
            )
        finally:
            plt.close(figure)
    temporary_path.replace(output_path)


def _plain_figure_name(value: str) -> str:
    candidate = value.strip()
    path = Path(candidate)
    if not candidate or candidate in {".", ".."}:
        raise ValueError("figure_name cannot be empty")
    if path.name != candidate or path.is_absolute():
        raise ValueError("figure_name must be a plain file stem")
    if path.suffix:
        raise ValueError("figure_name must not include a file extension")
    return candidate


def _unique_path_keys(values: list[str], *, field_name: str) -> set[str]:
    keys = [_path_key(value) for value in values]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{field_name} contains duplicate paths")
    return set(keys)


def _optional_path_key(value: str | None) -> str | None:
    return None if value is None else _path_key(value)


def _path_key(value: str) -> str:
    return Path(value).expanduser().resolve(strict=False).as_posix()


def _validate_listed_sources(
    expected_paths: set[str],
    sources_seen: dict[str, list[str]],
    *,
    field_name: str,
) -> None:
    missing = sorted(expected_paths - set(sources_seen))
    if missing:
        raise ValueError(
            f"{field_name} contains paths without indexed records: "
            + ", ".join(missing)
        )
    duplicates = sorted(
        path for path in expected_paths if len(sources_seen.get(path, [])) != 1
    )
    if duplicates:
        raise ValueError(
            f"{field_name} paths must map to exactly one indexed record: "
            + ", ".join(duplicates)
        )


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
