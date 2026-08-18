"""Prerregistra o ejecuta el gate NASA P3 de revisiones multiagente.

Sin ``--execute`` el comando solo materializa y muestra el plan. La ejecucion
real recorre tres sesiones independientes, despacha los cuatro triggers
primarios de cada una y conserva memoria y aplicacion de politica desactivadas.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import httpx

from codigo.app.api import create_app
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    CausalInputView,
    MonitoringReviewRequest,
    MonitoringReviewResult,
)
from codigo.app.services.agent_reliability import (
    AgentReliabilityAttempt,
    ObservedOllamaJSONClient,
)
from codigo.app.services.monitoring_replay import DEFAULT_MONITORING_SESSIONS_DIR
from codigo.app.services.monitoring_review_reliability import (
    DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
    MonitoringReviewReliabilityObservation,
    build_monitoring_review_reliability_result,
    default_monitoring_review_reliability_plan,
    monitoring_review_error_observations,
    observe_monitoring_review_result,
    preregister_monitoring_review_reliability_plan,
    publish_monitoring_review_reliability,
    write_monitoring_review_reliability_artifacts,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.llm import DEFAULT_OLLAMA_HOST
from codigo.scripts.run_nasa_monitoring_trigger_review_smoke import (
    run_full_session_review_cycle,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_main(args))


async def _main(args: argparse.Namespace) -> int:
    plan = default_monitoring_review_reliability_plan(plan_id=args.plan_id)
    preregistration = preregister_monitoring_review_reliability_plan(
        plan,
        output_root=args.output_root,
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "plan_only",
                    "will_execute_ollama": False,
                    "plan": plan.model_dump(mode="json"),
                    "plan_sha256": preregistration.plan_sha256,
                    "expected_child_runs": plan.expected_child_run_count,
                    "expected_role_decisions": plan.expected_observation_count,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0

    session_ids = tuple(
        f"{plan.plan_id}-rep-{repetition:02d}"
        for repetition in range(1, plan.repetitions + 1)
    )
    if any(len(session_id) > 160 for session_id in session_ids):
        raise ValueError(
            "plan_id is too long for derived monitoring session ids; "
            "execute mode accepts at most 153 characters"
        )
    config = plan.llm_config
    await _verify_ollama_model_digest(
        host=args.ollama_host,
        model=config.model,
        expected_digest=plan.model_digest_sha256,
    )
    physical_attempts: list[AgentReliabilityAttempt] = []
    llm_client = ObservedOllamaJSONClient(
        physical_attempts=physical_attempts,
        model=config.model,
        host=args.ollama_host,
        timeout_seconds=config.timeout_seconds,
        think=config.think,
        max_json_repair_attempts=config.max_json_repair_attempts,
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
    )
    app = create_app(
        runs_dir=Path(args.runs_dir),
        monitoring_sessions_dir=Path(args.sessions_dir),
        monitoring_review_llm_client=llm_client,
        monitoring_review_use_llm=True,
    )
    observations: list[MonitoringReviewReliabilityObservation] = []
    started_at = datetime.now(UTC)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://monitoring-review-reliability",
            timeout=30.0,
        ) as api_client:
            for repetition, session_id in enumerate(session_ids, start=1):
                physical_by_child: dict[str, tuple[AgentReliabilityAttempt, ...]] = {}
                progress = _progress_recorder(
                    repetition,
                    physical_attempts=physical_attempts,
                    physical_by_child=physical_by_child,
                )
                cycle = await run_full_session_review_cycle(
                    session_id=session_id,
                    timeout_seconds=args.child_timeout_seconds,
                    use_llm=True,
                    client=api_client,
                    progress_callback=progress,
                    poll_interval_seconds=args.poll_interval_seconds,
                )
                session = app.state.monitoring_review_store.decorate_session(
                    app.state.monitoring_replay_store.get_session(session_id)
                )
                observations.extend(
                    _observe_cycle(
                        plan=plan,
                        repetition=repetition,
                        cycle=cycle,
                        session=session,
                        runs_dir=Path(args.runs_dir),
                        physical_by_child=physical_by_child,
                    )
                )

    completed_at = datetime.now(UTC)
    result = build_monitoring_review_reliability_result(
        plan,
        observations,
        preregistration=preregistration,
        llm_config=config,
        started_at=started_at,
        completed_at=completed_at,
    )
    artifacts = write_monitoring_review_reliability_artifacts(
        result,
        output_root=args.output_root,
    )
    publication = publish_monitoring_review_reliability(
        result,
        artifacts,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "mode": "execute",
                "gate": result.gate.model_dump(mode="json"),
                "summary": result.summary.model_dump(mode="json"),
                "artifacts": artifacts.model_dump(mode="json"),
                "publication_sha256": publication.publication_sha256,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0 if result.gate.verdict == "passed" else 2


async def _verify_ollama_model_digest(
    *,
    host: str,
    model: str,
    expected_digest: str,
    client: Any | None = None,
) -> None:
    """Bloquea el gate si la etiqueta exacta no apunta al modelo sellado."""

    async def verify(selected_client: Any) -> None:
        try:
            response = await selected_client.get("/api/tags")
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"cannot verify sealed Ollama model {model!r} before execution: {exc}"
            ) from exc
        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError("Ollama /api/tags returned invalid JSON") from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/tags response has no models list")
        exact = [
            item
            for item in models
            if isinstance(item, dict) and item.get("name") == model
        ]
        if len(exact) != 1:
            if not exact:
                raise RuntimeError(
                    f"sealed Ollama model is not installed under exact name {model!r}"
                )
            raise RuntimeError(
                f"Ollama /api/tags returned duplicate exact entries for {model!r}"
            )
        observed_digest = exact[0].get("digest")
        if observed_digest != expected_digest:
            raise RuntimeError(
                f"Ollama model digest mismatch for {model!r}: "
                f"expected {expected_digest}, observed {observed_digest!r}"
            )

    if client is not None:
        await verify(client)
        return
    async with httpx.AsyncClient(
        base_url=host.rstrip("/"),
        timeout=10.0,
    ) as owned_client:
        await verify(owned_client)


def _observe_cycle(
    *,
    plan,
    repetition: int,
    cycle: dict[str, object],
    session,
    runs_dir: Path,
    physical_by_child: dict[str, tuple[AgentReliabilityAttempt, ...]],
) -> list[MonitoringReviewReliabilityObservation]:
    emitted = {
        item.trigger_id: item
        for item in session.triggers
        if item.lifecycle_status == "emitted"
    }
    attempts = {item.child_run_id: item for item in session.child_runs}
    output: list[MonitoringReviewReliabilityObservation] = []
    for review in cycle.get("reviews", []):
        if not isinstance(review, dict):
            raise RuntimeError("full-cycle review payload is malformed")
        trigger_id = str(review["trigger_id"])
        trigger = emitted.get(trigger_id)
        if trigger is None:
            raise RuntimeError(f"emitted trigger missing from session: {trigger_id}")
        expected = next(
            (
                item
                for item in plan.expected_contexts
                if item.trigger_type == trigger.trigger_type
                and item.reason_code == trigger.reason_code
                and item.condition_start_cursor == trigger.condition_start_cursor
                and item.cutoff_cursor == trigger.cutoff_cursor
            ),
            None,
        )
        if expected is None:
            raise RuntimeError(f"trigger is outside preregistered pack: {trigger_id}")
        child_run_id = str(review["child_run_id"])
        attempt = attempts.get(child_run_id)
        if attempt is None:
            raise RuntimeError(f"child attempt missing from session: {child_run_id}")
        request = MonitoringReviewRequest.model_validate(
            _read_json(Path(attempt.request_ref))
        )
        view = CausalInputView.model_validate(
            _read_json(Path(attempt.causal_view_ref))
        )
        catalog_path = Path(attempt.causal_view_ref).with_name(
            "evidence_catalog.json"
        )
        evidence_catalog = (
            CausalEvidenceCatalog.model_validate(_read_json(catalog_path))
            if catalog_path.is_file()
            else None
        )
        if attempt.result_ref is None:
            output.extend(
                monitoring_review_error_observations(
                    plan,
                    repetition=repetition,
                    context_id=expected.context_id,
                    session_id=session.state.session_id,
                    trigger_id=trigger.trigger_id,
                    trigger_event_id=trigger.event_id,
                    request_sha256=request.request_sha256,
                    causal_view_sha256=view.view_sha256,
                    child_run_id=child_run_id,
                    trigger_type=trigger.trigger_type,
                    reason_code=trigger.reason_code,
                    condition_start_cursor=int(trigger.condition_start_cursor or 0),
                    cutoff_cursor=int(trigger.cutoff_cursor or 0),
                    child_lifecycle_status=attempt.lifecycle_status,
                    run_ref=(runs_dir / child_run_id).as_posix(),
                    error=(attempt.error or "monitoring review result is missing"),
                )
            )
            continue
        result = MonitoringReviewResult.model_validate(
            _read_json(Path(attempt.result_ref))
        )
        physical_by_role = _partition_physical_attempts(
            result,
            physical_by_child.get(child_run_id, ()),
            allow_missing=bool(review.get("resumed")),
        )
        output.extend(
            observe_monitoring_review_result(
                plan,
                repetition=repetition,
                context_id=expected.context_id,
                trigger=trigger,
                causal_view=view,
                evidence_catalog=evidence_catalog,
                request=request,
                result=result,
                child_lifecycle_status=attempt.lifecycle_status,
                run_ref=(runs_dir / child_run_id).as_posix(),
                physical_attempts_by_role=physical_by_role,
            )
        )
    return output


def _partition_physical_attempts(
    result: MonitoringReviewResult,
    attempts: tuple[AgentReliabilityAttempt, ...],
    *,
    allow_missing: bool = False,
) -> dict[str, tuple[AgentReliabilityAttempt, ...]]:
    """Asigna llamadas fisicas al orden cerrado de los siete roles."""

    if allow_missing and not attempts:
        return {}
    cursor = 0
    partition: dict[str, tuple[AgentReliabilityAttempt, ...]] = {}
    for role_result in result.role_results:
        decision = role_result.decision
        if decision is None:
            expected_count = 0
        elif decision.generation_trace.origin == "guardrail_fallback":
            expected_count = max(decision.generation_trace.attempt_index - 1, 0)
        else:
            expected_count = decision.generation_trace.attempt_index
        partition[role_result.agent_name] = attempts[cursor : cursor + expected_count]
        cursor += expected_count
    if cursor != len(attempts):
        raise RuntimeError(
            "physical Ollama attempts do not match the seven role traces: "
            f"expected {cursor}, observed {len(attempts)}"
        )
    return partition


def _progress_recorder(
    repetition: int,
    *,
    physical_attempts: list[AgentReliabilityAttempt],
    physical_by_child: dict[str, tuple[AgentReliabilityAttempt, ...]],
):
    # La hija puede empezar en el hilo local antes de que el POST de dispatch
    # vuelva al caller. El cursor se toma antes del ciclo y se avanza solo al
    # observar cada terminal, por lo que tampoco se pierde su primera llamada.
    next_start = len(physical_attempts)

    def emit(event: dict[str, object]) -> None:
        nonlocal next_start
        child_run_id = str(event.get("child_run_id") or "")
        if event.get("kind") == "review_terminal":
            physical_by_child[child_run_id] = tuple(physical_attempts[next_start:])
            next_start = len(physical_attempts)
        if event.get("kind") not in {"review_dispatching", "review_terminal"}:
            return
        print(
            json.dumps(
                {"repetition": repetition, **event},
                ensure_ascii=True,
            ),
            flush=True,
        )

    return emit


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita tres replays P3 completos con Qwen 3.5."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--plan-id",
        default="nasa-p3-monitoring-review-qwen35-v1",
    )
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--child-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.25)
    parser.add_argument(
        "--output-root",
        default=DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR.as_posix(),
    )
    parser.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR.as_posix())
    parser.add_argument(
        "--sessions-dir",
        default=DEFAULT_MONITORING_SESSIONS_DIR.as_posix(),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
