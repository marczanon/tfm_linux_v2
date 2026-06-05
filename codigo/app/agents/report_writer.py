"""Agente redactor LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    ReportDecision,
    ReportRevisionDecision,
    ReportSection,
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


DEFAULT_REPORT_FORMAT = "markdown"
REQUIRED_SECTION_TITLES = [
    "Resumen ejecutivo",
    "Contexto y datos",
    "Configuraciones del pipeline",
    "Metricas y evaluacion",
    "Artefactos generados",
    "Limitaciones y siguientes pasos",
]


def decide_report_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ReportDecision:
    """Decide la estructura del informe usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_report_action_with_llm(state, client)
        except (ValidationError, ValueError) as exc:
            fallback = decide_report_action_deterministic(state)
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM report decision: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.82)
            return fallback
        except LLMCallError as exc:
            fallback = decide_report_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_report_action_deterministic(state)


def decide_report_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> ReportDecision:
    """Solicita al LLM una ReportDecision y valida sus limites."""

    messages = _report_writer_messages(state)
    schema = ReportDecision.model_json_schema()
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        return _validated_report_decision_from_payload(state, payload)
    except (ValidationError, ValueError) as exc:
        repaired_payload = llm_client.complete_json(
            _report_contract_repair_messages(
                messages,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        return _validated_report_decision_from_payload(state, repaired_payload)


def decide_report_action_deterministic(state: TFMStateModel) -> ReportDecision:
    """Fallback reproducible para generar el informe final Markdown."""

    return ReportDecision(
        decision_id=f"{state.run_id}:report_writer:{_report_turn(state):03d}",
        rationale=(
            "Deterministic report policy: generate a concise Markdown report with "
            "context, pipeline configuration, metrics, artifacts and limitations."
        ),
        confidence=1.0,
        output_path=_default_report_path(state),
        output_format=DEFAULT_REPORT_FORMAT,
        sections=_default_sections(state),
    )


def decide_report_revision_action(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    *,
    original_decision: ReportDecision | None = None,
    revision_round: int = 1,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ReportRevisionDecision:
    """Propone una revision estructurada del informe tras la verificacion."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_report_revision_action_with_llm(
                state,
                verification,
                client,
                original_decision=original_decision,
                revision_round=revision_round,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_report_revision_action_deterministic(
                state,
                verification,
                original_decision=original_decision,
                revision_round=revision_round,
            )
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM report revision: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.82)
            return fallback
        except LLMCallError as exc:
            fallback = decide_report_revision_action_deterministic(
                state,
                verification,
                original_decision=original_decision,
                revision_round=revision_round,
            )
            fallback.rationale = (
                f"{fallback.rationale} Fallback after revision LLM failure: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_report_revision_action_deterministic(
        state,
        verification,
        original_decision=original_decision,
        revision_round=revision_round,
    )


def decide_report_revision_action_with_llm(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    llm_client: JSONLLMClient,
    *,
    original_decision: ReportDecision | None = None,
    revision_round: int = 1,
) -> ReportRevisionDecision:
    """Solicita al LLM una revision del informe validada."""

    messages = _report_revision_messages(
        state,
        verification,
        original_decision=original_decision,
        revision_round=revision_round,
    )
    schema = ReportRevisionDecision.model_json_schema()
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        return _validated_report_revision_decision_from_payload(
            state,
            verification,
            payload,
        )
    except (ValidationError, ValueError) as exc:
        repaired_payload = llm_client.complete_json(
            _report_contract_repair_messages(
                messages,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        return _validated_report_revision_decision_from_payload(
            state,
            verification,
            repaired_payload,
        )


def decide_report_revision_action_deterministic(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    *,
    original_decision: ReportDecision | None = None,
    revision_round: int = 1,
) -> ReportRevisionDecision:
    """Fallback seguro: regenera secciones y declara como aplica las correcciones."""

    issues = _verification_issues(verification)
    issue_ids = [_issue_id(issue, index) for index, issue in enumerate(issues, start=1)]
    sections = _default_sections(state)
    if issues:
        sections = _sections_with_verification_notes(sections, verification, issues)
    evidence_refs = sorted(
        {
            ref
            for issue in issues
            for ref in issue.evidence_refs
        }
        | set(verification.evidence_refs)
    )
    changes = [
        issue.suggested_fix
        for issue in issues
        if issue.suggested_fix
    ] or ["No se requieren cambios factuales; se conserva el informe validado."]
    return ReportRevisionDecision(
        decision_id=(
            f"{state.run_id}:report_writer_revision:{revision_round:03d}"
        ),
        rationale=(
            "Deterministic revision policy: regenerate a conservative report from "
            "validated state and explicitly address verifier findings."
        ),
        confidence=0.82 if issues else 0.9,
        revision_round=revision_round,
        revision_of_decision_id=(
            original_decision.decision_id
            if original_decision is not None
            else f"{state.run_id}:report_writer:unknown"
        ),
        verifier_decision_id=verification.decision_id,
        output_path=_default_report_path(state),
        output_format=DEFAULT_REPORT_FORMAT,
        sections=sections,
        accepted_issue_ids=issue_ids,
        rejected_issue_ids=[],
        rejection_rationales={},
        changes_summary=changes,
        evidence_refs=evidence_refs,
    )


def _validated_report_decision_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> ReportDecision:
    decision = ReportDecision.model_validate(payload)
    _validate_report_decision_bounds(state, decision)
    return decision


def _validated_report_revision_decision_from_payload(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    payload: dict[str, Any],
) -> ReportRevisionDecision:
    decision = ReportRevisionDecision.model_validate(payload)
    _validate_report_revision_bounds(state, verification, decision)
    return decision


def _report_contract_repair_messages(
    original_messages: list[LLMMessage],
    *,
    invalid_payload: dict[str, Any],
    validation_error: Exception,
) -> list[LLMMessage]:
    return [
        *original_messages,
        LLMMessage(
            role="assistant",
            content=json.dumps(invalid_payload, indent=2, ensure_ascii=True),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "La decision anterior no valida contra el contrato del redactor.",
                    f"Error de validacion: {validation_error}",
                    "Corrige solo lo necesario y reemite un unico objeto JSON valido.",
                    "No inventes rutas, evidencias ni metricas.",
                    "No cambies decision_id, output_path ni output_format.",
                    "Conserva todas las secciones obligatorias.",
                    "No incluyas texto fuera del JSON.",
                ]
            ),
        ),
    ]


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_REPORT_WRITER_MODE", "").strip().lower() == "llm"


def _report_writer_messages(state: TFMStateModel) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente redactor de un pipeline industrial de "
                "deteccion de anomalias. Tu tarea es razonar y redactar el "
                "contenido narrativo del informe tecnico final para analistas "
                "humanos. No puedes inventar rutas, ejecutar codigo ni afirmar "
                "evidencias que no aparezcan en el estado. Debes devolver "
                "exclusivamente un objeto JSON compatible con ReportDecision; "
                "usa body, key_findings y recommendations para el texto humano."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_report_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- output_format debe ser markdown.",
                    f"- output_path debe ser {_default_report_path(state)}.",
                    "- Incluye todas las secciones obligatorias.",
                    "- Redacta las secciones en castellano tecnico claro.",
                    "- Manten cada body por debajo de 280 caracteres.",
                    "- Usa como maximo 3 key_findings y 2 recommendations por seccion.",
                    "- No devuelvas el informe como JSON al usuario final: este "
                    "JSON es solo el contrato interno validable.",
                    "- source_paths solo puede contener rutas ya presentes en el estado.",
                    *_profile_specific_report_rules(state),
                    f"- decision_id debe ser: {state.run_id}:report_writer:{_report_turn(state):03d}",
                ]
            ),
        ),
    ]


def _report_revision_messages(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    *,
    original_decision: ReportDecision | None,
    revision_round: int,
) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres report_writer revisando un informe tras la auditoria de "
                "report_verifier. Debes responder a incidencias factuales con "
                "una ReportRevisionDecision. Puedes cambiar estilo y enfasis, "
                "pero no inventar evidencia ni ignorar incidencias de severidad "
                "alta o critica. No ejecutes codigo ni devuelvas texto fuera del JSON."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Decision original del redactor:",
                    json.dumps(
                        None
                        if original_decision is None
                        else original_decision.model_dump(mode="json"),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Verificacion recibida:",
                    json.dumps(
                        _verification_payload_for_revision(verification),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(
                        _revision_json_template(
                            state,
                            verification,
                            original_decision=original_decision,
                            revision_round=revision_round,
                        ),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Reglas:",
                    "- output_format debe ser markdown.",
                    f"- output_path debe ser {_default_report_path(state)}.",
                    "- Conserva todas las secciones obligatorias.",
                    "- Manten cada body por debajo de 280 caracteres.",
                    "- Usa como maximo 3 key_findings y 2 recommendations por seccion.",
                    "- accepted_issue_ids y rejected_issue_ids deben responder a las incidencias.",
                    "- Si rechazas una incidencia, explica por que era estilo y no falsedad.",
                    "- No presentes validacion industrial, etiquetas oficiales o aprobacion si la evidencia no lo respalda.",
                    *_profile_specific_report_rules(state),
                    "- source_paths solo puede contener rutas ya presentes en el estado.",
                    f"- decision_id debe ser {state.run_id}:report_writer_revision:{revision_round:03d}.",
                ]
            ),
        ),
    ]


def _report_json_template(state: TFMStateModel) -> dict[str, Any]:
    return {
        "agent_name": "report_writer",
        "decision_id": f"{state.run_id}:report_writer:{_report_turn(state):03d}",
        "rationale": "Motivo tecnico breve de la estructura propuesta.",
        "confidence": 0.9,
        "output_path": _default_report_path(state),
        "output_format": DEFAULT_REPORT_FORMAT,
        "sections": _compact_report_sections_template(state),
    }


def _revision_json_template(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    *,
    original_decision: ReportDecision | None,
    revision_round: int,
) -> dict[str, Any]:
    issues = _verification_issues(verification)
    issue_ids = [_issue_id(issue, index) for index, issue in enumerate(issues, start=1)]
    return {
        "agent_name": "report_writer",
        "decision_id": f"{state.run_id}:report_writer_revision:{revision_round:03d}",
        "rationale": "Como se responde a la verificacion sin inventar evidencia.",
        "confidence": 0.86,
        "revision_round": revision_round,
        "revision_of_decision_id": (
            original_decision.decision_id
            if original_decision is not None
            else f"{state.run_id}:report_writer:unknown"
        ),
        "verifier_decision_id": verification.decision_id,
        "output_path": _default_report_path(state),
        "output_format": DEFAULT_REPORT_FORMAT,
        "sections": _compact_report_sections_template(state),
        "accepted_issue_ids": issue_ids,
        "rejected_issue_ids": [],
        "rejection_rationales": {},
        "changes_summary": verification.required_corrections,
        "evidence_refs": sorted(
            {
                ref
                for issue in issues
                for ref in issue.evidence_refs
            }
        ),
    }


def _compact_report_sections_template(state: TFMStateModel) -> list[dict[str, Any]]:
    metrics_path = None if state.metrics is None else state.metrics.metrics_path
    manifest_sources = [path for path in [state.manifest_path, state.profile_path] if path]
    artifact_paths = [artifact.path for artifact in state.artifacts[:6]]
    return [
        {
            "title": "Resumen ejecutivo",
            "body": "Sintesis breve de aprobacion, objetivo y cautelas.",
            "key_findings": ["Hallazgo principal."],
            "recommendations": ["Siguiente paso recomendado."],
            "evidence_refs": [],
            "include_metrics": False,
            "include_artifacts": False,
            "source_paths": [],
        },
        {
            "title": "Contexto y datos",
            "body": "Dataset, perfil de supervision y fuente de etiquetas.",
            "key_findings": ["Contexto relevante."],
            "recommendations": [],
            "evidence_refs": [],
            "include_metrics": False,
            "include_artifacts": False,
            "source_paths": manifest_sources,
        },
        {
            "title": "Configuraciones del pipeline",
            "body": "Limpieza, estructuracion y modelado elegidos.",
            "key_findings": ["Configuracion trazable."],
            "recommendations": [],
            "evidence_refs": [],
            "include_metrics": False,
            "include_artifacts": False,
            "source_paths": [],
        },
        {
            "title": "Metricas y evaluacion",
            "body": "Lectura principal de metricas y decision operacional.",
            "key_findings": ["Metrica temporal clave."],
            "recommendations": ["Revisar evidencia temporal."],
            "evidence_refs": [],
            "include_metrics": True,
            "include_artifacts": False,
            "source_paths": [path for path in [metrics_path] if path],
        },
        {
            "title": "Artefactos generados",
            "body": "Artefactos necesarios para reproducir la run.",
            "key_findings": ["Artefactos registrados."],
            "recommendations": [],
            "evidence_refs": [],
            "include_metrics": False,
            "include_artifacts": True,
            "source_paths": artifact_paths,
        },
        {
            "title": "Limitaciones y siguientes pasos",
            "body": "Limitaciones metodologicas y cautelas de uso.",
            "key_findings": ["Limitacion principal."],
            "recommendations": ["No extrapolar sin validacion adicional."],
            "evidence_refs": [],
            "include_metrics": False,
            "include_artifacts": False,
            "source_paths": [],
        },
    ]


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "dataset": state.project_context.dataset,
        "objective": state.project_context.objective,
        "supervision_profile": state.project_context.supervision_profile,
        "label_source": state.project_context.label_source,
        "label_granularity": state.project_context.label_granularity,
        "metrics": None if state.metrics is None else state.metrics.model_dump(mode="json"),
        "evaluation": None if state.evaluation is None else state.evaluation.model_dump(mode="json"),
        "cleaning_config": None
        if state.cleaning_config is None
        else state.cleaning_config.model_dump(mode="json"),
        "structuring_config": None
        if state.structuring_config is None
        else state.structuring_config.model_dump(mode="json"),
        "modeling_config": None
        if state.modeling_config is None
        else state.modeling_config.model_dump(mode="json"),
        "artifacts": [
            {
                "name": artifact.name,
                "artifact_type": artifact.artifact_type,
                "path": artifact.path,
                "producer": artifact.producer,
                "description": artifact.description,
            }
            for artifact in state.artifacts
        ],
        "errors": [error.model_dump(mode="json") for error in state.errors],
        "report_path": state.report_path,
    }


def _default_sections(state: TFMStateModel) -> list[ReportSection]:
    metrics_path = None if state.metrics is None else state.metrics.metrics_path
    artifact_paths = [artifact.path for artifact in state.artifacts]
    return [
        ReportSection(
            title="Resumen ejecutivo",
            body=_summary_body(state),
            key_findings=_summary_findings(state),
            recommendations=_summary_recommendations(state),
        ),
        ReportSection(
            title="Contexto y datos",
            body=_context_body(state),
            key_findings=_context_findings(state),
            source_paths=[path for path in [state.manifest_path, state.profile_path] if path],
        ),
        ReportSection(
            title="Configuraciones del pipeline",
            body=_configuration_body(state),
            key_findings=_configuration_findings(state),
        ),
        ReportSection(
            title="Metricas y evaluacion",
            body=_metrics_body(state),
            key_findings=_metrics_findings(state),
            recommendations=_metrics_recommendations(state),
            include_metrics=True,
            source_paths=[path for path in [metrics_path] if path],
        ),
        ReportSection(
            title="Artefactos generados",
            body=_artifacts_body(state),
            key_findings=_artifacts_findings(state),
            include_artifacts=True,
            source_paths=artifact_paths,
        ),
        ReportSection(
            title="Limitaciones y siguientes pasos",
            body=_limitations_body(state),
            key_findings=_limitation_findings(state),
            recommendations=_limitation_recommendations(state),
        ),
    ]


def _summary_body(state: TFMStateModel) -> str:
    status = _approval_status(state)
    metric_phrase = _metric_phrase(state)
    return (
        f"La ejecucion {state.run_id} queda {status}. "
        f"El pipeline ha procesado el dataset {state.project_context.dataset} "
        "manteniendo la separacion entre decisiones agenticas y ejecutores "
        f"deterministas. {metric_phrase}"
    )


def _summary_findings(state: TFMStateModel) -> list[str]:
    findings = [
        "La run conserva trazabilidad de estado, decisiones y artefactos.",
        "El informe se genera como documento Markdown orientado a analistas.",
    ]
    if state.errors:
        findings.append(f"Se han registrado {len(state.errors)} errores en el estado.")
    return findings


def _summary_recommendations(state: TFMStateModel) -> list[str]:
    if state.evaluation is not None and state.evaluation.approved:
        return ["Conservar la run como referencia reproducible del experimento."]
    return [
        "Revisar las limitaciones y decidir si procede una nueva configuracion.",
    ]


def _context_body(state: TFMStateModel) -> str:
    profile = state.dataset_profile
    n_files = "no disponible" if profile is None else str(profile.n_files)
    return (
        "El caso de uso pertenece a deteccion de anomalias industriales sobre "
        f"{state.project_context.machine_type}, con senal "
        f"{state.project_context.signal_type} y canal principal "
        f"{state.project_context.main_channel}. El perfil disponible resume "
        f"{n_files} ficheros sin cargar senales completas dentro del estado."
    )


def _context_findings(state: TFMStateModel) -> list[str]:
    findings = [
        f"Objetivo declarado: {state.project_context.objective}.",
        f"Modo de etiquetas: {state.project_context.label_mode}.",
        f"Perfil de supervision: {state.project_context.supervision_profile}.",
        f"Fuente de etiquetas: {state.project_context.label_source}.",
    ]
    if state.project_context.notes:
        findings.append(state.project_context.notes)
    return findings


def _configuration_body(state: TFMStateModel) -> str:
    return (
        "La configuracion usada por limpieza, estructuracion y modelado se "
        "mantiene en contratos Pydantic. El agente decide parametros dentro de "
        "esos contratos y las transformaciones reales quedan en ejecutores "
        "Python reproducibles."
    )


def _configuration_findings(state: TFMStateModel) -> list[str]:
    return [
        f"Limpieza: {_config_name(state.cleaning_config, 'strategy_id')}.",
        f"Estructuracion: {_config_name(state.structuring_config, 'window_size')}.",
        f"Modelo: {_config_name(state.modeling_config, 'model_name')}.",
    ]


def _metrics_body(state: TFMStateModel) -> str:
    if state.metrics is None:
        return (
            "La ejecucion no contiene metricas agregadas suficientes para "
            "emitir un juicio cuantitativo cerrado."
        )
    if _uses_temporal_degradation_profile(state):
        return (
            "La evaluacion principal corresponde al perfil temporal "
            "run-to-failure. El informe interpreta el detector por trayectoria: "
            "onset confirmado="
            f"{_format_metric(_metric_extra_float_any(state, 'degradation_confirmed_degradation_before_failure_rate', 'degradation_detected_before_failure_rate'))}, "
            "lead time persistente hasta fallo="
            f"{_format_metric(_metric_extra_float_any(state, 'degradation_mean_persistent_lead_time_to_failure', 'degradation_mean_lead_time_to_failure'))}, "
            "falsa alarma nominal="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_false_alarm_rate_nominal'))} "
            "caida Health Index="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_index_drop'))}, "
            "monotonicidad Health Index="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_monotonicity'))} "
            "y tendencia Spearman del score="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_score_trend_spearman'))}. "
            "Las metricas binarias quedan como apoyo si proceden de una politica "
            "proxy, no como ground truth oficial."
        )
    return (
        "La evaluacion resume el comportamiento del detector con metricas "
        f"clasicas de anomalia. Recall={_format_metric(state.metrics.recall)}, "
        f"F1={_format_metric(state.metrics.f1_score)} y "
        f"FPR={_format_metric(state.metrics.false_positive_rate)}. "
        f"{_evaluation_sentence(state)}"
    )


def _metrics_findings(state: TFMStateModel) -> list[str]:
    if state.metrics is None:
        return ["No hay metricas persistidas para esta run."]
    if _uses_temporal_degradation_profile(state):
        findings = [
            "Familia principal: run_to_failure_degradation.",
            (
                "Runs temporales evaluados: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_n_runs'))}."
            ),
            (
                "Onset confirmado antes de fallo: "
                f"{_format_metric(_metric_extra_float_any(state, 'degradation_confirmed_degradation_before_failure_rate', 'degradation_detected_before_failure_rate'))}."
            ),
            (
                "Lead time persistente medio a fallo: "
                f"{_format_metric(_metric_extra_float_any(state, 'degradation_mean_persistent_lead_time_to_failure', 'degradation_mean_lead_time_to_failure'))}."
            ),
            (
                "Falsa alarma nominal media: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_mean_false_alarm_rate_nominal'))}."
            ),
            (
                "Caida media del Health Index: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_index_drop'))}."
            ),
            (
                "Monotonicidad media del Health Index: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_monotonicity'))}."
            ),
            (
                "Robustez media del Health Index: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_robustness'))}."
            ),
            (
                "Tendencia Spearman media del score: "
                f"{_format_metric(_metric_extra_float(state, 'degradation_mean_score_trend_spearman'))}."
            ),
        ]
        if state.metrics.f1_score is not None:
            findings.append(
                f"F1 auxiliar/proxy: {_format_metric(state.metrics.f1_score)}."
            )
        return findings
    return [
        f"Precision: {_format_metric(state.metrics.precision)}.",
        f"Recall: {_format_metric(state.metrics.recall)}.",
        f"F1-score: {_format_metric(state.metrics.f1_score)}.",
        f"Tasa de falsos positivos: {_format_metric(state.metrics.false_positive_rate)}.",
    ]


def _metrics_recommendations(state: TFMStateModel) -> list[str]:
    if state.evaluation is None:
        return ["Ejecutar evaluacion antes de usar el resultado como evidencia final."]
    if _uses_temporal_degradation_profile(state):
        recommendations = [
            "Revisar la curva temporal de score, umbral, primera alerta y fallo estimado.",
            "No comparar esta run con CWRU solo por F1; usar metricas temporales y limitaciones.",
        ]
        if state.project_context.label_source in {"none", "temporal_proxy", "synthetic"}:
            recommendations.append(
                "Declarar que las etiquetas por ventana no son oficiales y dependen de la politica usada."
            )
        return recommendations
    if state.evaluation.approved:
        return ["Usar las metricas como baseline local, no como validacion industrial final."]
    return ["Comparar una configuracion alternativa antes de aprobar la run."]


def _artifacts_body(state: TFMStateModel) -> str:
    if not state.artifacts:
        return "No se han registrado artefactos persistidos en esta ejecucion."
    return (
        "Los artefactos registrados permiten reconstruir el hilo experimental: "
        "manifiestos, perfiles, salidas de limpieza, features, modelos, "
        "predicciones, metricas e informes segun las fases ejecutadas."
    )


def _artifacts_findings(state: TFMStateModel) -> list[str]:
    if not state.artifacts:
        return ["No hay artefactos disponibles para auditar."]
    counts: dict[str, int] = {}
    for artifact in state.artifacts:
        counts[artifact.artifact_type] = counts.get(artifact.artifact_type, 0) + 1
    return [f"{artifact_type}: {count}." for artifact_type, count in sorted(counts.items())]


def _limitations_body(state: TFMStateModel) -> str:
    if state.evaluation is None or not state.evaluation.limitations:
        return (
            "No se han declarado limitaciones especificas en la evaluacion, "
            "pero el resultado debe interpretarse como validacion local del TFM."
        )
    return (
        "La run incluye limitaciones declaradas por el evaluador. Estas "
        "limitaciones no son errores tecnicos; acotan el uso responsable de "
        "las conclusiones."
    )


def _limitation_findings(state: TFMStateModel) -> list[str]:
    if state.evaluation is None or not state.evaluation.limitations:
        return ["Sin limitaciones especificas persistidas por el evaluador."]
    return list(state.evaluation.limitations)


def _limitation_recommendations(state: TFMStateModel) -> list[str]:
    recommendations = [
        "Revisar el evidence pack antes de presentar conclusiones del experimento.",
    ]
    if (
        state.project_context.dataset == "nasa_ims_bearing"
        or state.project_context.label_source in {"none", "temporal_proxy", "synthetic"}
    ):
        recommendations.append(
            "Explicitar la politica temporal y no presentar etiquetas proxy como oficiales."
        )
    return recommendations


def _profile_specific_report_rules(state: TFMStateModel) -> list[str]:
    if not _uses_temporal_degradation_profile(state):
        return []
    return [
        (
            "- Para run_to_failure_degradation, presenta lead time, falsas "
            "alarmas nominales y tendencia del score como lectura principal."
        ),
        (
            "- No presentes F1 como metrica principal si las etiquetas son "
            "proxy, sinteticas o no oficiales."
        ),
        (
            "- Si label_source no es official, declara explicitamente que no "
            "hay etiquetas oficiales por ventana."
        ),
    ]


def _uses_temporal_degradation_profile(state: TFMStateModel) -> bool:
    return state.project_context.supervision_profile == "run_to_failure_degradation"


def _metric_extra_float(state: TFMStateModel, key: str) -> float | None:
    if state.metrics is None:
        return None
    value = state.metrics.extra.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _metric_extra_float_any(state: TFMStateModel, *keys: str) -> float | None:
    for key in keys:
        value = _metric_extra_float(state, key)
        if value is not None:
            return value
    return None


def _verification_payload_for_revision(
    verification: ReportVerificationDecision,
) -> dict[str, Any]:
    issues = _verification_issues(verification)
    return {
        "decision_id": verification.decision_id,
        "verification_status": verification.verification_status,
        "summary": verification.summary,
        "required_corrections": verification.required_corrections,
        "acceptable_style_notes": verification.acceptable_style_notes,
        "issues": [
            {
                "issue_id": _issue_id(issue, index),
                "issue_type": issue.issue_type,
                "severity": issue.severity,
                "claim_text": issue.claim_text,
                "reason": issue.reason,
                "evidence_refs": issue.evidence_refs,
                "suggested_fix": issue.suggested_fix,
            }
            for index, issue in enumerate(issues, start=1)
        ],
    }


def _verification_issues(
    verification: ReportVerificationDecision,
) -> list[ReportVerificationIssue]:
    return [
        *verification.unsupported_claims,
        *verification.misleading_claims,
        *verification.missing_limitations,
    ]


def _issue_id(issue: ReportVerificationIssue, index: int) -> str:
    if issue.issue_id:
        return issue.issue_id
    return f"verification_issue_{index:03d}"


def _sections_with_verification_notes(
    sections: list[ReportSection],
    verification: ReportVerificationDecision,
    issues: list[ReportVerificationIssue],
) -> list[ReportSection]:
    issue_findings = [
        f"{_issue_id(issue, index)}: {issue.reason}"
        for index, issue in enumerate(issues, start=1)
    ]
    issue_recommendations = [
        issue.suggested_fix
        for issue in issues
        if issue.suggested_fix
    ]
    updated: list[ReportSection] = []
    for section in sections:
        if section.title != "Limitaciones y siguientes pasos":
            updated.append(section)
            continue
        body = (
            f"{section.body or ''}\n\n"
            "Tras la verificacion agentica del informe, esta version revisada "
            "responde a las incidencias factuales detectadas y conserva solo "
            "conclusiones respaldadas por la evidencia de la run."
        ).strip()
        updated.append(
            section.model_copy(
                update={
                    "body": body,
                    "key_findings": [
                        *section.key_findings,
                        f"Verificacion inicial: {verification.verification_status}.",
                        *issue_findings,
                    ],
                    "recommendations": [
                        *section.recommendations,
                        *issue_recommendations,
                    ],
                    "evidence_refs": sorted(
                        set(section.evidence_refs)
                        | {
                            ref
                            for issue in issues
                            for ref in issue.evidence_refs
                        }
                    ),
                }
            )
        )
    return updated


def _approval_status(state: TFMStateModel) -> str:
    if state.evaluation is None:
        return "pendiente de evaluacion"
    if state.evaluation.approved:
        return "aprobada por el evaluador"
    return "completada pero no aprobada por el evaluador"


def _metric_phrase(state: TFMStateModel) -> str:
    if state.metrics is None:
        return "No hay metricas cuantitativas agregadas en el estado."
    if _uses_temporal_degradation_profile(state):
        return (
            "El resumen temporal principal es onset_confirmado="
            f"{_format_metric(_metric_extra_float_any(state, 'degradation_confirmed_degradation_before_failure_rate', 'degradation_detected_before_failure_rate'))}, "
            "lead_time_persistente="
            f"{_format_metric(_metric_extra_float_any(state, 'degradation_mean_persistent_lead_time_to_failure', 'degradation_mean_lead_time_to_failure'))}, "
            "falsa_alarma_nominal="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_false_alarm_rate_nominal'))} "
            "HI_drop="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_index_drop'))}, "
            "HI_monotonicidad="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_health_monotonicity'))} "
            "y tendencia_score="
            f"{_format_metric(_metric_extra_float(state, 'degradation_mean_score_trend_spearman'))}."
        )
    return (
        f"El resumen cuantitativo principal es F1={_format_metric(state.metrics.f1_score)} "
        f"y recall={_format_metric(state.metrics.recall)}."
    )


def _evaluation_sentence(state: TFMStateModel) -> str:
    if state.evaluation is None:
        return "No hay juicio estructurado del evaluador."
    return f"Juicio del evaluador: {state.evaluation.summary}"


def _config_name(value: object, attribute: str) -> str:
    if value is None:
        return "no disponible"
    return str(getattr(value, attribute, "no disponible"))


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _validate_report_decision_bounds(
    state: TFMStateModel,
    decision: ReportDecision,
) -> None:
    if decision.output_format != DEFAULT_REPORT_FORMAT:
        raise ValueError("output_format must be markdown for the MVP")
    expected_path = _default_report_path(state)
    if decision.output_path != expected_path:
        raise ValueError(f"output_path must be {expected_path}")

    titles = [section.title for section in decision.sections]
    missing = [title for title in REQUIRED_SECTION_TITLES if title not in titles]
    if missing:
        raise ValueError(f"missing required report sections: {', '.join(missing)}")

    allowed_paths = _allowed_source_paths(state)
    for section in decision.sections:
        unsupported = sorted(set(section.source_paths) - allowed_paths)
        if unsupported:
            raise ValueError(
                f"unsupported source paths in section {section.title}: "
                f"{', '.join(unsupported)}"
            )


def _validate_report_revision_bounds(
    state: TFMStateModel,
    verification: ReportVerificationDecision,
    decision: ReportRevisionDecision,
) -> None:
    _validate_report_decision_bounds(state, decision)
    expected_id = (
        f"{state.run_id}:report_writer_revision:{decision.revision_round:03d}"
    )
    if decision.decision_id != expected_id:
        raise ValueError(f"decision_id must be {expected_id}")
    if decision.verifier_decision_id != verification.decision_id:
        raise ValueError("verifier_decision_id must match verification decision")
    issue_ids = {
        _issue_id(issue, index)
        for index, issue in enumerate(_verification_issues(verification), start=1)
    }
    high_severity_issue_ids = {
        _issue_id(issue, index)
        for index, issue in enumerate(_verification_issues(verification), start=1)
        if issue.severity in {"high", "critical"}
    }
    answered = set(decision.accepted_issue_ids) | set(decision.rejected_issue_ids)
    missing_high = sorted(high_severity_issue_ids - answered)
    if missing_high:
        raise ValueError(
            "high or critical verifier issues require an explicit response: "
            + ", ".join(missing_high)
        )
    unknown = sorted(answered - issue_ids)
    if unknown:
        raise ValueError("revision cites unknown issue ids: " + ", ".join(unknown))


def _allowed_source_paths(state: TFMStateModel) -> set[str]:
    paths = {
        artifact.path
        for artifact in state.artifacts
    }
    for value in [
        state.manifest_path,
        state.profile_path,
        state.clean_path,
        state.tensor_path,
        state.splits_path,
        None if state.metrics is None else state.metrics.metrics_path,
    ]:
        if value:
            paths.add(value)
    return paths


def _default_report_path(state: TFMStateModel) -> str:
    return f"codigo/reports/{state.project_context.dataset}/{state.run_id}/final_report.md"


def _report_turn(state: TFMStateModel) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == "report_writer"
        for message in state.messages
    )
