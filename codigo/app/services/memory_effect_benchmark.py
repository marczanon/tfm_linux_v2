"""Benchmark offline para medir si la memoria RAG influye en las runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import RetrievedMemoryContext
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.memory_quality_gate import (
    MemoryQualityGateReport,
    evaluate_memory_quality,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    load_run_snapshot,
)
from codigo.app.services.run_registry import RunComparison, compare_runs

BenchmarkAgentName = Literal[
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
]

MemoryAgentBenchmarkOutcome = Literal[
    "no_decision",
    "no_retrieval",
    "no_relevant_memory_returned",
    "retrieved_not_used",
    "used_aligned",
    "used_with_policy_warning",
    "usage_invalid",
]

MemoryRunMode = Literal[
    "no_memory_observed",
    "no_relevant_memory_returned",
    "retrieval_only",
    "memory_used",
    "memory_usage_invalid",
]

MemoryControlledVariant = Literal[
    "baseline",
    "memory_off",
    "memory_full",
    "memory_filtered",
    "memory_conflict_excluded",
    "retrieval_only",
    "unknown",
]


class MetricDelta(StrictBaseModel):
    """Diferencia de una metrica respecto a una run baseline."""

    metric: str = Field(min_length=1)
    baseline_value: float | None = None
    run_value: float | None = None
    delta: float | None = None
    higher_is_better: bool
    direction: Literal["better", "worse", "unchanged", "unknown"]


class MemoryAgentBenchmark(StrictBaseModel):
    """Resumen de retrieval y uso declarado de memoria para un agente."""

    agent_name: BenchmarkAgentName
    decision_id: str | None = None
    retrieval_available: bool
    retrieved_count: NonNegativeInt = 0
    cited_count: NonNegativeInt = 0
    ignored_count: NonNegativeInt = 0
    similarity_min: float | None = None
    similarity_mean: float | None = None
    similarity_max: float | None = None
    retrieval_backend: str | None = None
    embedding_model: str | None = None
    memory_context_id: str | None = None
    retrieved_memory_record_ids: list[str] = Field(default_factory=list)
    cited_memory_record_ids: list[str] = Field(default_factory=list)
    ignored_memory_record_ids: list[str] = Field(default_factory=list)
    cited_without_retrieval: list[str] = Field(default_factory=list)
    missing_usage_declarations: list[str] = Field(default_factory=list)
    missing_risk_mitigations: list[str] = Field(default_factory=list)
    quality_gate: MemoryQualityGateReport | None = None
    quality_pass_count: NonNegativeInt = 0
    quality_caution_count: NonNegativeInt = 0
    quality_exclude_candidate_count: NonNegativeInt = 0
    quality_caution_ids: list[str] = Field(default_factory=list)
    quality_exclude_candidate_ids: list[str] = Field(default_factory=list)
    memory_usage_summary: str | None = None
    outcome: MemoryAgentBenchmarkOutcome
    summary: str = Field(min_length=1)


class MemoryRunEffectSignals(StrictBaseModel):
    """Senales comparativas frente a una run baseline."""

    baseline_run_id: str | None = None
    config_changed_from_baseline: bool | None = None
    changed_config_sections: list[str] = Field(default_factory=list)
    metric_deltas: list[MetricDelta] = Field(default_factory=list)
    any_metric_delta: bool = False
    note: str = Field(min_length=1)


class MemoryRunBenchmark(StrictBaseModel):
    """Resultado de benchmark de memoria para una run."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    controlled_variant: MemoryControlledVariant = "unknown"
    supervision_profile: str | None = None
    model_name: str | None = None
    approved: bool | None = None
    memory_mode: MemoryRunMode
    retrieved_context_count: NonNegativeInt = 0
    retrieved_memory_record_count: NonNegativeInt = 0
    cited_memory_record_count: NonNegativeInt = 0
    memory_used_by_agents: list[BenchmarkAgentName] = Field(default_factory=list)
    agents: list[MemoryAgentBenchmark] = Field(default_factory=list)
    effect_signals: MemoryRunEffectSignals


class MemoryEffectBenchmarkReport(StrictBaseModel):
    """Informe agregado para evaluar si la memoria esta aportando algo."""

    report_id: str = Field(min_length=1)
    run_ids: list[str] = Field(min_length=1)
    baseline_run_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_count: NonNegativeInt
    retrieval_run_count: NonNegativeInt
    memory_used_run_count: NonNegativeInt
    invalid_usage_run_count: NonNegativeInt
    quality_gate_warning_run_count: NonNegativeInt = 0
    agent_usage_counts: dict[str, int] = Field(default_factory=dict)
    variant_counts: dict[str, int] = Field(default_factory=dict)
    runs: list[MemoryRunBenchmark] = Field(default_factory=list)
    run_comparison: RunComparison | None = None
    executive_summary: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class MemoryEffectBenchmarkArtifacts(StrictBaseModel):
    """Artefactos persistidos para el benchmark de memoria."""

    benchmark_path: str
    report_path: str
    benchmark: MemoryEffectBenchmarkReport


def benchmark_memory_effect(
    *,
    run_ids: list[str],
    baseline_run_id: str | None = None,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    output_dir: str | Path | None = None,
    agents: list[BenchmarkAgentName] | None = None,
    variant_labels: dict[str, MemoryControlledVariant] | None = None,
) -> MemoryEffectBenchmarkArtifacts:
    """Construye y escribe un benchmark offline de efecto de memoria."""

    report = build_memory_effect_benchmark(
        run_ids=run_ids,
        baseline_run_id=baseline_run_id,
        runs_dir=runs_dir,
        agents=agents,
        variant_labels=variant_labels,
    )
    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else Path("codigo/reports")
        / "memory_benchmarks"
        / _safe_report_dir_name(report.report_id)
    )
    return write_memory_effect_benchmark(report, target_dir)


def build_memory_effect_benchmark(
    *,
    run_ids: list[str],
    baseline_run_id: str | None = None,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    agents: list[BenchmarkAgentName] | None = None,
    variant_labels: dict[str, MemoryControlledVariant] | None = None,
) -> MemoryEffectBenchmarkReport:
    """Evalua retrieval, uso declarado y senales frente a baseline."""

    normalized_run_ids = _normalize_run_ids(run_ids, baseline_run_id)
    states = {
        run_id: _load_state(run_id, runs_dir)
        for run_id in normalized_run_ids
    }
    baseline_state = None if baseline_run_id is None else states[baseline_run_id]
    comparison = (
        compare_runs(normalized_run_ids, runs_dir)
        if len(normalized_run_ids) >= 2
        else None
    )
    agent_names = agents or [
        "cleaner",
        "structurer",
        "modeler",
        "evaluator",
        "report_writer",
    ]
    runs = [
        _run_benchmark(
            state,
            baseline_state=baseline_state,
            agents=agent_names,
            controlled_variant=_variant_for_run(
                state.run_id,
                baseline_run_id=baseline_run_id,
                variant_labels=variant_labels,
            ),
        )
        for state in states.values()
    ]
    agent_usage_counts = _agent_usage_counts(runs)
    report = MemoryEffectBenchmarkReport(
        report_id=f"memory_effect_benchmark:{'_'.join(normalized_run_ids)}",
        run_ids=normalized_run_ids,
        baseline_run_id=baseline_run_id,
        run_count=len(runs),
        retrieval_run_count=sum(
            run.retrieved_memory_record_count > 0 for run in runs
        ),
        memory_used_run_count=sum(
            run.memory_mode == "memory_used" for run in runs
        ),
        invalid_usage_run_count=sum(
            run.memory_mode == "memory_usage_invalid" for run in runs
        ),
        quality_gate_warning_run_count=sum(
            any(
                agent.quality_caution_count or agent.quality_exclude_candidate_count
                for agent in run.agents
            )
            for run in runs
        ),
        agent_usage_counts=agent_usage_counts,
        variant_counts=_variant_counts(runs),
        runs=runs,
        run_comparison=comparison,
        executive_summary=_executive_summary(runs),
        limitations=[
            (
                "Este benchmark observa senales comparativas, no prueba "
                "causalidad si las runs no fueron ejecutadas como pares "
                "controlados con la misma configuracion salvo memoria."
            ),
            (
                "La memoria solo se considera usada cuando el agente declara "
                "used_memory_context=true y cita IDs recuperados."
            ),
            (
                "El quality gate marca candidatos de exclusion o cautela, pero "
                "no consolida recuerdos ni sustituye la deliberacion del agente."
            ),
        ],
    )
    return report


def write_memory_effect_benchmark(
    benchmark: MemoryEffectBenchmarkReport,
    output_dir: str | Path,
) -> MemoryEffectBenchmarkArtifacts:
    """Persiste el benchmark en JSON y Markdown."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    benchmark_path = output / "memory_effect_benchmark.json"
    report_path = output / "memory_effect_benchmark.md"
    benchmark_path.write_text(
        json.dumps(benchmark.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_benchmark_markdown(benchmark), encoding="utf-8")
    return MemoryEffectBenchmarkArtifacts(
        benchmark_path=benchmark_path.as_posix(),
        report_path=report_path.as_posix(),
        benchmark=benchmark,
    )


def _run_benchmark(
    state: TFMStateModel,
    *,
    baseline_state: TFMStateModel | None,
    agents: list[BenchmarkAgentName],
    controlled_variant: MemoryControlledVariant,
) -> MemoryRunBenchmark:
    agent_benchmarks = [_agent_benchmark(state, agent) for agent in agents]
    retrieved_context_count = sum(agent.retrieval_available for agent in agent_benchmarks)
    retrieved_record_count = sum(agent.retrieved_count for agent in agent_benchmarks)
    cited_record_count = sum(agent.cited_count for agent in agent_benchmarks)
    used_agents = [
        agent.agent_name
        for agent in agent_benchmarks
        if agent.outcome in {"used_aligned", "used_with_policy_warning"}
    ]
    return MemoryRunBenchmark(
        run_id=state.run_id,
        dataset=state.project_context.dataset,
        controlled_variant=controlled_variant,
        supervision_profile=state.project_context.supervision_profile,
        model_name=None if state.modeling_config is None else state.modeling_config.model_name,
        approved=None if state.evaluation is None else state.evaluation.approved,
        memory_mode=_run_memory_mode(agent_benchmarks),
        retrieved_context_count=retrieved_context_count,
        retrieved_memory_record_count=retrieved_record_count,
        cited_memory_record_count=cited_record_count,
        memory_used_by_agents=used_agents,
        agents=agent_benchmarks,
        effect_signals=_effect_signals(state, baseline_state),
    )


def _agent_benchmark(
    state: TFMStateModel,
    agent_name: BenchmarkAgentName,
) -> MemoryAgentBenchmark:
    decision = _latest_agent_decision(state, agent_name)
    context = _load_memory_context(state, agent_name)
    quality_gate = (
        None
        if context is None
        else evaluate_memory_quality(
            context,
            supervision_profile=state.project_context.supervision_profile,
        )
    )
    retrieved_ids = (
        [] if context is None else [item.record.memory_record_id for item in context.items]
    )
    cited_ids = _decision_memory_ids(decision)
    declared_use_ids = _declared_use_ids(decision)
    cited_without_retrieval = sorted(set(cited_ids) - set(retrieved_ids))
    missing_usage = sorted(set(cited_ids) - set(declared_use_ids))
    ignored_ids = sorted(set(retrieved_ids) - set(cited_ids))
    missing_risk = _missing_risk_mitigations(decision, context)
    quality_exclude_ids = (
        []
        if quality_gate is None
        else [
            item.memory_record_id
            for item in quality_gate.items
            if item.recommendation == "exclude_candidate"
        ]
    )
    quality_caution_ids = (
        []
        if quality_gate is None
        else [
            item.memory_record_id
            for item in quality_gate.items
            if item.recommendation == "caution"
        ]
    )
    cited_quality_exclude_ids = sorted(set(cited_ids) & set(quality_exclude_ids))
    similarities = [] if context is None else [item.similarity for item in context.items]
    outcome = _agent_outcome(
        decision=decision,
        context=context,
        cited_ids=cited_ids,
        cited_without_retrieval=cited_without_retrieval,
        missing_usage=missing_usage,
        missing_risk_mitigations=missing_risk,
        cited_quality_exclude_ids=cited_quality_exclude_ids,
    )
    return MemoryAgentBenchmark(
        agent_name=agent_name,
        decision_id=None if decision is None else _optional_str(decision.get("decision_id")),
        retrieval_available=context is not None,
        retrieved_count=len(retrieved_ids),
        cited_count=len(cited_ids),
        ignored_count=len(ignored_ids),
        similarity_min=None if not similarities else min(similarities),
        similarity_mean=None if not similarities else sum(similarities) / len(similarities),
        similarity_max=None if not similarities else max(similarities),
        retrieval_backend=None if context is None else context.retrieval_backend,
        embedding_model=None if context is None else context.embedding_model,
        memory_context_id=None if context is None else context.context_id,
        retrieved_memory_record_ids=retrieved_ids,
        cited_memory_record_ids=cited_ids,
        ignored_memory_record_ids=ignored_ids,
        cited_without_retrieval=cited_without_retrieval,
        missing_usage_declarations=missing_usage,
        missing_risk_mitigations=missing_risk,
        quality_gate=quality_gate,
        quality_pass_count=0 if quality_gate is None else quality_gate.pass_count,
        quality_caution_count=0 if quality_gate is None else quality_gate.caution_count,
        quality_exclude_candidate_count=(
            0 if quality_gate is None else quality_gate.exclude_candidate_count
        ),
        quality_caution_ids=quality_caution_ids,
        quality_exclude_candidate_ids=quality_exclude_ids,
        memory_usage_summary=_decision_memory_summary(decision),
        outcome=outcome,
        summary=_agent_summary(agent_name, outcome, len(retrieved_ids), len(cited_ids)),
    )


def _agent_outcome(
    *,
    decision: dict[str, Any] | None,
    context: RetrievedMemoryContext | None,
    cited_ids: list[str],
    cited_without_retrieval: list[str],
    missing_usage: list[str],
    missing_risk_mitigations: list[str],
    cited_quality_exclude_ids: list[str],
) -> MemoryAgentBenchmarkOutcome:
    if decision is None:
        return "no_decision"
    if context is None:
        return "no_retrieval"
    if not context.items:
        return "no_relevant_memory_returned"
    used_memory = bool(decision.get("used_memory_context"))
    if not used_memory:
        return "retrieved_not_used"
    if (
        not cited_ids
        or cited_without_retrieval
        or missing_usage
        or _optional_str(decision.get("memory_context_id")) != context.context_id
    ):
        return "usage_invalid"
    if missing_risk_mitigations or cited_quality_exclude_ids:
        return "used_with_policy_warning"
    return "used_aligned"


def _run_memory_mode(
    agent_benchmarks: list[MemoryAgentBenchmark],
) -> MemoryRunMode:
    outcomes = {agent.outcome for agent in agent_benchmarks}
    if "usage_invalid" in outcomes:
        return "memory_usage_invalid"
    if "used_aligned" in outcomes or "used_with_policy_warning" in outcomes:
        return "memory_used"
    if "retrieved_not_used" in outcomes:
        return "retrieval_only"
    if "no_relevant_memory_returned" in outcomes:
        return "no_relevant_memory_returned"
    return "no_memory_observed"


def _effect_signals(
    state: TFMStateModel,
    baseline_state: TFMStateModel | None,
) -> MemoryRunEffectSignals:
    if baseline_state is None or baseline_state.run_id == state.run_id:
        return MemoryRunEffectSignals(
            baseline_run_id=None if baseline_state is None else baseline_state.run_id,
            config_changed_from_baseline=False if baseline_state is not None else None,
            note=(
                "Run usada como baseline."
                if baseline_state is not None
                else "No se proporciono baseline; solo se audita actividad de memoria."
            ),
        )
    changed_sections = _changed_config_sections(state, baseline_state)
    deltas = _metric_deltas(state, baseline_state)
    any_delta = any(item.delta not in {None, 0.0} for item in deltas)
    return MemoryRunEffectSignals(
        baseline_run_id=baseline_state.run_id,
        config_changed_from_baseline=bool(changed_sections),
        changed_config_sections=changed_sections,
        metric_deltas=deltas,
        any_metric_delta=any_delta,
        note=(
            "Hay senales comparativas frente al baseline; no implican causalidad "
            "si la unica diferencia experimental no fue la memoria."
        ),
    )


def _changed_config_sections(
    state: TFMStateModel,
    baseline_state: TFMStateModel,
) -> list[str]:
    sections: list[str] = []
    for name in ("cleaning_config", "structuring_config", "modeling_config"):
        if _model_dump(getattr(state, name)) != _model_dump(getattr(baseline_state, name)):
            sections.append(name.replace("_config", ""))
    return sections


def _metric_deltas(
    state: TFMStateModel,
    baseline_state: TFMStateModel,
) -> list[MetricDelta]:
    metrics = {
        "precision": True,
        "recall": True,
        "f1_score": True,
        "false_positive_rate": False,
        "degradation_detected_before_failure_rate": True,
        "degradation_mean_lead_time_to_failure": True,
        "degradation_mean_false_alarm_rate_nominal": False,
        "degradation_mean_score_trend_spearman": True,
        "degradation_missed_runs": False,
        "degradation_mean_initial_final_separation": True,
    }
    return [
        _metric_delta(
            metric,
            baseline_value=_metric_value(baseline_state, metric),
            run_value=_metric_value(state, metric),
            higher_is_better=higher_is_better,
        )
        for metric, higher_is_better in metrics.items()
        if _metric_value(baseline_state, metric) is not None
        or _metric_value(state, metric) is not None
    ]


def _metric_delta(
    metric: str,
    *,
    baseline_value: float | None,
    run_value: float | None,
    higher_is_better: bool,
) -> MetricDelta:
    if baseline_value is None or run_value is None:
        delta = None
        direction: Literal["better", "worse", "unchanged", "unknown"] = "unknown"
    else:
        delta = run_value - baseline_value
        if delta == 0:
            direction = "unchanged"
        elif (delta > 0 and higher_is_better) or (delta < 0 and not higher_is_better):
            direction = "better"
        else:
            direction = "worse"
    return MetricDelta(
        metric=metric,
        baseline_value=baseline_value,
        run_value=run_value,
        delta=delta,
        higher_is_better=higher_is_better,
        direction=direction,
    )


def _metric_value(state: TFMStateModel, metric: str) -> float | None:
    if state.metrics is None:
        return None
    if hasattr(state.metrics, metric):
        value = getattr(state.metrics, metric)
        return _optional_float(value)
    extra_value = state.metrics.extra.get(metric)
    return _optional_float(extra_value)


def _load_state(run_id: str, runs_dir: str | Path) -> TFMStateModel:
    snapshot = load_run_snapshot(run_id, runs_dir)
    return TFMStateModel.model_validate_json(
        Path(snapshot.state_path).read_text(encoding="utf-8")
    )


def _latest_agent_decision(
    state: TFMStateModel,
    agent_name: BenchmarkAgentName,
) -> dict[str, Any] | None:
    for message in reversed(state.messages):
        if message.role != "agent" or message.name != agent_name:
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _load_memory_context(
    state: TFMStateModel,
    agent_name: BenchmarkAgentName,
) -> RetrievedMemoryContext | None:
    path = _artifact_path(state, f"{agent_name}_retrieved_memory_context")
    if path is None:
        return None
    try:
        return RetrievedMemoryContext.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None


def _artifact_path(state: TFMStateModel, name: str) -> str | None:
    matches = [artifact.path for artifact in state.artifacts if artifact.name == name]
    return matches[-1] if matches else None


def _decision_memory_ids(decision: dict[str, Any] | None) -> list[str]:
    if decision is None:
        return []
    raw = decision.get("memory_record_ids")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item)]


def _declared_use_ids(decision: dict[str, Any] | None) -> list[str]:
    if decision is None:
        return []
    raw = decision.get("memory_record_uses")
    if not isinstance(raw, list):
        return []
    return [
        str(item.get("memory_record_id"))
        for item in raw
        if isinstance(item, dict) and item.get("memory_record_id")
    ]


def _decision_memory_summary(decision: dict[str, Any] | None) -> str | None:
    if decision is None:
        return None
    return _optional_str(decision.get("memory_usage_summary"))


def _missing_risk_mitigations(
    decision: dict[str, Any] | None,
    context: RetrievedMemoryContext | None,
) -> list[str]:
    if decision is None or context is None:
        return []
    uses_by_id = {
        str(item.get("memory_record_id")): item
        for item in decision.get("memory_record_uses", [])
        if isinstance(item, dict) and item.get("memory_record_id")
    }
    missing: list[str] = []
    for item in context.items:
        record = item.record
        if record.memory_record_id not in _decision_memory_ids(decision):
            continue
        use = uses_by_id.get(record.memory_record_id)
        if record.memory_role in {"warning", "boundary_case"} and not (
            isinstance(use, dict) and _optional_str(use.get("risk_mitigation"))
        ):
            missing.append(record.memory_record_id)
    return missing


def _agent_summary(
    agent_name: str,
    outcome: MemoryAgentBenchmarkOutcome,
    retrieved_count: int,
    cited_count: int,
) -> str:
    if outcome == "used_aligned":
        return (
            f"{agent_name} recupero {retrieved_count} recuerdos y cito "
            f"{cited_count} con declaracion valida."
        )
    if outcome == "used_with_policy_warning":
        return (
            f"{agent_name} declaro uso de memoria, pero hay advertencias de "
            "mitigacion o politica."
        )
    if outcome == "usage_invalid":
        return f"{agent_name} declaro memoria de forma invalida o incompleta."
    if outcome == "retrieved_not_used":
        return (
            f"{agent_name} recibio {retrieved_count} recuerdos, pero no declaro "
            "uso en su decision."
        )
    if outcome == "no_relevant_memory_returned":
        return f"{agent_name} consulto memoria, pero no se recuperaron recuerdos."
    if outcome == "no_decision":
        return f"No se encontro decision persistida para {agent_name}."
    return f"{agent_name} no tuvo retrieval de memoria persistido."


def _executive_summary(runs: list[MemoryRunBenchmark]) -> str:
    used = [run.run_id for run in runs if run.memory_mode == "memory_used"]
    invalid = [run.run_id for run in runs if run.memory_mode == "memory_usage_invalid"]
    retrieval_only = [run.run_id for run in runs if run.memory_mode == "retrieval_only"]
    if invalid:
        return (
            "La memoria hizo algo, pero hay uso invalido o incompleto en: "
            + ", ".join(invalid)
            + "."
        )
    if used:
        return (
            "La memoria hizo algo declarado por agentes en: "
            + ", ".join(used)
            + "."
        )
    if retrieval_only:
        return (
            "La memoria fue recuperada pero no declarada como usada en: "
            + ", ".join(retrieval_only)
            + "."
        )
    return "No se observa actividad de memoria en las runs analizadas."


def _agent_usage_counts(runs: list[MemoryRunBenchmark]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        for agent in run.memory_used_by_agents:
            counts[agent] = counts.get(agent, 0) + 1
    return dict(sorted(counts.items()))


def _variant_counts(runs: list[MemoryRunBenchmark]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.controlled_variant] = counts.get(run.controlled_variant, 0) + 1
    return dict(sorted(counts.items()))


def _variant_for_run(
    run_id: str,
    *,
    baseline_run_id: str | None,
    variant_labels: dict[str, MemoryControlledVariant] | None,
) -> MemoryControlledVariant:
    if variant_labels is not None and run_id in variant_labels:
        return variant_labels[run_id]
    if baseline_run_id is not None and run_id == baseline_run_id:
        return "baseline"
    return "unknown"


def _normalize_run_ids(
    run_ids: list[str],
    baseline_run_id: str | None,
) -> list[str]:
    if not run_ids:
        raise ValueError("memory benchmark requires at least one run_id")
    normalized: list[str] = []
    for run_id in ([baseline_run_id] if baseline_run_id else []) + run_ids:
        if run_id is None:
            continue
        if run_id not in normalized:
            normalized.append(run_id)
    return normalized


def _benchmark_markdown(benchmark: MemoryEffectBenchmarkReport) -> str:
    lines = [
        f"# Benchmark de efecto de memoria {benchmark.generated_at.isoformat()}",
        "",
        benchmark.executive_summary,
        "",
        "## Resumen",
        "",
        f"- Runs analizadas: `{benchmark.run_count}`",
        f"- Baseline: `{benchmark.baseline_run_id or 'n/a'}`",
        f"- Runs con retrieval: `{benchmark.retrieval_run_count}`",
        f"- Runs con memoria usada: `{benchmark.memory_used_run_count}`",
        f"- Runs con uso invalido: `{benchmark.invalid_usage_run_count}`",
        f"- Runs con advertencias del quality gate: `{benchmark.quality_gate_warning_run_count}`",
        f"- Uso por agente: `{benchmark.agent_usage_counts}`",
        f"- Variantes: `{benchmark.variant_counts}`",
        "",
        "## Runs",
        "",
        "| Run | Variante | Modo memoria | Modelo | Retrieval | Citados | Agentes que usan | Cambios vs baseline |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in benchmark.runs:
        lines.append(
            "| "
            f"`{run.run_id}` | `{run.controlled_variant}` | `{run.memory_mode}` | "
            f"`{run.model_name or 'n/a'}` | "
            f"`{run.retrieved_memory_record_count}` | "
            f"`{run.cited_memory_record_count}` | "
            f"{_format_ids(run.memory_used_by_agents)} | "
            f"{_format_ids(run.effect_signals.changed_config_sections)} |"
        )
    lines.extend(["", "## Agentes", ""])
    for run in benchmark.runs:
        lines.append(f"### {run.run_id}")
        lines.append("")
        lines.append(
            "| Agente | Resultado | Recuperados | Citados | Ignorados | Gate pass/caution/exclude | Backend | Embedding |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for agent in run.agents:
            lines.append(
                "| "
                f"{agent.agent_name} | `{agent.outcome}` | "
                f"`{agent.retrieved_count}` | `{agent.cited_count}` | "
                f"`{agent.ignored_count}` | "
                f"`{agent.quality_pass_count}/{agent.quality_caution_count}/"
                f"{agent.quality_exclude_candidate_count}` | "
                f"`{agent.retrieval_backend or 'n/a'}` | "
                f"`{agent.embedding_model or 'n/a'}` |"
            )
        lines.append("")
        for agent in run.agents:
            if agent.outcome in {"used_aligned", "used_with_policy_warning", "usage_invalid"}:
                lines.append(f"- {agent.summary}")
                if agent.cited_memory_record_ids:
                    lines.append(f"  Recuerdos citados: {_format_ids(agent.cited_memory_record_ids)}")
                if agent.missing_risk_mitigations:
                    lines.append(
                        "  Mitigacion ausente: "
                        + _format_ids(agent.missing_risk_mitigations)
                    )
                if agent.quality_caution_ids:
                    lines.append(
                        "  Quality gate cautela: "
                        + _format_ids(agent.quality_caution_ids)
                    )
                if agent.quality_exclude_candidate_ids:
                    lines.append(
                        "  Quality gate exclusion candidata: "
                        + _format_ids(agent.quality_exclude_candidate_ids)
                    )
        deltas = [
            item for item in run.effect_signals.metric_deltas if item.delta is not None
        ]
        if deltas:
            lines.extend(["", "Metricas frente al baseline:"])
            for delta in deltas:
                lines.append(
                    f"- `{delta.metric}`: {_fmt(delta.baseline_value)} -> "
                    f"{_fmt(delta.run_value)} (`{delta.direction}`, "
                    f"delta {_fmt(delta.delta)})"
                )
        lines.append("")
    lines.extend(["## Limitaciones", ""])
    lines.extend(f"- {item}" for item in benchmark.limitations)
    return "\n".join(lines).rstrip() + "\n"


def _format_ids(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) or "n/a"


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _safe_report_dir_name(report_id: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in report_id)[
        :160
    ]


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
