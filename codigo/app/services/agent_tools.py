"""Catalogo minimo de herramientas seguras para agentes."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from codigo.app.schemas.reasoning import (
    AgentToolAgent,
    AgentToolObservation,
    AgentToolRequest,
    AgentToolSpec,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.online_blind import (
    assert_online_blind_payload,
    is_online_blind_decision_agent,
    sanitize_online_blind_payload,
)
from codigo.app.services.run_visualization import build_temporal_series_from_predictions
from codigo.app.services.temporal_model_readiness import (
    assess_temporal_model_readiness,
)

EVIDENCE_LOOKUP_TOOL = "evidence_lookup"
TEMPORAL_HEALTH_LOOKUP_TOOL = "temporal_health_lookup"
DEGRADATION_METRICS_LOOKUP_TOOL = "degradation_metrics_lookup"
TEMPORAL_MODEL_READINESS_TOOL = "temporal_model_readiness_assessor"
THRESHOLD_ANALYSIS_TOOL = "threshold_analysis"

EVIDENCE_LOOKUP_SECTIONS = {
    "project_context",
    "paths",
    "configs",
    "metrics",
    "temporal",
    "evaluation",
    "artifacts",
    "errors",
    "policy",
}

DEFAULT_EVIDENCE_LOOKUP_SECTIONS = [
    "project_context",
    "configs",
    "metrics",
    "temporal",
    "evaluation",
    "artifacts",
    "errors",
    "policy",
]

DEFAULT_THRESHOLD_QUANTILES = [0.90, 0.95, 0.975, 0.99, 1.0]
DEFAULT_TEMPORAL_RUN_LIMIT = 5
MAX_TEMPORAL_RUN_LIMIT = 20

ONLINE_BLIND_EVIDENCE_LOOKUP_SECTIONS = (
    "project_context",
    "configs",
    "policy",
)

DEGRADATION_METRIC_NAMES = [
    "degradation_available",
    "degradation_n_runs",
    "degradation_health_policy_id",
    "degradation_alert_policy_id",
    "degradation_persistent_alert_min_windows",
    "degradation_detected_before_failure_rate",
    "degradation_confirmed_degradation_before_failure_rate",
    "degradation_mean_lead_time_to_failure",
    "degradation_mean_persistent_lead_time_to_failure",
    "degradation_mean_false_alarm_rate_nominal",
    "degradation_mean_score_trend_spearman",
    "degradation_missed_runs",
    "degradation_missed_confirmed_degradation_runs",
    "degradation_mean_initial_final_separation",
    "degradation_mean_isolated_alert_points",
    "degradation_mean_alert_episodes",
    "degradation_mean_longest_alert_streak",
    "degradation_health_indicator_policy_id",
    "degradation_mean_health_index_drop",
    "degradation_mean_health_monotonicity",
    "degradation_mean_health_robustness",
    "degradation_mean_health_nominal_volatility",
    "degradation_mean_health_degradation_trend_strength",
    "degradation_mean_health_indicator_score",
    "degradation_health_trendability",
    "degradation_health_prognosability",
]

DEGRADATION_METRIC_ALIASES = {
    "degradation_detected_before_failure_rate": "detected_before_failure_rate",
    "degradation_confirmed_degradation_before_failure_rate": "confirmed_degradation_before_failure_rate",
    "degradation_mean_lead_time_to_failure": "mean_lead_time_to_failure",
    "degradation_mean_persistent_lead_time_to_failure": "mean_persistent_lead_time_to_failure",
    "degradation_mean_false_alarm_rate_nominal": "mean_false_alarm_rate_nominal",
    "degradation_mean_score_trend_spearman": "mean_score_trend_spearman",
    "degradation_missed_runs": "missed_runs",
    "degradation_missed_confirmed_degradation_runs": "missed_confirmed_degradation_runs",
    "degradation_mean_initial_final_separation": "mean_initial_final_separation",
    "degradation_mean_isolated_alert_points": "mean_isolated_alert_points",
    "degradation_mean_alert_episodes": "mean_alert_episodes",
    "degradation_mean_longest_alert_streak": "mean_longest_alert_streak",
    "degradation_mean_health_index_drop": "mean_health_index_drop",
    "degradation_mean_health_monotonicity": "mean_health_monotonicity",
    "degradation_mean_health_robustness": "mean_health_robustness",
    "degradation_mean_health_nominal_volatility": "mean_health_nominal_volatility",
    "degradation_mean_health_degradation_trend_strength": "mean_health_degradation_trend_strength",
    "degradation_mean_health_indicator_score": "mean_health_indicator_score",
    "degradation_health_trendability": "health_trendability",
    "degradation_health_prognosability": "health_prognosability",
}

ALL_TOOL_AGENTS: list[AgentToolAgent] = [
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
    "report_verifier",
    "researcher",
]


def agent_tool_catalog(
    *,
    agent_name: AgentToolAgent | None = None,
) -> list[AgentToolSpec]:
    """Devuelve las herramientas declaradas, filtradas por agente si procede."""

    specs = [
        _evidence_lookup_spec(),
        _temporal_health_lookup_spec(),
        _degradation_metrics_lookup_spec(),
        _temporal_model_readiness_spec(),
        _threshold_analysis_spec(),
    ]
    if agent_name is None:
        return specs
    return [spec for spec in specs if agent_name in spec.allowed_agents]


def get_agent_tool_spec(tool_name: str) -> AgentToolSpec:
    """Busca una herramienta declarada por nombre."""

    for spec in agent_tool_catalog():
        if spec.tool_name == tool_name:
            return spec
    raise ValueError(f"unknown agent tool: {tool_name}")


def run_agent_tool_request(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    """Ejecuta una herramienta segura y devuelve una observacion estructurada."""

    spec = get_agent_tool_spec(request.tool_name)
    if request.agent_name not in spec.allowed_agents:
        return _blocked_observation(
            request,
            f"{request.agent_name} is not allowed to use {request.tool_name}",
        )
    if request.run_id != state.run_id:
        return _blocked_observation(
            request,
            "tool request run_id does not match current state",
        )
    online_blind_block_reason = _online_blind_tool_block_reason(state, request)
    if online_blind_block_reason is not None:
        return _blocked_observation(request, online_blind_block_reason)
    if request.tool_name == EVIDENCE_LOOKUP_TOOL:
        try:
            return _run_evidence_lookup(state, request)
        except ValueError as exc:
            return _failed_observation(request, str(exc))
    if request.tool_name == TEMPORAL_HEALTH_LOOKUP_TOOL:
        try:
            return _run_temporal_health_lookup(state, request)
        except ValueError as exc:
            return _failed_observation(request, str(exc))
    if request.tool_name == DEGRADATION_METRICS_LOOKUP_TOOL:
        try:
            return _run_degradation_metrics_lookup(state, request)
        except ValueError as exc:
            return _failed_observation(request, str(exc))
    if request.tool_name == TEMPORAL_MODEL_READINESS_TOOL:
        try:
            return _run_temporal_model_readiness(state, request)
        except ValueError as exc:
            return _failed_observation(request, str(exc))
    if request.tool_name == THRESHOLD_ANALYSIS_TOOL:
        try:
            return _run_threshold_analysis(state, request)
        except ValueError as exc:
            return _failed_observation(request, str(exc))
    return _failed_observation(request, f"unsupported agent tool: {request.tool_name}")


def build_state_evidence_catalog(state: TFMStateModel) -> dict[str, Any]:
    """Construye un catalogo cerrado de evidencias citables de una run."""

    refs: list[str] = [
        "report:final_report",
        f"dataset:{state.project_context.dataset}",
        f"label_mode:{state.project_context.label_mode}",
        f"objective:{state.project_context.objective}",
        f"supervision_profile:{state.project_context.supervision_profile}",
        f"label_source:{state.project_context.label_source}",
        f"label_granularity:{state.project_context.label_granularity}",
        f"data_provenance:{state.project_context.data_provenance}",
    ]
    details: dict[str, Any] = {
        "run_id": state.run_id,
        "dataset": state.project_context.dataset,
        "label_mode": state.project_context.label_mode,
        "objective": state.project_context.objective,
        "report_path": state.report_path,
        "project_context": state.project_context.model_dump(mode="json"),
    }
    if state.cleaning_config is not None:
        refs.append("config:cleaning")
        details["cleaning_config"] = state.cleaning_config.model_dump(mode="json")
    if state.structuring_config is not None:
        refs.append("config:structuring")
        details["structuring_config"] = state.structuring_config.model_dump(
            mode="json"
        )
    if state.modeling_config is not None:
        refs.append("config:modeling")
        refs.append(f"model:{state.modeling_config.model_name}")
        details["modeling_config"] = state.modeling_config.model_dump(mode="json")
    if state.metrics is not None:
        metrics = state.metrics.model_dump(mode="json")
        details["metrics"] = metrics
        for name, value in metrics.items():
            if name != "extra" and value is not None:
                refs.append(f"metric:{name}")
        for name, value in metrics.get("extra", {}).items():
            if value is not None:
                refs.append(f"metric_extra:{name}")
                refs.extend(_metric_extra_evidence_aliases(name))
    else:
        refs.append("metrics:missing")
    temporal_evidence = _temporal_evidence_pack(state)
    refs.extend(temporal_evidence["evidence_refs"])
    details["temporal_evidence"] = temporal_evidence
    if state.evaluation is None:
        refs.append("evaluation:missing")
        details["evaluation"] = None
    else:
        refs.append(
            "evaluation:approved"
            if state.evaluation.approved
            else "evaluation:not_approved"
        )
        details["evaluation"] = state.evaluation.model_dump(mode="json")
        for index, limitation in enumerate(state.evaluation.limitations, start=1):
            refs.append(f"limitation:{index}")
            details[f"limitation:{index}"] = limitation
    details["dataset_policy"] = _dataset_policy_summary(state)
    if state.project_context.dataset == "nasa_ims_bearing":
        refs.append("policy:nasa_ims_methodology")
    else:
        refs.append("policy:local_dataset")
    artifacts = []
    for artifact in state.artifacts:
        ref = f"artifact:{artifact.name}"
        refs.append(ref)
        artifacts.append(
            {
                "ref": ref,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "producer": artifact.producer,
                "description": artifact.description,
                "metadata": artifact.metadata,
                "path": artifact.path,
            }
        )
    details["artifacts"] = artifacts
    if state.errors:
        details["errors"] = [error.model_dump(mode="json") for error in state.errors]
        for index, _error in enumerate(state.errors, start=1):
            refs.append(f"error:{index}")
    else:
        details["errors"] = []
    details["paths"] = {
        "raw_path": state.raw_path,
        "manifest_path": state.manifest_path,
        "profile_path": state.profile_path,
        "clean_path": state.clean_path,
        "tensor_path": state.tensor_path,
        "splits_path": state.splits_path,
        "report_path": state.report_path,
    }
    details["allowed_evidence_refs"] = sorted(set(refs))
    return details


def _evidence_lookup_spec() -> AgentToolSpec:
    return AgentToolSpec(
        tool_name=EVIDENCE_LOOKUP_TOOL,
        description=(
            "Consulta evidencia persistida en el estado de una run sin modificar "
            "datos ni artefactos."
        ),
        allowed_agents=ALL_TOOL_AGENTS,
        effect="read_only",
        input_schema={
            "include": sorted(EVIDENCE_LOOKUP_SECTIONS),
            "artifact_limit": "integer between 1 and 100",
        },
        output_schema={
            "summary": "human readable observation summary",
            "evidence_refs": "closed list of refs the agent may cite",
            "payload": "selected evidence sections",
        },
        human_summary_template=(
            "{agent_name} consulta evidencia de la run mediante evidence_lookup."
        ),
    )


def _temporal_health_lookup_spec() -> AgentToolSpec:
    return AgentToolSpec(
        tool_name=TEMPORAL_HEALTH_LOOKUP_TOOL,
        description=(
            "Consulta el estado temporal run-to-failure: salud actual, primer "
            "pico, aviso sostenido, episodios, racha maxima y fallo historico."
        ),
        allowed_agents=ALL_TOOL_AGENTS,
        effect="read_only",
        input_schema={
            "run_limit": (
                f"integer between 1 and {MAX_TEMPORAL_RUN_LIMIT}, default "
                f"{DEFAULT_TEMPORAL_RUN_LIMIT}"
            ),
        },
        output_schema={
            "summary": "human readable temporal health observation",
            "evidence_refs": "closed list of temporal refs the agent may cite",
            "payload": "focused temporal health evidence",
        },
        human_summary_template=(
            "{agent_name} consulta salud temporal mediante temporal_health_lookup."
        ),
    )


def _degradation_metrics_lookup_spec() -> AgentToolSpec:
    return AgentToolSpec(
        tool_name=DEGRADATION_METRICS_LOOKUP_TOOL,
        description=(
            "Consulta metricas principales del perfil run-to-failure y el "
            "contexto de etiquetas sin tratar F1 como criterio principal."
        ),
        allowed_agents=ALL_TOOL_AGENTS,
        effect="read_only",
        input_schema={},
        output_schema={
            "summary": "human readable degradation metrics observation",
            "evidence_refs": "closed list of metric refs the agent may cite",
            "payload": "focused degradation metric evidence",
        },
        human_summary_template=(
            "{agent_name} consulta metricas temporales mediante "
            "degradation_metrics_lookup."
        ),
    )


def _temporal_model_readiness_spec() -> AgentToolSpec:
    return AgentToolSpec(
        tool_name=TEMPORAL_MODEL_READINESS_TOOL,
        description=(
            "Evalua si la run tiene datos suficientes para autoencoder denso "
            "o RUL experimental sin entrenar modelos ni crear artefactos."
        ),
        allowed_agents=ALL_TOOL_AGENTS,
        effect="read_only",
        input_schema={},
        output_schema={
            "summary": "human readable readiness observation",
            "evidence_refs": "closed list of readiness refs the agent may cite",
            "payload": "structured readiness assessment",
        },
        human_summary_template=(
            "{agent_name} consulta readiness temporal para modelos avanzados."
        ),
    )


def _threshold_analysis_spec() -> AgentToolSpec:
    return AgentToolSpec(
        tool_name=THRESHOLD_ANALYSIS_TOOL,
        description=(
            "Analiza sensibilidad de umbral sobre predicciones persistidas sin "
            "recomendar una configuracion cerrada."
        ),
        allowed_agents=["modeler", "evaluator"],
        effect="read_only",
        input_schema={
            "primary_split": "split to score, default test",
            "threshold_source_split": "split used to derive candidate thresholds, default validation",
            "quantiles": "list of floats in (0, 1], default [0.90, 0.95, 0.975, 0.99, 1.0]",
            "near_threshold_limit": "integer between 1 and 20",
        },
        output_schema={
            "summary": "human readable cautionary threshold diagnostic",
            "candidate_metrics": "metrics by candidate score quantile",
            "near_threshold_windows": "closest windows to the current threshold",
        },
        human_summary_template=(
            "{agent_name} analiza sensibilidad de umbral mediante threshold_analysis."
        ),
    )


def _run_evidence_lookup(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    include = _requested_sections_for_request(state, request)
    artifact_limit = _artifact_limit(request.arguments.get("artifact_limit"))
    catalog = build_state_evidence_catalog(state)
    payload = _selected_evidence_payload(
        catalog,
        include=include,
        artifact_limit=artifact_limit,
    )
    evidence_refs = _selected_evidence_refs(catalog, include=include)
    if is_online_blind_decision_agent(state, request.agent_name):
        payload = _online_blind_evidence_payload(payload)
        evidence_refs = [
            ref
            for ref in evidence_refs
            if not any(
                token in ref.lower()
                for token in (
                    "failure",
                    "lead_time",
                    "relative_life",
                    "time_to_failure",
                )
            )
        ]
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:001",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="success",
        summary=(
            f"evidence_lookup devolvio {len(include)} seccion(es) y "
            f"{len(evidence_refs)} referencia(s) citables."
        ),
        evidence_refs=evidence_refs,
        payload=payload,
    )


def _run_temporal_health_lookup(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    run_limit = _temporal_run_limit(request.arguments.get("run_limit"))
    catalog = build_state_evidence_catalog(state)
    temporal = catalog["temporal_evidence"]
    runs = temporal["runs_sample"][:run_limit]
    payload = {
        "analysis_type": "temporal_health_lookup",
        "available": temporal["available"],
        "run_id": state.run_id,
        "dataset": catalog["dataset"],
        "supervision_profile": temporal["supervision_profile"],
        "label_context": temporal["label_context"],
        "series": temporal["series"],
        "primary_run": None if not runs else runs[0],
        "runs": runs,
        "run_limit": run_limit,
        "n_runs_returned": len(runs),
        "n_runs_total": (
            None
            if temporal["series"] is None
            else temporal["series"].get("n_runs_total")
        ),
        "warnings": temporal["warnings"],
        "interpretation_guardrail": (
            "temporal_health_lookup observa salud temporal. No estima RUL, no "
            "aprueba runs y no convierte un pico aislado en fallo real."
        ),
    }
    refs = _temporal_health_refs(catalog)
    refs.append(f"tool:{TEMPORAL_HEALTH_LOOKUP_TOOL}")
    summary = _temporal_health_summary(payload)
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:001",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="success",
        summary=summary,
        evidence_refs=sorted(set(refs)),
        payload=payload,
    )


def _run_degradation_metrics_lookup(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    catalog = build_state_evidence_catalog(state)
    temporal = catalog["temporal_evidence"]
    metrics = temporal["metrics"]
    payload = {
        "analysis_type": "degradation_metrics_lookup",
        "available": metrics["available"],
        "run_id": state.run_id,
        "dataset": catalog["dataset"],
        "supervision_profile": temporal["supervision_profile"],
        "label_context": temporal["label_context"],
        "metric_families": metrics["metric_families"],
        "primary_metrics": metrics["aliases"],
        "raw_metrics": metrics["raw"],
        "primary_names": metrics["primary_names"],
        "binary_metric_guardrail": (
            "F1, recall y precision pueden existir como proxy auxiliar, pero "
            "no son el criterio principal del perfil run-to-failure."
        ),
        "warnings": _degradation_metric_warnings(temporal),
        "interpretation_guardrail": (
            "degradation_metrics_lookup observa metricas temporales; no elige "
            "modelo, no aprueba la run y no presenta etiquetas proxy como "
            "oficiales."
        ),
    }
    refs = _degradation_metric_refs(catalog)
    refs.append(f"tool:{DEGRADATION_METRICS_LOOKUP_TOOL}")
    summary = _degradation_metrics_summary(payload)
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:001",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="success",
        summary=summary,
        evidence_refs=sorted(set(refs)),
        payload=payload,
    )


def _run_temporal_model_readiness(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    features_path = _features_path_for_readiness(state)
    predictions = _predictions_artifact(state)
    assessment = assess_temporal_model_readiness(
        features_path=features_path,
        predictions_path=None if predictions is None else predictions.path,
        splits_path=state.splits_path,
    )
    payload = assessment.model_dump(mode="json")
    payload["interpretation_guardrail"] = (
        "temporal_model_readiness_assessor no entrena modelos, no estima RUL "
        "y no autoriza arquitectura libre; solo evalua si procede proponer "
        "autoencoder_dense o RUL experimental bajo contratos cerrados."
    )
    refs = _readiness_refs(state, payload)
    refs.append(f"tool:{TEMPORAL_MODEL_READINESS_TOOL}")
    summary = _readiness_summary(payload)
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:001",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="success",
        summary=summary,
        evidence_refs=sorted(set(refs)),
        payload=payload,
    )


def _run_threshold_analysis(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> AgentToolObservation:
    artifact = _predictions_artifact(state)
    if artifact is None:
        return _blocked_observation(
            request,
            "threshold_analysis requires a predictions artifact in the current state",
        )
    primary_split = _string_argument(
        request.arguments.get("primary_split"),
        default="test",
        name="primary_split",
    )
    threshold_source_split = _string_argument(
        request.arguments.get("threshold_source_split"),
        default="validation",
        name="threshold_source_split",
    )
    quantiles = _threshold_quantiles(request.arguments.get("quantiles"))
    near_limit = _near_threshold_limit(request.arguments.get("near_threshold_limit"))
    rows = _read_prediction_rows(artifact.path)
    analysis = _threshold_analysis_payload(
        rows,
        primary_split=primary_split,
        threshold_source_split=threshold_source_split,
        quantiles=quantiles,
        near_threshold_limit=near_limit,
    )
    evidence_refs = [f"artifact:{artifact.name}", "tool:threshold_analysis"]
    if state.metrics is not None:
        evidence_refs.extend(
            ref
            for ref in build_state_evidence_catalog(state)["allowed_evidence_refs"]
            if ref.startswith("metric:") or ref.startswith("metric_extra:")
        )
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:001",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="success",
        summary=_threshold_analysis_summary(analysis),
        evidence_refs=sorted(set(evidence_refs)),
        payload=analysis,
    )


def _selected_evidence_payload(
    catalog: dict[str, Any],
    *,
    include: list[str],
    artifact_limit: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": catalog["run_id"],
        "dataset": catalog["dataset"],
        "requested_sections": include,
    }
    if "project_context" in include:
        payload["project_context"] = catalog["project_context"]
    if "paths" in include:
        payload["paths"] = catalog["paths"]
    if "configs" in include:
        payload["configs"] = {
            "cleaning_config": catalog.get("cleaning_config"),
            "structuring_config": catalog.get("structuring_config"),
            "modeling_config": catalog.get("modeling_config"),
        }
    if "metrics" in include:
        payload["metrics"] = catalog.get("metrics")
    if "temporal" in include:
        payload["temporal"] = catalog.get("temporal_evidence")
    if "evaluation" in include:
        payload["evaluation"] = catalog.get("evaluation")
        payload["limitations"] = [
            value
            for key, value in sorted(catalog.items())
            if key.startswith("limitation:")
        ]
    if "artifacts" in include:
        payload["artifacts"] = catalog["artifacts"][:artifact_limit]
        payload["artifact_limit"] = artifact_limit
        payload["n_artifacts_total"] = len(catalog["artifacts"])
    if "errors" in include:
        payload["errors"] = catalog["errors"]
    if "policy" in include:
        payload["dataset_policy"] = catalog["dataset_policy"]
    return payload


def _selected_evidence_refs(
    catalog: dict[str, Any],
    *,
    include: list[str],
) -> list[str]:
    refs = set()
    if "project_context" in include:
        refs.update(
            [
                f"dataset:{catalog['dataset']}",
                f"label_mode:{catalog['label_mode']}",
                f"objective:{catalog['objective']}",
                f"supervision_profile:{catalog['project_context'].get('supervision_profile')}",
                f"label_source:{catalog['project_context'].get('label_source')}",
                f"label_granularity:{catalog['project_context'].get('label_granularity')}",
                f"data_provenance:{catalog['project_context'].get('data_provenance')}",
            ]
        )
    if "configs" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("config:") or ref.startswith("model:")
        )
    if "metrics" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("metric:")
            or ref.startswith("metric_extra:")
            or ref == "metrics:missing"
        )
    if "temporal" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("temporal:")
            or ref.startswith("supervision_profile:")
            or ref.startswith("label_source:")
            or ref.startswith("label_granularity:")
            or ref.startswith("metric:degradation_")
            or ref.startswith("metric_extra:degradation_")
            or ref in {
                "metric:detected_before_failure_rate",
                "metric:confirmed_degradation_before_failure_rate",
                "metric:mean_lead_time_to_failure",
                "metric:mean_persistent_lead_time_to_failure",
                "metric:mean_false_alarm_rate_nominal",
                "metric:mean_score_trend_spearman",
                "metric:missed_runs",
                "metric:missed_confirmed_degradation_runs",
                "metric:mean_initial_final_separation",
                "metric:mean_isolated_alert_points",
                "metric:mean_alert_episodes",
                "metric:mean_longest_alert_streak",
                "metric:mean_health_index_drop",
                "metric:mean_health_monotonicity",
                "metric:mean_health_robustness",
                "metric:mean_health_nominal_volatility",
                "metric:mean_health_degradation_trend_strength",
                "metric:mean_health_indicator_score",
                "metric:health_trendability",
                "metric:health_prognosability",
                "health:indicator_available",
                "health:monotonicity",
                "health:robustness",
                "health:onset_confirmed",
                "health:dominant_evidence",
            }
        )
    if "evaluation" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("evaluation:") or ref.startswith("limitation:")
        )
    if "artifacts" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("artifact:") or ref == "report:final_report"
        )
    if "errors" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("error:")
        )
    if "policy" in include:
        refs.update(
            ref
            for ref in catalog["allowed_evidence_refs"]
            if ref.startswith("policy:")
        )
    return sorted(refs)


def _online_blind_tool_block_reason(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> str | None:
    if not is_online_blind_decision_agent(state, request.agent_name):
        return None
    if request.tool_name == EVIDENCE_LOOKUP_TOOL:
        raw_sections = request.arguments.get("include")
        if raw_sections is None:
            return None
        try:
            sections = _requested_sections(raw_sections)
        except ValueError:
            return None
        forbidden = sorted(
            set(sections) - set(ONLINE_BLIND_EVIDENCE_LOOKUP_SECTIONS)
        )
        if not forbidden:
            return None
        return (
            "online_blind decision agents cannot inspect retrospective evidence "
            "sections: "
            + ", ".join(forbidden)
        )
    return (
        f"{request.tool_name} is retrospective or reads held-out monitoring "
        "evidence and is unavailable to online_blind decision agents"
    )


def _requested_sections_for_request(
    state: TFMStateModel,
    request: AgentToolRequest,
) -> list[str]:
    raw_sections = request.arguments.get("include")
    if (
        raw_sections is None
        and is_online_blind_decision_agent(state, request.agent_name)
    ):
        return list(ONLINE_BLIND_EVIDENCE_LOOKUP_SECTIONS)
    return _requested_sections(raw_sections)


def _online_blind_evidence_payload(payload: dict[str, Any]) -> dict[str, Any]:
    project_context = payload.get("project_context")
    if isinstance(project_context, dict):
        allowed_context_fields = {
            "dataset",
            "machine_type",
            "signal_type",
            "objective",
            "target_sample_rate_hz",
            "main_channel",
            "label_mode",
            "supervision_profile",
            "label_granularity",
            "label_source",
            "data_provenance",
        }
        payload["project_context"] = {
            key: value
            for key, value in project_context.items()
            if key in allowed_context_fields
        }
    dataset_policy = payload.get("dataset_policy")
    if isinstance(dataset_policy, dict):
        payload["dataset_policy"] = {
            key: value
            for key, value in dataset_policy.items()
            if key in {"dataset", "policy_ref", "summary"}
        }
    payload["evidence_view"] = "online_blind"
    sanitized = sanitize_online_blind_payload(payload)
    assert_online_blind_payload(sanitized)
    return sanitized


def _requested_sections(raw: object) -> list[str]:
    if raw is None:
        return list(DEFAULT_EVIDENCE_LOOKUP_SECTIONS)
    if not isinstance(raw, list):
        raise ValueError("evidence_lookup include must be a list")
    sections = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("evidence_lookup include values must be strings")
        if item not in EVIDENCE_LOOKUP_SECTIONS:
            raise ValueError(f"unknown evidence_lookup section: {item}")
        sections.append(item)
    if not sections:
        raise ValueError("evidence_lookup include cannot be empty")
    return list(dict.fromkeys(sections))


def _artifact_limit(raw: object) -> int:
    if raw is None:
        return 50
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("evidence_lookup artifact_limit must be an integer")
    if raw < 1 or raw > 100:
        raise ValueError("evidence_lookup artifact_limit must be between 1 and 100")
    return raw


def _dataset_policy_summary(state: TFMStateModel) -> dict[str, Any]:
    if state.project_context.dataset == "nasa_ims_bearing":
        return {
            "dataset": "nasa_ims_bearing",
            "policy_ref": "policy:nasa_ims_methodology",
            "summary": (
                "NASA IMS requiere politica temporal o etiquetas controladas "
                "antes de presentar resultados supervisados como evidencia."
            ),
            "notes": state.project_context.notes,
        }
    return {
        "dataset": state.project_context.dataset,
        "policy_ref": "policy:local_dataset",
        "summary": (
            "Dataset local permitido por la politica actual del runner comun."
        ),
        "notes": state.project_context.notes,
    }


def _temporal_evidence_pack(state: TFMStateModel) -> dict[str, Any]:
    artifact = _predictions_artifact(state)
    metrics = _degradation_metrics_payload(state)
    should_read_temporal_predictions = (
        artifact is not None
        and (
            state.project_context.supervision_profile == "run_to_failure_degradation"
            or metrics["available"]
            or metrics.get("metric_families") == "run_to_failure_degradation"
            or (
                isinstance(metrics.get("metric_families"), str)
                and "run_to_failure_degradation" in metrics["metric_families"]
            )
        )
    )
    temporal_series = (
        None
        if not should_read_temporal_predictions
        else build_temporal_series_from_predictions(artifact.path, max_points=250)
    )
    run_summaries = (
        []
        if temporal_series is None
        else [_temporal_run_summary(run) for run in temporal_series.runs[:5]]
    )
    warnings = _temporal_evidence_warnings(
        state,
        temporal_series=temporal_series,
        predictions_available=artifact is not None,
        run_summaries=run_summaries,
    )
    refs = _temporal_evidence_refs(
        state,
        metrics=metrics,
        temporal_series=temporal_series,
        run_summaries=run_summaries,
        predictions_available=artifact is not None,
    )
    return {
        "available": bool(temporal_series is not None and temporal_series.available),
        "supervision_profile": state.project_context.supervision_profile,
        "label_context": {
            "label_mode": state.project_context.label_mode,
            "label_source": state.project_context.label_source,
            "label_granularity": state.project_context.label_granularity,
            "proxy_warning": state.project_context.label_source
            in {"none", "temporal_proxy", "synthetic"},
        },
        "cleaner_context": _cleaner_temporal_context(state),
        "metrics": metrics,
        "series": (
            None
            if temporal_series is None
            else {
                "available": temporal_series.available,
                "x_axis": temporal_series.x_axis,
                "n_runs_total": temporal_series.n_runs_total,
                "n_points_total": temporal_series.n_points_total,
                "warnings": temporal_series.warnings,
            }
        ),
        "temporal_policy": (
            None
            if temporal_series is None or not run_summaries
            else {
                "health_policy_id": run_summaries[0]["policy"][
                    "health_policy_id"
                ],
                "alert_policy_id": run_summaries[0]["policy"][
                    "alert_policy_id"
                ],
                "health_indicator_policy_id": run_summaries[0]["policy"][
                    "health_indicator_policy_id"
                ],
                "persistent_alert_min_windows": run_summaries[0]["policy"][
                    "persistent_alert_min_windows"
                ],
            }
        ),
        "primary_run": None if not run_summaries else run_summaries[0],
        "runs_sample": run_summaries,
        "n_runs_returned": len(run_summaries),
        "warnings": warnings,
        "agent_guidance": _temporal_agent_guidance(),
        "evidence_refs": sorted(set(refs)),
    }


def _degradation_metrics_payload(state: TFMStateModel) -> dict[str, Any]:
    extra = {} if state.metrics is None else state.metrics.extra
    raw = {
        name: extra.get(name)
        for name in DEGRADATION_METRIC_NAMES
        if extra.get(name) is not None
    }
    aliases = {
        alias: extra.get(name)
        for name, alias in DEGRADATION_METRIC_ALIASES.items()
        if extra.get(name) is not None
    }
    return {
        "available": bool(extra.get("degradation_available")),
        "metric_families": extra.get("metric_families"),
        "raw": raw,
        "aliases": aliases,
        "primary_names": [
            "confirmed_degradation_before_failure_rate",
            "mean_persistent_lead_time_to_failure",
            "mean_health_index_drop",
            "mean_health_monotonicity",
            "mean_health_robustness",
            "detected_before_failure_rate",
            "mean_lead_time_to_failure",
            "mean_false_alarm_rate_nominal",
            "mean_score_trend_spearman",
            "missed_runs",
        ],
    }


def _temporal_run_summary(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "x_axis": run.x_axis,
        "n_windows": run.n_points_total,
        "n_points_sampled": run.n_points_sampled,
        "threshold": run.threshold,
        "policy": {
            "health_policy_id": run.health_policy_id,
            "alert_policy_id": run.alert_policy_id,
            "health_indicator_policy_id": run.health_indicator_policy_id,
            "persistent_alert_min_windows": run.persistent_alert_min_windows,
        },
        "current": {
            "x": run.current_x,
            "time": run.current_time,
            "time_to_failure_seconds": run.current_time_to_failure_seconds,
            "health_state": run.current_health_state,
            "health_index": run.current_health_index,
            "health_index_smoothed": run.current_health_index_smoothed,
            "health_trend": run.current_health_trend,
            "risk_index": run.current_risk_index,
            "risk_index_smoothed": run.current_risk_index_smoothed,
            "reason": run.current_state_reason,
        },
        "health_indicator": {
            "initial_health_index": run.health_initial_index,
            "final_health_index": run.health_final_index,
            "health_index_drop": run.health_index_drop,
            "health_index_drop_ratio": run.health_index_drop_ratio,
            "health_slope": run.health_slope,
            "health_trend_spearman": run.health_trend_spearman,
            "health_degradation_trend_strength": (
                run.health_degradation_trend_strength
            ),
            "health_monotonicity": run.health_monotonicity,
            "health_robustness": run.health_robustness,
            "health_nominal_volatility": run.health_nominal_volatility,
            "health_indicator_score": run.health_indicator_score,
            "health_dominant_evidence": run.health_dominant_evidence,
            "health_indicator_status": run.health_indicator_status,
        },
        "first_spike": {
            "x": run.first_alert_x,
            "time": run.first_alert_time,
            "time_to_failure_seconds": run.first_alert_time_to_failure_seconds,
        },
        "first_persistent_alert": {
            "x": run.first_persistent_alert_x,
            "time": run.first_persistent_alert_time,
            "time_to_failure_seconds": (
                run.first_persistent_alert_time_to_failure_seconds
            ),
            "min_consecutive_windows": run.persistent_alert_min_windows,
        },
        "onset_confirmed": {
            "confirmed": run.onset_confirmed,
            "x": run.onset_confirmed_x,
            "time": run.onset_confirmed_time,
            "time_to_failure_seconds": (
                run.onset_confirmed_time_to_failure_seconds
            ),
            "policy_ref": f"policy:{run.health_policy_id}",
        },
        "episodes": {
            "alert_points": run.alert_points,
            "warning_points": run.warning_points,
            "critical_points": run.critical_points,
            "isolated_alert_points": run.isolated_alert_points,
            "alert_episodes": run.alert_episodes,
            "longest_alert_streak": run.longest_alert_streak,
        },
        "failure": {
            "x": run.failure_x,
            "time": run.failure_time,
            "reference": run.failure_reference,
        },
    }


def _cleaner_temporal_context(state: TFMStateModel) -> dict[str, Any]:
    return {
        "role": "signal_quality_gate_for_temporal_monitoring",
        "main_channel": state.project_context.main_channel,
        "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
        "profile_path": state.profile_path,
        "clean_path": state.clean_path,
        "selected_channel": (
            None
            if state.cleaning_config is None
            else state.cleaning_config.selected_channel
        ),
        "normalization": (
            None if state.cleaning_config is None else state.cleaning_config.normalization
        ),
        "why_it_matters": (
            "El cleaner fija canal, frecuencia y calidad de senal; esas "
            "decisiones condicionan continuidad temporal, comparabilidad de "
            "ventanas y estabilidad del score de degradacion."
        ),
    }


def _temporal_agent_guidance() -> dict[str, str]:
    return {
        "cleaner": (
            "Razonar sobre canal, remuestreo, no finitos y normalizacion como "
            "precondiciones de una trayectoria temporal estable."
        ),
        "modeler": (
            "Elegir modelo y politica de score por deteccion temprana, "
            "persistencia, tendencia y coste de falsas alarmas, no por F1."
        ),
        "evaluator": (
            "Separar pico aislado, aviso sostenido y fallo historico; no aprobar "
            "solo por un umbral puntual."
        ),
        "report_writer": (
            "Explicar el resultado como monitorizacion run-to-failure con "
            "etiquetas proxy si aplica."
        ),
        "report_verifier": (
            "Bloquear afirmaciones de RUL o etiquetas oficiales no soportadas."
        ),
    }


def _temporal_health_refs(catalog: dict[str, Any]) -> list[str]:
    return [
        ref
        for ref in catalog["allowed_evidence_refs"]
        if ref.startswith("temporal:")
        or ref.startswith("health:")
        or ref.startswith("supervision_profile:")
        or ref.startswith("label_source:")
        or ref.startswith("label_granularity:")
        or ref.startswith("artifact:")
    ]


def _degradation_metric_refs(catalog: dict[str, Any]) -> list[str]:
    return [
        ref
        for ref in catalog["allowed_evidence_refs"]
        if ref.startswith("metric:degradation_")
        or ref.startswith("metric_extra:degradation_")
        or ref.startswith("health:")
        or ref.startswith("supervision_profile:")
        or ref.startswith("label_source:")
        or ref.startswith("label_granularity:")
        or ref in {
            "metric:detected_before_failure_rate",
            "metric:confirmed_degradation_before_failure_rate",
            "metric:mean_lead_time_to_failure",
            "metric:mean_persistent_lead_time_to_failure",
            "metric:mean_false_alarm_rate_nominal",
            "metric:mean_score_trend_spearman",
            "metric:missed_runs",
            "metric:missed_confirmed_degradation_runs",
            "metric:mean_initial_final_separation",
            "metric:mean_isolated_alert_points",
            "metric:mean_alert_episodes",
            "metric:mean_longest_alert_streak",
            "metric:mean_health_index_drop",
            "metric:mean_health_monotonicity",
            "metric:mean_health_robustness",
            "metric:mean_health_nominal_volatility",
            "metric:mean_health_degradation_trend_strength",
            "metric:mean_health_indicator_score",
            "metric:health_trendability",
            "metric:health_prognosability",
        }
    ]


def _temporal_health_summary(payload: dict[str, Any]) -> str:
    if not payload["available"]:
        return (
            "temporal_health_lookup no encontro una serie temporal disponible; "
            "la observacion queda limitada a contexto y advertencias."
        )
    primary = payload.get("primary_run") or {}
    current = primary.get("current") or {}
    persistent = primary.get("first_persistent_alert") or {}
    return (
        "temporal_health_lookup observo estado "
        f"{current.get('health_state')} con primer aviso sostenido en "
        f"{persistent.get('x')} y {payload['n_runs_returned']} run(s) devuelta(s)."
    )


def _degradation_metrics_summary(payload: dict[str, Any]) -> str:
    if not payload["available"]:
        return (
            "degradation_metrics_lookup no encontro metricas temporales "
            "disponibles para el perfil run-to-failure."
        )
    metrics = payload["primary_metrics"]
    confirmed = metrics.get("confirmed_degradation_before_failure_rate")
    lead_time = metrics.get("mean_persistent_lead_time_to_failure")
    if lead_time is None:
        lead_time = metrics.get("mean_lead_time_to_failure")
    false_alarm = metrics.get("mean_false_alarm_rate_nominal")
    trend = metrics.get("mean_score_trend_spearman")
    health_drop = metrics.get("mean_health_index_drop")
    health_monotonicity = metrics.get("mean_health_monotonicity")
    return (
        "degradation_metrics_lookup devolvio metricas temporales primarias: "
        f"onset_confirmado={confirmed}, lead_time={lead_time}, falsas_alarmas={false_alarm}, "
        f"tendencia={trend}, caida_hi={health_drop}, monotonicidad_hi={health_monotonicity}."
    )


def _readiness_summary(payload: dict[str, Any]) -> str:
    if not payload.get("available"):
        return (
            "temporal_model_readiness_assessor no encontro features suficientes; "
            "autoencoder y RUL quedan bloqueados."
        )
    return (
        "temporal_model_readiness_assessor devolvio readiness="
        f"{payload.get('readiness_level')}, autoencoder_ready="
        f"{payload.get('autoencoder_ready')}, rul_ready={payload.get('rul_ready')} "
        f"y siguiente_experimento={payload.get('recommended_next_experiment')}."
    )


def _degradation_metric_warnings(temporal: dict[str, Any]) -> list[str]:
    warnings = list(temporal["warnings"])
    if not temporal["metrics"]["available"]:
        warnings.append("Faltan metricas temporales de degradacion.")
    if temporal["label_context"]["proxy_warning"]:
        warnings.append(
            "Las metricas se apoyan en etiquetas proxy o experimentales; no "
            "deben presentarse como ground truth oficial por ventana."
        )
    return list(dict.fromkeys(warnings))


def _readiness_refs(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> list[str]:
    refs = [
        "readiness:temporal_model_readiness",
        f"readiness:level:{payload.get('readiness_level')}",
        (
            "readiness:autoencoder_ready"
            if payload.get("autoencoder_ready")
            else "readiness:autoencoder_blocked"
        ),
        (
            "readiness:rul_ready"
            if payload.get("rul_ready")
            else "readiness:rul_blocked"
        ),
        f"readiness:cost:{payload.get('estimated_cost_level')}",
        f"readiness:leakage:{payload.get('leakage_risk')}",
        f"supervision_profile:{state.project_context.supervision_profile}",
    ]
    if payload.get("features_path"):
        refs.append("artifact:features")
    if payload.get("predictions_path"):
        refs.append("artifact:model_predictions")
    for reason in payload.get("blocked_reasons") or []:
        refs.append(f"readiness:blocker:{reason}")
    for reason in payload.get("caution_reasons") or []:
        refs.append(f"readiness:caution:{reason}")
    return refs


def _temporal_evidence_warnings(
    state: TFMStateModel,
    *,
    temporal_series: Any | None,
    predictions_available: bool,
    run_summaries: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    is_temporal_profile = (
        state.project_context.supervision_profile == "run_to_failure_degradation"
    )
    if not is_temporal_profile:
        warnings.append(
            "El perfil actual no es run_to_failure_degradation; la evidencia "
            "temporal es auxiliar o no aplicable."
        )
    if state.project_context.label_source in {"none", "temporal_proxy", "synthetic"}:
        warnings.append(
            "Las etiquetas por ventana no son oficiales; deben tratarse como "
            "proxy o evidencia experimental."
        )
    if is_temporal_profile:
        warnings.append(
            "RUL no esta estimado en este hito; solo se expone tiempo a fallo "
            "historico cuando existe en el replay."
        )
    if not predictions_available:
        warnings.append(
            "No hay artefacto de predicciones; no se puede resumir la trayectoria."
        )
    if temporal_series is not None:
        warnings.extend(temporal_series.warnings)
    if run_summaries:
        first = run_summaries[0]
        first_spike = first["first_spike"]["x"]
        persistent = first["first_persistent_alert"]["x"]
        isolated = first["episodes"]["isolated_alert_points"]
        if first_spike is not None and persistent is None:
            warnings.append(
                "Existe primer pico de alerta pero no aviso sostenido con la "
                "persistencia minima configurada."
            )
        if isolated:
            warnings.append(
                "Hay picos aislados; no deben interpretarse como fallo real sin "
                "persistencia temporal."
            )
    return warnings


def _temporal_evidence_refs(
    state: TFMStateModel,
    *,
    metrics: dict[str, Any],
    temporal_series: Any | None,
    run_summaries: list[dict[str, Any]],
    predictions_available: bool,
) -> list[str]:
    refs: list[str] = ["temporal:cleaner_signal_quality_context"]
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        refs.append("temporal:run_to_failure_profile")
        refs.append("temporal:rul_not_estimated")
    else:
        refs.append("temporal:not_run_to_failure_profile")
    if predictions_available:
        refs.append("temporal:predictions_available")
    else:
        refs.append("temporal:predictions_missing")
    if temporal_series is None or not temporal_series.available:
        refs.append("temporal:unavailable")
    else:
        refs.extend(
            [
                "temporal:series_available",
                "temporal:current_health_state",
                "temporal:health_policy",
                "temporal:alert_policy",
                "temporal:health_indicator_policy",
                "temporal:alert_episodes",
                "temporal:longest_alert_streak",
                "temporal:failure_reference",
                "health:indicator_available",
            ]
        )
    for name in metrics.get("raw", {}):
        refs.append(f"metric_extra:{name}")
        refs.extend(_metric_extra_evidence_aliases(name))
    if run_summaries:
        first = run_summaries[0]
        if first["first_spike"]["x"] is not None:
            refs.extend(["temporal:first_spike", "temporal:first_alert"])
        if first["first_persistent_alert"]["x"] is not None:
            refs.append("temporal:first_persistent_alert")
        if first["onset_confirmed"]["confirmed"]:
            refs.append("temporal:onset_confirmed")
            refs.append("health:onset_confirmed")
        health = first.get("health_indicator") or {}
        if health.get("health_monotonicity") is not None:
            refs.append("health:monotonicity")
        if health.get("health_robustness") is not None:
            refs.append("health:robustness")
        if health.get("health_dominant_evidence") is not None:
            refs.append("health:dominant_evidence")
        if first["episodes"]["isolated_alert_points"]:
            refs.append("temporal:isolated_alert_points")
    return refs


def _metric_extra_evidence_aliases(name: str) -> list[str]:
    refs: list[str] = []
    if name.startswith("degradation_"):
        refs.append(f"metric:{name}")
    alias = DEGRADATION_METRIC_ALIASES.get(name)
    if alias is not None:
        refs.append(f"metric:{alias}")
    return refs


def _predictions_artifact(state: TFMStateModel):
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == "predictions":
            return artifact
    return None


def _features_path_for_readiness(state: TFMStateModel) -> str | None:
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == "features":
            return artifact.path
    if state.tensor_path:
        return str(Path(state.tensor_path).with_name("windows_features.csv"))
    return None


def _read_prediction_rows(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            required = {"split", "anomaly_score"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "predictions are missing columns: " + ", ".join(sorted(missing))
                )
            rows = [
                {
                    **row,
                    "anomaly_score": float(row["anomaly_score"]),
                    "target": _int_or_none(row.get("target")),
                    "threshold": _float_or_none(row.get("threshold")),
                }
                for row in reader
            ]
    except OSError as exc:
        raise ValueError(f"cannot read predictions artifact: {path}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid predictions artifact: {exc}") from exc
    if not rows:
        raise ValueError("predictions artifact is empty")
    return rows


def _threshold_analysis_payload(
    rows: list[dict[str, Any]],
    *,
    primary_split: str,
    threshold_source_split: str,
    quantiles: list[float],
    near_threshold_limit: int,
) -> dict[str, Any]:
    primary_rows = [row for row in rows if row.get("split") == primary_split]
    if not primary_rows:
        raise ValueError(f"primary split not found or empty: {primary_split}")
    source_rows = [
        row for row in rows if row.get("split") == threshold_source_split
    ]
    threshold_source_fallback = False
    if not source_rows:
        source_rows = primary_rows
        threshold_source_fallback = True
    source_scores = sorted(float(row["anomaly_score"]) for row in source_rows)
    current_threshold = _current_threshold(primary_rows)
    candidate_metrics = [
        _candidate_threshold_metrics(
            primary_rows,
            quantile=quantile,
            threshold=_quantile(source_scores, quantile),
        )
        for quantile in quantiles
    ]
    return {
        "analysis_type": "threshold_sensitivity",
        "primary_split": primary_split,
        "threshold_source_split": threshold_source_split,
        "threshold_source_fallback": threshold_source_fallback,
        "n_primary_rows": len(primary_rows),
        "n_threshold_source_rows": len(source_rows),
        "current_threshold": current_threshold,
        "candidate_metrics": candidate_metrics,
        "score_summary_by_target": _score_summary_by_target(primary_rows),
        "near_threshold_windows": _near_threshold_windows(
            primary_rows,
            current_threshold=current_threshold,
            limit=near_threshold_limit,
        ),
        "interpretation_guardrail": (
            "This tool diagnoses threshold sensitivity only. It does not select "
            "a threshold, approve a run or replace model-family comparison."
        ),
    }


def _candidate_threshold_metrics(
    rows: list[dict[str, Any]],
    *,
    quantile: float,
    threshold: float,
) -> dict[str, Any]:
    predictions = [
        {
            "target": row["target"],
            "predicted": 1 if float(row["anomaly_score"]) > threshold else 0,
        }
        for row in rows
    ]
    labeled = [item for item in predictions if item["target"] in {0, 1}]
    result: dict[str, Any] = {
        "quantile": quantile,
        "threshold": threshold,
        "predicted_anomalies": sum(item["predicted"] for item in predictions),
        "n_rows": len(rows),
    }
    if not labeled:
        result["metrics_available"] = False
        return result
    tp = sum(1 for item in labeled if item["target"] == 1 and item["predicted"] == 1)
    fp = sum(1 for item in labeled if item["target"] == 0 and item["predicted"] == 1)
    tn = sum(1 for item in labeled if item["target"] == 0 and item["predicted"] == 0)
    fn = sum(1 for item in labeled if item["target"] == 1 and item["predicted"] == 0)
    precision = None if tp + fp == 0 else tp / (tp + fp)
    recall = None if tp + fn == 0 else tp / (tp + fn)
    fpr = None if fp + tn == 0 else fp / (fp + tn)
    f1_score = (
        None
        if precision is None or recall is None or precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    result.update(
        {
            "metrics_available": True,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "false_positive_rate": fpr,
            "confusion_matrix": {
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "tp": tp,
            },
        }
    )
    return result


def _score_summary_by_target(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        target = row.get("target")
        key = "unlabeled" if target not in {0, 1} else str(target)
        groups.setdefault(key, []).append(float(row["anomaly_score"]))
    return {key: _score_stats(values) for key, values in sorted(groups.items())}


def _score_stats(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": _quantile(ordered, 0.5),
        "max": ordered[-1],
    }


def _near_threshold_windows(
    rows: list[dict[str, Any]],
    *,
    current_threshold: float | None,
    limit: int,
) -> list[dict[str, Any]]:
    if current_threshold is None:
        return []
    ranked = sorted(
        rows,
        key=lambda row: abs(float(row["anomaly_score"]) - current_threshold),
    )
    return [
        {
            "window_id": row.get("window_id"),
            "file_id": row.get("file_id"),
            "split": row.get("split"),
            "target": row.get("target"),
            "label": row.get("label"),
            "anomaly_score": float(row["anomaly_score"]),
            "margin_to_current_threshold": (
                float(row["anomaly_score"]) - current_threshold
            ),
        }
        for row in ranked[:limit]
    ]


def _threshold_analysis_summary(analysis: dict[str, Any]) -> str:
    candidates = analysis["candidate_metrics"]
    available = [item for item in candidates if item.get("metrics_available")]
    if not available:
        return (
            "threshold_analysis genero sensibilidad de scores, pero no hay "
            "etiquetas validas para recalcular metricas por umbral."
        )
    best_f1 = max(
        (item for item in available if item.get("f1_score") is not None),
        key=lambda item: item["f1_score"],
        default=None,
    )
    if best_f1 is None:
        return (
            "threshold_analysis comparo umbrales candidatos sin seleccionar una "
            "configuracion; las metricas disponibles son incompletas."
        )
    return (
        "threshold_analysis comparo sensibilidad por cuantiles sin recomendar "
        "un umbral cerrado. Mejor F1 observado en el barrido: "
        f"{best_f1['f1_score']:.4f} con quantile={best_f1['quantile']}."
    )


def _current_threshold(rows: list[dict[str, Any]]) -> float | None:
    for row in rows:
        if row.get("threshold") is not None:
            return float(row["threshold"])
    return None


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("cannot compute quantile for empty values")
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return float(values[lower] * (1 - weight) + values[upper] * weight)


def _threshold_quantiles(raw: object) -> list[float]:
    if raw is None:
        return list(DEFAULT_THRESHOLD_QUANTILES)
    if not isinstance(raw, list):
        raise ValueError("threshold_analysis quantiles must be a list")
    values = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise ValueError("threshold_analysis quantiles must be numeric")
        value = float(item)
        if not 0.0 < value <= 1.0:
            raise ValueError("threshold_analysis quantiles must be in (0, 1]")
        values.append(value)
    if not values:
        raise ValueError("threshold_analysis quantiles cannot be empty")
    return list(dict.fromkeys(values))


def _near_threshold_limit(raw: object) -> int:
    if raw is None:
        return 5
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("threshold_analysis near_threshold_limit must be an integer")
    if raw < 1 or raw > 20:
        raise ValueError(
            "threshold_analysis near_threshold_limit must be between 1 and 20"
        )
    return raw


def _temporal_run_limit(raw: object) -> int:
    if raw is None:
        return DEFAULT_TEMPORAL_RUN_LIMIT
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("temporal_health_lookup run_limit must be an integer")
    if raw < 1 or raw > MAX_TEMPORAL_RUN_LIMIT:
        raise ValueError(
            "temporal_health_lookup run_limit must be between 1 and "
            f"{MAX_TEMPORAL_RUN_LIMIT}"
        )
    return raw


def _string_argument(raw: object, *, default: str, name: str) -> str:
    if raw is None:
        return default
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"threshold_analysis {name} must be a non-empty string")
    return raw.strip()


def _float_or_none(value: object) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _int_or_none(value: object) -> int | None:
    if value in {None, ""}:
        return None
    return int(float(value))


def _blocked_observation(
    request: AgentToolRequest,
    reason: str,
) -> AgentToolObservation:
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:blocked",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="blocked",
        summary="La herramienta no se ejecuto por politica de uso.",
        errors=[reason],
    )


def _failed_observation(
    request: AgentToolRequest,
    reason: str,
) -> AgentToolObservation:
    return AgentToolObservation(
        observation_id=f"{request.request_id}:observation:failed",
        request_id=request.request_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        tool_name=request.tool_name,
        status="failed",
        summary="La herramienta no pudo devolver una observacion valida.",
        errors=[reason],
    )
