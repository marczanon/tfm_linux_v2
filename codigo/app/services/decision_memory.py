"""Episodios de decision y candidatos de memoria derivados de post-mortems."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codigo.app.schemas.agent_decisions import (
    EvaluationDecision,
    ModelingAlternative,
    ModelingDecision,
    ModelingRetryDecision,
    StructuringAlternative,
    StructuringDecision,
)
from codigo.app.schemas.common import JsonScalar, StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentReasoningPostmortem,
    DecisionEpisode,
    DecisionOption,
    MemoryCandidate,
    ReasoningOutcome,
    RetrievedMemoryContext,
)
from codigo.app.schemas.state import (
    EvaluationResult,
    MetricsReport,
    ModelingConfig,
    StructuringConfig,
    TFMStateModel,
)
from codigo.app.services.vector_memory import memory_candidate_from_decision_episode

FPR_TARGET = 0.10
RECALL_TARGET = 0.80


class DecisionMemoryArtifacts(StrictBaseModel):
    """Artefactos persistidos para memoria basada en episodios de decision."""

    episode_path: str
    episode_report_path: str
    candidate_path: str
    candidate_report_path: str
    episode: DecisionEpisode
    candidate: MemoryCandidate


def build_modeling_retry_decision_episode(
    *,
    source_run_id: str,
    run_id: str,
    decision: ModelingRetryDecision,
    postmortem: AgentReasoningPostmortem,
    before_metrics: MetricsReport | None,
    after_metrics: MetricsReport | None,
    evaluation: EvaluationResult | None,
    memory_context: RetrievedMemoryContext | None = None,
) -> DecisionEpisode:
    """Construye un episodio general a partir de un reintento del modelador."""

    before = _metrics_dict(before_metrics)
    after = _metrics_dict(after_metrics)
    retrieved_memory_ids = (
        decision.memory_record_ids
        if memory_context is None
        else [item.record.memory_record_id for item in memory_context.items]
    )
    return DecisionEpisode(
        episode_id=f"{run_id}:decision_episode:{decision.attempt_number:03d}",
        run_id=run_id,
        decision_id=decision.decision_id,
        agent_name=decision.agent_name,
        target_agent="modeler",
        decision_type="modeling",
        dataset="nasa_ims_bearing",
        context_summary=_context_summary(
            source_run_id=source_run_id,
            before=before,
            decision=decision,
            memory_context=memory_context,
        ),
        options_considered=_decision_options(decision),
        chosen_action=postmortem.action_taken,
        expected_effect=decision.expected_effect,
        evidence_used=decision.evidence_used,
        retrieved_memory_record_ids=retrieved_memory_ids,
        execution_result_summary=(
            postmortem.automatic_critique
            if evaluation is None
            else f"{postmortem.automatic_critique} Evaluacion: {evaluation.summary}"
        ),
        before_metrics=before,
        after_metrics=after,
        metric_deltas=postmortem.metric_deltas,
        tradeoffs_observed=_tradeoffs(before, after),
        failure_modes=_failure_modes(postmortem, after, evaluation),
        outcome=postmortem.outcome,
        lesson_learned=_lesson_learned(postmortem, evaluation),
        reusable_lessons=_episode_lessons(postmortem, before, after, evaluation),
        when_to_reuse=_when_to_reuse(postmortem, before, after),
        when_not_to_reuse=_when_not_to_reuse(postmortem, before, after, evaluation),
        risk_if_misused=_risk_if_misused(postmortem, after),
        human_review_status=postmortem.human_review_status,
    )


def build_modeling_retry_memory_candidate(
    episode: DecisionEpisode,
    *,
    reusable_as_context: bool,
) -> MemoryCandidate:
    """Destila un episodio de modelado en candidato indexable."""

    return memory_candidate_from_decision_episode(
        episode,
        reusable_as_context=reusable_as_context,
    )


def build_modeling_decision_episode(
    *,
    state: TFMStateModel,
    decision: ModelingDecision,
    execution_result_summary: str | None = None,
    outcome: ReasoningOutcome = "supported",
    memory_context: RetrievedMemoryContext | None = None,
) -> DecisionEpisode:
    """Construye un episodio reutilizable a partir de una decision modeladora."""

    retrieved_memory_ids = _retrieved_memory_ids([], memory_context)
    return DecisionEpisode(
        episode_id=f"{state.run_id}:modeler:decision_episode:{_safe_id(decision.decision_id)}",
        run_id=state.run_id,
        decision_id=decision.decision_id,
        agent_name=decision.agent_name,
        target_agent="modeler",
        decision_type="modeling",
        dataset=state.project_context.dataset,
        context_summary=_modeling_context_summary(state, decision),
        options_considered=_modeling_options(decision),
        chosen_action=_modeling_action(decision),
        expected_effect=_modeling_expected_effect(decision),
        evidence_used=_modeling_evidence(decision, memory_context),
        retrieved_memory_record_ids=retrieved_memory_ids,
        execution_result_summary=execution_result_summary,
        after_metrics=_metrics_dict(state.metrics),
        tradeoffs_observed=_modeling_tradeoffs(state, decision),
        failure_modes=_modeling_failure_modes(outcome),
        outcome=outcome,
        lesson_learned=_modeling_lesson(state, decision),
        reusable_lessons=_modeling_reusable_lessons(state, decision),
        when_to_reuse=_modeling_when_to_reuse(state, decision),
        when_not_to_reuse=_modeling_when_not_to_reuse(state),
        risk_if_misused=_modeling_risk_if_misused(state),
    )


def build_modeling_memory_candidate(
    episode: DecisionEpisode,
    *,
    reusable_as_context: bool,
) -> MemoryCandidate:
    """Destila un episodio de modelado inicial en candidato indexable."""

    return memory_candidate_from_decision_episode(
        episode,
        reusable_as_context=reusable_as_context,
    )


def build_structuring_decision_episode(
    *,
    state: TFMStateModel,
    decision: StructuringDecision,
    execution_result_summary: str | None = None,
    outcome: ReasoningOutcome = "inconclusive",
    memory_context: RetrievedMemoryContext | None = None,
) -> DecisionEpisode:
    """Construye un episodio reutilizable a partir de una decision estructuradora."""

    retrieved_memory_ids = _retrieved_memory_ids(decision.memory_record_ids, memory_context)
    return DecisionEpisode(
        episode_id=f"{state.run_id}:structurer:decision_episode:{_safe_id(decision.decision_id)}",
        run_id=state.run_id,
        decision_id=decision.decision_id,
        agent_name=decision.agent_name,
        target_agent="structurer",
        decision_type="structuring",
        dataset=state.project_context.dataset,
        context_summary=_structuring_context_summary(state, decision, memory_context),
        options_considered=_structuring_options(decision),
        chosen_action=_structuring_action(decision.structuring_config),
        expected_effect="Generar ventanas, features y splits reproducibles para modelado.",
        evidence_used=_structuring_evidence(memory_context),
        retrieved_memory_record_ids=retrieved_memory_ids,
        execution_result_summary=execution_result_summary,
        tradeoffs_observed=_structuring_tradeoffs(decision.structuring_config),
        failure_modes=_structuring_failure_modes(outcome),
        outcome=outcome,
        lesson_learned=_structuring_lesson(decision, execution_result_summary),
        reusable_lessons=_structuring_reusable_lessons(decision.structuring_config),
        when_to_reuse=_structuring_when_to_reuse(state, decision.structuring_config),
        when_not_to_reuse=_structuring_when_not_to_reuse(state),
        risk_if_misused=(
            "Puede trasladar una ventana o feature set a otro dataset sin comprobar "
            "frecuencia, canal, fuga temporal o resultados aguas abajo."
        ),
    )


def build_structuring_memory_candidate(
    episode: DecisionEpisode,
    *,
    reusable_as_context: bool,
) -> MemoryCandidate:
    """Destila un episodio de estructuracion en candidato indexable."""

    return memory_candidate_from_decision_episode(
        episode,
        reusable_as_context=reusable_as_context,
    )


def build_evaluation_decision_episode(
    *,
    state: TFMStateModel,
    decision: EvaluationDecision,
    memory_context: RetrievedMemoryContext | None = None,
) -> DecisionEpisode:
    """Construye un episodio reutilizable a partir de una decision evaluadora."""

    metrics = _metrics_dict(state.metrics)
    retrieved_memory_ids = _retrieved_memory_ids(decision.memory_record_ids, memory_context)
    return DecisionEpisode(
        episode_id=f"{state.run_id}:evaluator:decision_episode:{_safe_id(decision.decision_id)}",
        run_id=state.run_id,
        decision_id=decision.decision_id,
        agent_name=decision.agent_name,
        target_agent="evaluator",
        decision_type="evaluation",
        dataset=state.project_context.dataset,
        context_summary=_evaluation_context_summary(state, decision),
        options_considered=_evaluation_options(decision),
        chosen_action=_evaluation_action(decision),
        expected_effect=(
            "Aceptar solo ejecuciones que cumplen el protocolo local o pedir "
            "nueva configuracion cuando las metricas no son suficientes."
        ),
        evidence_used=_evaluation_evidence(decision, memory_context),
        retrieved_memory_record_ids=retrieved_memory_ids,
        execution_result_summary=decision.evaluation.summary,
        after_metrics=metrics,
        tradeoffs_observed=_evaluation_tradeoffs(state.metrics, decision),
        failure_modes=_evaluation_failure_modes(state.metrics, decision),
        outcome=_evaluation_outcome(state, decision),
        lesson_learned=_evaluation_lesson(decision),
        reusable_lessons=_evaluation_reusable_lessons(decision),
        when_to_reuse=_evaluation_when_to_reuse(state, decision),
        when_not_to_reuse=_evaluation_when_not_to_reuse(state),
        risk_if_misused=(
            "Puede convertir una advertencia historica en aprobacion si no se "
            "respetan metricas, umbrales y politica de etiquetado actuales."
        ),
    )


def build_evaluation_memory_candidate(
    episode: DecisionEpisode,
    *,
    reusable_as_context: bool,
) -> MemoryCandidate:
    """Destila un episodio de evaluacion en candidato indexable."""

    return memory_candidate_from_decision_episode(
        episode,
        reusable_as_context=reusable_as_context,
    )


def write_decision_memory_artifacts(
    *,
    episode: DecisionEpisode,
    candidate: MemoryCandidate,
    output_dir: str | Path,
) -> DecisionMemoryArtifacts:
    """Persiste episodio y candidato de memoria en JSON y Markdown."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    episode_path = output / "decision_episode.json"
    episode_report_path = output / "decision_episode.md"
    candidate_path = output / "memory_candidate.json"
    candidate_report_path = output / "memory_candidate.md"

    episode_path.write_text(
        json.dumps(episode.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    episode_report_path.write_text(_episode_markdown(episode), encoding="utf-8")
    candidate_path.write_text(
        json.dumps(candidate.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    candidate_report_path.write_text(_candidate_markdown(candidate), encoding="utf-8")
    return DecisionMemoryArtifacts(
        episode_path=episode_path.as_posix(),
        episode_report_path=episode_report_path.as_posix(),
        candidate_path=candidate_path.as_posix(),
        candidate_report_path=candidate_report_path.as_posix(),
        episode=episode,
        candidate=candidate,
    )


def _metrics_dict(metrics: MetricsReport | None) -> dict[str, float | None]:
    if metrics is None:
        return {}
    values: dict[str, float | None] = {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1_score": metrics.f1_score,
        "false_positive_rate": metrics.false_positive_rate,
    }
    for key, value in metrics.extra.items():
        if key.startswith("degradation_") and isinstance(value, (int, float)):
            values[key] = float(value)
    return values


def _context_summary(
    *,
    source_run_id: str,
    before: dict[str, float | None],
    decision: ModelingRetryDecision,
    memory_context: RetrievedMemoryContext | None,
) -> str:
    memory_text = (
        "sin memoria recuperada"
        if memory_context is None or not memory_context.items
        else f"con {len(memory_context.items)} recuerdos recuperados"
    )
    return (
        f"Reintento del modelador sobre {source_run_id}, {memory_text}. "
        f"Metricas previas: precision={_fmt(before.get('precision'))}, "
        f"recall={_fmt(before.get('recall'))}, "
        f"F1={_fmt(before.get('f1_score'))}, "
        f"FPR={_fmt(before.get('false_positive_rate'))}. "
        f"Decision declarada: {decision.learning_summary}"
    )


def _decision_options(decision: ModelingRetryDecision) -> list[DecisionOption]:
    options = [
        _option_from_modeling_config(
            option_id="chosen_retry_config",
            config=decision.retry_config,
            description=(
                "Configuracion elegida para el reintento."
                if decision.should_retry
                else "Sin configuracion de reintento seleccionada."
            ),
            expected_effect=decision.expected_effect,
            selected=decision.should_retry and decision.retry_config is not None,
        )
    ]
    options.extend(_option_from_alternative(alt) for alt in decision.comparison_candidates)
    if not decision.should_retry:
        options.append(
            DecisionOption(
                option_id="stop",
                option_type="control_action",
                description=decision.stop_reason or "El agente decide no reintentar.",
                selected=True,
            )
        )
    return [option for option in options if option is not None]


def _option_from_modeling_config(
    *,
    option_id: str,
    config: ModelingConfig | None,
    description: str,
    expected_effect: str | None,
    selected: bool,
) -> DecisionOption | None:
    if config is None:
        if selected:
            return None
        return DecisionOption(
            option_id=option_id,
            option_type="model_config",
            description=description,
            expected_effect=expected_effect,
            selected=selected,
        )
    return DecisionOption(
        option_id=option_id,
        option_type="model_config",
        description=description,
        parameters=_config_parameters(config),
        expected_effect=expected_effect,
        risk_notes=_modeling_risks(config),
        selected=selected,
    )


def _option_from_alternative(alternative: ModelingAlternative) -> DecisionOption:
    return DecisionOption(
        option_id=alternative.alternative_id,
        option_type="model_config",
        description=alternative.rationale,
        parameters=_config_parameters(alternative.modeling_config),
        expected_effect=alternative.expected_effect,
        risk_notes=_modeling_risks(alternative.modeling_config),
        selected=False,
    )


def _config_parameters(config: ModelingConfig) -> dict[str, JsonScalar]:
    parameters: dict[str, JsonScalar] = {
        "model_name": config.model_name,
        "random_state": config.random_state,
    }
    for key, value in sorted(config.hyperparameters.items()):
        parameters[key] = _json_scalar(value)
    return parameters


def _json_scalar(value: Any) -> JsonScalar:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, sort_keys=True)


def _safe_id(value: str) -> str:
    return value.replace(":", "_").replace("/", "_")


def _retrieved_memory_ids(
    decision_memory_ids: list[str],
    memory_context: RetrievedMemoryContext | None,
) -> list[str]:
    if memory_context is None:
        return decision_memory_ids
    return [item.record.memory_record_id for item in memory_context.items]


def _modeling_context_summary(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> str:
    strategy = decision.decision_strategy
    return (
        f"Decision del modelador para {state.project_context.dataset}. "
        f"Perfil={state.project_context.supervision_profile}. "
        f"Modelo={decision.modeling_config.model_name}. "
        f"Estrategia={strategy.strategy_type}. Hipotesis: {strategy.hypothesis}"
        + (
            ""
            if strategy.alert_policy is None
            else f" Politica de alerta: {strategy.alert_policy}"
        )
        + (
            ""
            if not strategy.optimization_targets
            else " Objetivos: " + ", ".join(strategy.optimization_targets) + "."
        )
    )


def _modeling_options(decision: ModelingDecision) -> list[DecisionOption]:
    options = [
        _option_from_modeling_config(
            option_id="chosen_modeling_config",
            config=decision.modeling_config,
            description="Configuracion elegida por el modelador.",
            expected_effect=_modeling_expected_effect(decision),
            selected=True,
        )
    ]
    options.extend(_option_from_alternative(alt) for alt in decision.comparison_candidates)
    return [option for option in options if option is not None]


def _modeling_action(decision: ModelingDecision) -> str:
    config = decision.modeling_config
    return (
        f"Use model_name={config.model_name}, train_split={decision.train_split}, "
        f"validation_split={decision.validation_split or 'none'}, "
        f"hyperparameters={json.dumps(config.hyperparameters, sort_keys=True)}."
    )


def _modeling_expected_effect(decision: ModelingDecision) -> str:
    strategy = decision.decision_strategy
    if strategy.optimization_targets:
        return "Optimizar " + ", ".join(strategy.optimization_targets) + "."
    if decision.comparison_candidates:
        return "Comparar la familia elegida con alternativas soportadas."
    return "Entrenar un detector reproducible y generar score de anomalia."


def _modeling_evidence(
    decision: ModelingDecision,
    memory_context: RetrievedMemoryContext | None,
) -> list[str]:
    evidence = ["features_artifact", "supported_model_families"]
    strategy = decision.decision_strategy
    evidence.extend(strategy.tool_names)
    evidence.extend(strategy.evidence_refs)
    if memory_context is not None and memory_context.items:
        evidence.append("retrieved_memory_context")
    return list(dict.fromkeys(evidence))


def _modeling_tradeoffs(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> list[str]:
    strategy = decision.decision_strategy
    tradeoffs = [
        f"model_family:{decision.modeling_config.model_name}",
        f"strategy:{strategy.strategy_type}",
    ]
    tradeoffs.extend(strategy.risk_notes)
    tradeoffs.extend(f"target:{target}" for target in strategy.optimization_targets)
    if strategy.alert_policy is not None:
        tradeoffs.append("alert_policy_declared")
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        tradeoffs.extend(
            [
                "run_to_failure_modeling_strategy",
                "score_trend_over_binary_f1",
            ]
        )
        if "temporal_health_lookup" in strategy.tool_names:
            tradeoffs.append("temporal_health_tool_used")
        if "degradation_metrics_lookup" in strategy.tool_names:
            tradeoffs.append("degradation_metrics_tool_used")
    return sorted(set(tradeoffs))


def _modeling_failure_modes(outcome: ReasoningOutcome) -> list[str]:
    if outcome in {"contradicted", "overcorrected"}:
        return ["modeling_choice_contradicted_by_downstream_evidence"]
    if outcome == "inconclusive":
        return ["requires_downstream_evaluation"]
    return []


def _modeling_lesson(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> str:
    profile = state.project_context.supervision_profile
    strategy = decision.decision_strategy
    return (
        f"El modelador eligio {decision.modeling_config.model_name} para "
        f"{profile} con estrategia {strategy.strategy_type}. "
        f"Hipotesis: {strategy.hypothesis}"
    )


def _modeling_reusable_lessons(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> list[str]:
    config = decision.modeling_config
    strategy = decision.decision_strategy
    lessons = [
        "modeling_decisions_require_downstream_evaluation",
        f"model_family_{config.model_name}",
        f"strategy_{strategy.strategy_type}",
    ]
    threshold = config.hyperparameters.get("threshold_quantile")
    if isinstance(threshold, (int, float)):
        lessons.append(f"threshold_quantile_{threshold}")
    lessons.extend(f"target_{target}" for target in strategy.optimization_targets)
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        lessons.extend(
            [
                "run_to_failure_modeling_requires_temporal_metrics",
                "f1_is_auxiliary_for_temporal_profile",
            ]
        )
        if strategy.alert_policy is not None:
            lessons.append("temporal_alert_policy_must_be_explicit")
    return sorted(set(lessons))


def _modeling_when_to_reuse(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> list[str]:
    return [
        f"dataset={state.project_context.dataset}",
        f"supervision_profile={state.project_context.supervision_profile}",
        f"model_name={decision.modeling_config.model_name}",
        f"strategy={decision.decision_strategy.strategy_type}",
        "the modeler needs prior evidence about model family and alert policy",
    ]


def _modeling_when_not_to_reuse(state: TFMStateModel) -> list[str]:
    conditions = [
        f"dataset is not comparable with {state.project_context.dataset}",
        "feature set, split policy or label source changed without review",
    ]
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        conditions.extend(
            [
                "current task requires real RUL estimation rather than historic lead time",
                "failure metadata or temporal proxy policy changed",
            ]
        )
    return conditions


def _modeling_risk_if_misused(state: TFMStateModel) -> str:
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        return (
            "Puede trasladar una politica temporal a otro activo sin comprobar "
            "lead time historico, falsas alarmas nominales, etiquetas proxy y "
            "ausencia de RUL estimado."
        )
    return (
        "Puede reutilizar una familia de modelo sin revisar features, split, "
        "etiquetas y umbral operativo del contexto actual."
    )


def _structuring_context_summary(
    state: TFMStateModel,
    decision: StructuringDecision,
    memory_context: RetrievedMemoryContext | None,
) -> str:
    memory_text = (
        "sin memoria recuperada"
        if memory_context is None or not memory_context.items
        else f"con {len(memory_context.items)} recuerdos recuperados"
    )
    config = decision.structuring_config
    return (
        f"Decision del estructurador para {state.project_context.dataset}, "
        f"{memory_text}. Canal={config.main_channel}, "
        f"sample_rate={config.target_sample_rate_hz}, "
        f"window_size={config.window_size}, overlap={config.overlap}, "
        f"features={len(config.features)}. Razonamiento: {decision.rationale}"
    )


def _structuring_options(decision: StructuringDecision) -> list[DecisionOption]:
    options = [
        _option_from_structuring_config(
            option_id="chosen_structuring_config",
            config=decision.structuring_config,
            description="Configuracion elegida por el estructurador.",
            expected_effect="Crear ventanas y features para la etapa de modelado.",
            selected=True,
        )
    ]
    options.extend(_option_from_structuring_alternative(alt) for alt in decision.comparison_candidates)
    return options


def _option_from_structuring_alternative(
    alternative: StructuringAlternative,
) -> DecisionOption:
    return _option_from_structuring_config(
        option_id=alternative.alternative_id,
        config=alternative.structuring_config,
        description=alternative.rationale,
        expected_effect=alternative.expected_effect,
        selected=False,
    )


def _option_from_structuring_config(
    *,
    option_id: str,
    config: StructuringConfig,
    description: str,
    expected_effect: str | None,
    selected: bool,
) -> DecisionOption:
    return DecisionOption(
        option_id=option_id,
        option_type="structuring_config",
        description=description,
        parameters=_structuring_parameters(config),
        expected_effect=expected_effect,
        risk_notes=_structuring_risks(config),
        selected=selected,
    )


def _structuring_parameters(config: StructuringConfig) -> dict[str, JsonScalar]:
    return {
        "window_size": config.window_size,
        "overlap": config.overlap,
        "main_channel": config.main_channel,
        "target_sample_rate_hz": config.target_sample_rate_hz,
        "label_mode": config.label_mode,
        "n_features": len(config.features),
        "features": ",".join(config.features),
    }


def _structuring_risks(config: StructuringConfig) -> list[str]:
    risks: list[str] = []
    if config.window_size <= 1024:
        risks.append("short windows can increase temporal resolution but may add noise")
    if config.window_size >= 4096:
        risks.append("long windows add context but reduce the number of samples")
    if config.overlap >= 0.75:
        risks.append("high overlap can increase redundancy between windows")
    if config.label_mode != "binary_anomaly":
        risks.append("fault-type labels require stronger label quality checks")
    return risks


def _structuring_action(config: StructuringConfig) -> str:
    return (
        f"Use window_size={config.window_size}, overlap={config.overlap}, "
        f"main_channel={config.main_channel}, "
        f"target_sample_rate_hz={config.target_sample_rate_hz}, "
        f"label_mode={config.label_mode}, features={len(config.features)}."
    )


def _structuring_evidence(
    memory_context: RetrievedMemoryContext | None,
) -> list[str]:
    evidence = ["project_context", "clean_signal_summary", "supported_structuring_bounds"]
    if memory_context is not None and memory_context.items:
        evidence.append("retrieved_memory_context")
    return evidence


def _structuring_tradeoffs(config: StructuringConfig) -> list[str]:
    tradeoffs = ["window_context_vs_temporal_resolution"]
    if config.overlap > 0:
        tradeoffs.append("overlap_increases_sample_count_and_redundancy")
    if len(config.features) >= 8:
        tradeoffs.append("richer_feature_set_increases_explainability_and_dimensionality")
    return tradeoffs


def _structuring_failure_modes(outcome: ReasoningOutcome) -> list[str]:
    if outcome in {"contradicted", "overcorrected"}:
        return ["structuring_choice_hurt_downstream_result"]
    if outcome == "inconclusive":
        return ["requires_downstream_metric_evidence"]
    return []


def _structuring_lesson(
    decision: StructuringDecision,
    execution_result_summary: str | None,
) -> str:
    result = execution_result_summary or "Pendiente de evidencia aguas abajo."
    return (
        f"La estructuracion elegida fue {decision.structuring_config.window_size} "
        f"muestras con overlap {decision.structuring_config.overlap}. {result}"
    )


def _structuring_reusable_lessons(config: StructuringConfig) -> list[str]:
    return sorted(
        {
            "structuring_decisions_require_downstream_evaluation",
            f"window_size_{config.window_size}",
            f"overlap_{config.overlap}",
            f"label_mode_{config.label_mode}",
        }
    )


def _structuring_when_to_reuse(
    state: TFMStateModel,
    config: StructuringConfig,
) -> list[str]:
    return [
        f"dataset={state.project_context.dataset}",
        f"sample_rate={config.target_sample_rate_hz}",
        f"main_channel={config.main_channel}",
        "the agent needs prior evidence about window and feature trade-offs",
    ]


def _structuring_when_not_to_reuse(state: TFMStateModel) -> list[str]:
    return [
        "target sample rate or sensor channel differs from the current context",
        "temporal split policy has changed and leakage risk must be rechecked",
        f"dataset is not comparable with {state.project_context.dataset}",
    ]


def _evaluation_context_summary(
    state: TFMStateModel,
    decision: EvaluationDecision,
) -> str:
    metrics = _metrics_dict(state.metrics)
    temporal_metrics = _temporal_metric_summary(metrics)
    return (
        f"Decision del evaluador para {state.project_context.dataset}. "
        f"Perfil={state.project_context.supervision_profile}. "
        f"Metricas: precision={_fmt(metrics.get('precision'))}, "
        f"recall={_fmt(metrics.get('recall'))}, "
        f"F1={_fmt(metrics.get('f1_score'))}, "
        f"FPR={_fmt(metrics.get('false_positive_rate'))}. "
        + ("" if temporal_metrics is None else f"Metricas temporales: {temporal_metrics}. ")
        + f"Aprobada={decision.evaluation.approved}. Razonamiento: {decision.rationale}"
        + (
            ""
            if decision.operational_assessment is None
            else f" Assessment operacional: {decision.operational_assessment}"
        )
    )


def _evaluation_options(decision: EvaluationDecision) -> list[DecisionOption]:
    return [
        DecisionOption(
            option_id="approve_and_continue",
            option_type="evaluation_action",
            description="Aprobar la ejecucion y continuar.",
            expected_effect="Permitir que el pipeline cierre la run como valida.",
            risk_notes=["Only valid if recall and FPR satisfy the local protocol."],
            selected=decision.evaluation.approved,
        ),
        DecisionOption(
            option_id="reject_and_retry",
            option_type="evaluation_action",
            description="Rechazar la ejecucion y pedir nueva configuracion.",
            expected_effect="Evitar aceptar metricas que no cumplen el protocolo.",
            risk_notes=["Can trigger another agentic iteration if retry budget remains."],
            selected=not decision.evaluation.approved,
        ),
    ]


def _evaluation_action(decision: EvaluationDecision) -> str:
    status = "approve" if decision.evaluation.approved else "reject"
    return f"{status}; next_action={decision.evaluation.next_action}"


def _evaluation_evidence(
    decision: EvaluationDecision,
    memory_context: RetrievedMemoryContext | None,
) -> list[str]:
    evidence = ["metrics_report", "evaluation_thresholds", "evaluation_protocol"]
    evidence.extend(decision.tool_names)
    evidence.extend(decision.evidence_refs)
    if memory_context is not None and memory_context.items:
        evidence.append("retrieved_memory_context")
    return list(dict.fromkeys(evidence))


def _evaluation_tradeoffs(
    metrics: MetricsReport | None,
    decision: EvaluationDecision,
) -> list[str]:
    if metrics is None:
        return ["metrics_missing"]
    tradeoffs: list[str] = []
    if metrics.recall is not None and decision.min_recall_required is not None:
        if metrics.recall < decision.min_recall_required:
            tradeoffs.append("recall_below_required")
    if (
        metrics.false_positive_rate is not None
        and decision.max_false_positive_rate is not None
    ):
        if metrics.false_positive_rate > decision.max_false_positive_rate:
            tradeoffs.append("false_positive_rate_above_allowed")
    if decision.evaluation.approved:
        tradeoffs.append("metrics_satisfy_local_protocol")
    if decision.temporal_guardrail_checks:
        tradeoffs.extend(decision.temporal_guardrail_checks)
    return tradeoffs or ["no_blocking_metric_tradeoff"]


def _evaluation_failure_modes(
    metrics: MetricsReport | None,
    decision: EvaluationDecision,
) -> list[str]:
    if decision.evaluation.approved:
        return []
    return _evaluation_tradeoffs(metrics, decision)


def _evaluation_outcome(
    state: TFMStateModel,
    decision: EvaluationDecision,
) -> ReasoningOutcome:
    if state.metrics is None:
        return "inconclusive"
    if (
        state.project_context.supervision_profile == "run_to_failure_degradation"
        and decision.evaluation.approved
        and (decision.evaluation.limitations or decision.temporal_guardrail_checks)
    ):
        return "partially_supported"
    return "supported"


def _evaluation_lesson(decision: EvaluationDecision) -> str:
    return (
        f"El evaluador decidio {decision.evaluation.next_action}: "
        f"{decision.evaluation.summary}"
    )


def _evaluation_reusable_lessons(decision: EvaluationDecision) -> list[str]:
    lessons = ["evaluation_thresholds_are_binding"]
    if decision.evaluation.approved:
        lessons.append("approval_requires_protocol_compliance")
    else:
        lessons.append("rejection_can_be_correct_even_after_partial_improvement")
    if decision.temporal_guardrail_checks:
        lessons.append("temporal_guardrails_are_binding")
    if decision.operational_assessment is not None:
        lessons.append("operational_defensibility_must_be_documented")
    return lessons


def _evaluation_when_to_reuse(
    state: TFMStateModel,
    decision: EvaluationDecision,
) -> list[str]:
    conditions = [
        f"dataset={state.project_context.dataset}",
        f"min_recall_required={decision.min_recall_required}",
        f"max_false_positive_rate={decision.max_false_positive_rate}",
        "the evaluator needs prior evidence about metric trade-offs",
        f"supervision_profile={state.project_context.supervision_profile}",
    ]
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        conditions.extend(
            [
                f"label_source={state.project_context.label_source}",
                f"label_granularity={state.project_context.label_granularity}",
                "the evaluator needs prior temporal guardrails for run-to-failure",
            ]
        )
    return conditions


def _evaluation_when_not_to_reuse(state: TFMStateModel) -> list[str]:
    conditions = [
        "labels, temporal split or metric definitions changed",
        "NASA IMS real is being evaluated without a defended labeling policy",
        "human review marks the prior judgment as unsafe or excluded",
    ]
    if state.project_context.supervision_profile == "run_to_failure_degradation":
        conditions.extend(
            [
                "current task requires real RUL estimation rather than historic lead time",
                "alert policy no longer separates isolated spike from sustained alert",
                "official per-window labels replace temporal proxy labels",
            ]
        )
    return conditions


def _temporal_metric_summary(metrics: dict[str, float | None]) -> str | None:
    names = [
        "degradation_confirmed_degradation_before_failure_rate",
        "degradation_mean_persistent_lead_time_to_failure",
        "degradation_mean_health_index_drop",
        "degradation_mean_health_monotonicity",
        "degradation_mean_health_robustness",
        "degradation_mean_health_nominal_volatility",
        "degradation_mean_health_indicator_score",
        "degradation_detected_before_failure_rate",
        "degradation_mean_lead_time_to_failure",
        "degradation_mean_false_alarm_rate_nominal",
        "degradation_mean_score_trend_spearman",
        "degradation_missed_runs",
        "degradation_missed_confirmed_degradation_runs",
    ]
    values = [
        f"{name}={_fmt(metrics.get(name))}"
        for name in names
        if name in metrics
    ]
    return None if not values else ", ".join(values)


def _modeling_risks(config: ModelingConfig) -> list[str]:
    risks: list[str] = []
    threshold = config.hyperparameters.get("threshold_quantile")
    if isinstance(threshold, (int, float)):
        if threshold <= 0.5:
            risks.append("threshold_quantile muy bajo puede disparar falsos positivos")
        if threshold >= 0.99:
            risks.append("threshold_quantile alto puede dejar anomalias sin detectar")
    if config.model_name == "pca_reconstruction_error":
        risks.append("PCA puede reducir FPR pero perder recall en fallos no lineales")
    if config.model_name == "autoencoder_dense":
        risks.append(
            "autoencoder_dense puede mejorar sensibilidad no lineal pero requiere readiness y control de falsas alarmas"
        )
    return risks


def _tradeoffs(
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> list[str]:
    tradeoffs: list[str] = []
    if _improved(before, after, "recall") and _worsened_fpr(before, after):
        tradeoffs.append("recall_improved_fpr_worsened")
    if _improved(before, after, "f1_score"):
        tradeoffs.append("f1_improved")
    if _worse(before, after, "precision"):
        tradeoffs.append("precision_worsened")
    if _improved_fpr(before, after):
        tradeoffs.append("fpr_improved")
    return tradeoffs or ["no_clear_metric_tradeoff"]


def _failure_modes(
    postmortem: AgentReasoningPostmortem,
    after: dict[str, float | None],
    evaluation: EvaluationResult | None,
) -> list[str]:
    modes: list[str] = []
    if postmortem.outcome == "overcorrected":
        modes.append("overcorrection")
    if postmortem.outcome == "contradicted":
        modes.append("decision_contradicted_by_metrics")
    if _metric(after, "false_positive_rate") > FPR_TARGET:
        modes.append("false_positive_rate_above_target")
    if _metric(after, "recall") < RECALL_TARGET:
        modes.append("recall_below_target")
    if evaluation is not None and not evaluation.approved:
        modes.append("evaluation_rejected")
    return sorted(set(modes)) or ["requires_more_evidence"]


def _lesson_learned(
    postmortem: AgentReasoningPostmortem,
    evaluation: EvaluationResult | None,
) -> str:
    if evaluation is None:
        return postmortem.automatic_critique
    return f"{postmortem.automatic_critique} Decision evaluadora: {evaluation.summary}"


def _episode_lessons(
    postmortem: AgentReasoningPostmortem,
    before: dict[str, float | None],
    after: dict[str, float | None],
    evaluation: EvaluationResult | None,
) -> list[str]:
    lessons = list(postmortem.reusable_lessons)
    if _improved(before, after, "recall") and _worsened_fpr(before, after):
        lessons.append("recall_gain_must_be_checked_against_fpr")
    if evaluation is not None and not evaluation.approved:
        lessons.append("metric_improvement_can_still_be_rejected")
    if postmortem.outcome == "partially_supported":
        lessons.append("compare_model_family_after_partial_threshold_gain")
    return sorted(set(lessons))


def _when_to_reuse(
    postmortem: AgentReasoningPostmortem,
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> list[str]:
    conditions = [
        f"decision_type=modeling and outcome={postmortem.outcome}",
        "the agent needs prior evidence about metric trade-offs",
    ]
    if _metric(before, "recall") < RECALL_TARGET:
        conditions.append("previous run has recall below target")
    if _improved(before, after, "recall"):
        conditions.append("a similar action improved recall")
    return conditions


def _when_not_to_reuse(
    postmortem: AgentReasoningPostmortem,
    before: dict[str, float | None],
    after: dict[str, float | None],
    evaluation: EvaluationResult | None,
) -> list[str]:
    conditions: list[str] = []
    if postmortem.outcome in {"overcorrected", "contradicted"}:
        conditions.append("do not reuse as a positive recommendation")
    if _metric(after, "false_positive_rate") > FPR_TARGET:
        conditions.append("false positive rate after the decision is above target")
    if evaluation is not None and not evaluation.approved:
        conditions.append("the evaluator rejected the final execution")
    return conditions or ["do not reuse without checking current dataset constraints"]


def _risk_if_misused(
    postmortem: AgentReasoningPostmortem,
    after: dict[str, float | None],
) -> str:
    if postmortem.outcome == "overcorrected":
        return "Puede convertir una mejora de recall en exceso de falsas alarmas."
    if _metric(after, "false_positive_rate") > FPR_TARGET:
        return "Puede aceptar una mejora parcial aunque el FPR siga fuera de objetivo."
    if postmortem.outcome == "contradicted":
        return "Puede repetir una accion que las metricas ya contradijeron."
    return "Puede reutilizarse fuera de contexto si no se revisan dataset y metricas."


def _episode_markdown(episode: DecisionEpisode) -> str:
    lines = [
        f"# Episodio de decision {episode.run_id}",
        "",
        f"- Agente: `{episode.agent_name}`",
        f"- Tipo: `{episode.decision_type}`",
        f"- Decision: `{episode.decision_id}`",
        f"- Resultado: `{episode.outcome}`",
        f"- Dataset: `{episode.dataset or 'n/a'}`",
        "",
        "## Contexto",
        "",
        episode.context_summary,
        "",
        "## Accion elegida",
        "",
        episode.chosen_action,
        "",
        "## Leccion",
        "",
        episode.lesson_learned,
        "",
        "## Alternativas",
        "",
    ]
    for option in episode.options_considered:
        selected = "si" if option.selected else "no"
        lines.append(
            f"- `{option.option_id}` ({option.option_type}, seleccionada={selected}): "
            f"{option.description}"
        )
    lines.extend(
        [
            "",
            "## Reutilizacion",
            "",
            "- Usar cuando: " + "; ".join(episode.when_to_reuse),
            "- No usar cuando: " + "; ".join(episode.when_not_to_reuse),
            f"- Riesgo: {episode.risk_if_misused or 'n/a'}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _candidate_markdown(candidate: MemoryCandidate) -> str:
    lines = [
        f"# Candidato de memoria {candidate.candidate_id}",
        "",
        f"- Agente destino: `{candidate.target_agent}`",
        f"- Rol de memoria: `{candidate.memory_role}`",
        f"- Reutilizable: `{candidate.reusable_as_context}`",
        f"- Excluido: `{candidate.exclude_from_context}`",
        f"- Dataset: `{candidate.dataset or 'n/a'}`",
        "",
        "## Resumen",
        "",
        candidate.summary,
        "",
        "## Contenido",
        "",
        candidate.content,
        "",
        "## Politica de reutilizacion",
        "",
        "- Usar cuando: " + "; ".join(candidate.when_to_reuse),
        "- No usar cuando: " + "; ".join(candidate.when_not_to_reuse),
        f"- Riesgo: {candidate.risk_if_misused or 'n/a'}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _metric(metrics: dict[str, float | None], name: str) -> float:
    value = metrics.get(name)
    return 0.0 if value is None else value


def _improved(
    before: dict[str, float | None],
    after: dict[str, float | None],
    name: str,
) -> bool:
    before_value = before.get(name)
    after_value = after.get(name)
    return before_value is not None and after_value is not None and after_value > before_value


def _worse(
    before: dict[str, float | None],
    after: dict[str, float | None],
    name: str,
) -> bool:
    before_value = before.get(name)
    after_value = after.get(name)
    return before_value is not None and after_value is not None and after_value < before_value


def _worsened_fpr(
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> bool:
    before_value = before.get("false_positive_rate")
    after_value = after.get("false_positive_rate")
    return before_value is not None and after_value is not None and after_value > before_value


def _improved_fpr(
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> bool:
    before_value = before.get("false_positive_rate")
    after_value = after.get("false_positive_rate")
    return before_value is not None and after_value is not None and after_value < before_value


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
