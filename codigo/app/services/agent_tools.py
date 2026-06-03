"""Catalogo minimo de herramientas seguras para agentes."""

from __future__ import annotations

import csv
from typing import Any

from codigo.app.schemas.reasoning import (
    AgentToolAgent,
    AgentToolObservation,
    AgentToolRequest,
    AgentToolSpec,
)
from codigo.app.schemas.state import TFMStateModel

EVIDENCE_LOOKUP_TOOL = "evidence_lookup"
THRESHOLD_ANALYSIS_TOOL = "threshold_analysis"

EVIDENCE_LOOKUP_SECTIONS = {
    "project_context",
    "paths",
    "configs",
    "metrics",
    "evaluation",
    "artifacts",
    "errors",
    "policy",
}

DEFAULT_EVIDENCE_LOOKUP_SECTIONS = [
    "project_context",
    "configs",
    "metrics",
    "evaluation",
    "artifacts",
    "errors",
    "policy",
]

DEFAULT_THRESHOLD_QUANTILES = [0.90, 0.95, 0.975, 0.99, 1.0]

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

    specs = [_evidence_lookup_spec(), _threshold_analysis_spec()]
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
    if request.tool_name == EVIDENCE_LOOKUP_TOOL:
        try:
            return _run_evidence_lookup(state, request)
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
    else:
        refs.append("metrics:missing")
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
    include = _requested_sections(request.arguments.get("include"))
    artifact_limit = _artifact_limit(request.arguments.get("artifact_limit"))
    catalog = build_state_evidence_catalog(state)
    payload = _selected_evidence_payload(
        catalog,
        include=include,
        artifact_limit=artifact_limit,
    )
    evidence_refs = _selected_evidence_refs(catalog, include=include)
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
            if ref.startswith("metric:")
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
            if ref.startswith("metric:") or ref == "metrics:missing"
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


def _predictions_artifact(state: TFMStateModel):
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == "predictions":
            return artifact
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
