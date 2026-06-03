"""Generacion determinista del informe tecnico final."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from codigo.app.schemas.agent_decisions import ReportDecision, ReportSection
from codigo.app.schemas.executor_results import ReportExecutorResult
from codigo.app.schemas.state import ArtifactRef, PipelineError, TFMStateModel


def generate_technical_report(
    state: TFMStateModel,
    decision: ReportDecision,
) -> ReportExecutorResult:
    """Escribe un informe Markdown usando una decision validada."""

    started_at = datetime.now(UTC)
    report_path = Path(decision.output_path)
    try:
        if decision.output_format != "markdown":
            raise ValueError("only markdown reports are supported in the local MVP")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_render_report(state, decision), encoding="utf-8")
        artifact = ArtifactRef(
            name="final_report",
            artifact_type="report",
            path=str(report_path),
            producer="report_writer",
            metadata={
                "output_format": decision.output_format,
                "n_sections": len(decision.sections),
            },
        )
        return ReportExecutorResult(
            executor_name="report_writer",
            status="success",
            message="Technical report generated.",
            artifacts=[artifact],
            errors=[],
            state_updates={"report_path": str(report_path)},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            report_path=str(report_path),
        )
    except Exception as exc:
        error = PipelineError(
            stage="reporting",
            node="report_writer",
            message=str(exc),
            recoverable=True,
        )
        return ReportExecutorResult(
            executor_name="report_writer",
            status="failed",
            message="Technical report generation failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            report_path=str(report_path),
        )


def _render_report(state: TFMStateModel, decision: ReportDecision) -> str:
    lines = [
        "# Informe tecnico de deteccion de anomalias",
        "",
        f"- Run ID: `{state.run_id}`",
        f"- Thread ID: `{state.thread_id}`",
        f"- Dataset: `{state.project_context.dataset}`",
        f"- Objetivo: `{state.project_context.objective}`",
        f"- Decision del redactor: `{decision.decision_id}`",
        "",
    ]
    for section in decision.sections:
        lines.extend(_render_section(state, section))
    return "\n".join(lines).rstrip() + "\n"


def _render_section(state: TFMStateModel, section: ReportSection) -> list[str]:
    title_key = section.title.strip().lower()
    lines = [f"## {section.title}", ""]
    if section.body:
        lines.extend(_paragraph_lines(section.body))
    elif "resumen" in title_key:
        lines.extend(_summary_lines(state))
    elif "contexto" in title_key or "datos" in title_key:
        lines.extend(_context_lines(state))
    elif "config" in title_key or "pipeline" in title_key:
        lines.extend(_configuration_lines(state))
    elif "metrica" in title_key or "evaluacion" in title_key:
        lines.extend(_metrics_lines(state))
    elif "artefact" in title_key:
        lines.extend(_artifact_lines(state))
    elif "limit" in title_key or "siguiente" in title_key:
        lines.extend(_limitation_lines(state))
    else:
        lines.append("Seccion solicitada por el agente redactor.")

    if section.key_findings:
        lines.extend(["", "Hallazgos principales:"])
        lines.extend([f"- {item}" for item in section.key_findings])
    if section.recommendations:
        lines.extend(["", "Recomendaciones:"])
        lines.extend([f"- {item}" for item in section.recommendations])
    if section.include_metrics and "metrica" not in title_key:
        lines.extend(["", *(_metrics_lines(state))])
    elif section.include_metrics and section.body:
        lines.extend(["", "Detalle de metricas:", *(_metrics_lines(state))])
    if section.include_artifacts and "artefact" not in title_key:
        lines.extend(["", *(_artifact_lines(state))])
    elif section.include_artifacts and section.body:
        lines.extend(["", "Inventario de artefactos:", *(_artifact_lines(state))])
    if section.evidence_refs:
        lines.extend(["", "Referencias de evidencia:", *[f"- {ref}" for ref in section.evidence_refs]])
    if section.source_paths:
        lines.extend(["", "Fuentes:", *[f"- `{path}`" for path in section.source_paths]])
    lines.append("")
    return lines


def _paragraph_lines(body: str) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    if not paragraphs:
        return []
    lines: list[str] = []
    for paragraph in paragraphs:
        lines.extend([paragraph, ""])
    return lines[:-1]


def _summary_lines(state: TFMStateModel) -> list[str]:
    if state.evaluation is None:
        status = "pendiente de evaluacion"
    elif state.evaluation.approved:
        status = "aprobada"
    else:
        status = "completada, no aprobada por metricas insuficientes"
    return [
        f"La ejecucion `{state.run_id}` queda {status} para el MVP local.",
        "El flujo mantiene separados los agentes LLM y los ejecutores deterministas.",
    ]


def _context_lines(state: TFMStateModel) -> list[str]:
    profile = state.dataset_profile
    return [
        f"- Dominio: `{state.project_context.domain}`",
        f"- Maquina: `{state.project_context.machine_type}`",
        f"- Tipo de senal: `{state.project_context.signal_type}`",
        f"- Canal principal: `{state.project_context.main_channel}`",
        f"- Ficheros perfilados: `{None if profile is None else profile.n_files}`",
    ]


def _configuration_lines(state: TFMStateModel) -> list[str]:
    return [
        f"- Limpieza: `{_config_summary(state.cleaning_config)}`",
        f"- Estructuracion: `{_config_summary(state.structuring_config)}`",
        f"- Modelado: `{_config_summary(state.modeling_config)}`",
    ]


def _metrics_lines(state: TFMStateModel) -> list[str]:
    metrics = state.metrics
    if metrics is None:
        return ["No hay metricas en el estado."]
    lines = [
        f"- Precision: `{_format_metric(metrics.precision)}`",
        f"- Recall: `{_format_metric(metrics.recall)}`",
        f"- F1-score: `{_format_metric(metrics.f1_score)}`",
        f"- ROC-AUC: `{_format_metric(metrics.roc_auc)}`",
        f"- PR-AUC: `{_format_metric(metrics.pr_auc)}`",
        f"- FPR: `{_format_metric(metrics.false_positive_rate)}`",
    ]
    if state.evaluation is not None:
        lines.append(f"- Juicio: `{state.evaluation.summary}`")
    return lines


def _artifact_lines(state: TFMStateModel) -> list[str]:
    if not state.artifacts:
        return ["No hay artefactos registrados."]
    return [
        f"- `{artifact.artifact_type}` | `{artifact.name}` | `{artifact.path}`"
        for artifact in state.artifacts
    ]


def _limitation_lines(state: TFMStateModel) -> list[str]:
    if state.evaluation is None or not state.evaluation.limitations:
        return ["No se han registrado limitaciones especificas."]
    return [f"- {item}" for item in state.evaluation.limitations]


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _config_summary(value: object) -> str:
    if value is None:
        return "n/a"
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
        parts = [
            f"{key}={payload[key]}"
            for key in sorted(payload)
            if payload[key] is not None and key in _CONFIG_KEYS
        ]
        return ", ".join(parts) or value.__class__.__name__
    return str(value)


_CONFIG_KEYS = {
    "strategy_id",
    "normalization",
    "selected_channel",
    "window_size",
    "overlap",
    "main_channel",
    "target_sample_rate_hz",
    "label_mode",
    "model_name",
    "random_state",
}
