"""Prerregistra o ejecuta la campaña NASA de evidencia agentiva (~56 h fuente).

La ejecución usa el replay P3, el bridge y las runs hijas existentes. No
activa memoria ni aplica políticas. Sin ``--execute`` no crea FastAPI, no abre
una sesión y no consulta Ollama.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
from functools import wraps
import json
from pathlib import Path
from typing import Any

import httpx

from codigo.app.api import create_app
from codigo.app.services.agent_reliability import (
    AgentReliabilityAttempt,
    ObservedOllamaJSONClient,
)
from codigo.app.services.llm import DEFAULT_OLLAMA_HOST
from codigo.app.services.monitoring_evidence_campaign import (
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID,
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    default_monitoring_evidence_campaign_plan,
    finalize_monitoring_evidence_campaign,
    load_published_monitoring_evidence_campaign,
    preregister_monitoring_evidence_campaign_plan,
    publish_monitoring_evidence_campaign,
    start_monitoring_evidence_campaign_state,
    update_monitoring_evidence_campaign_state,
    validate_monitoring_evidence_campaign_sources,
    write_monitoring_evidence_campaign_artifacts,
)
from codigo.app.services.monitoring_replay import (
    DEFAULT_MONITORING_SESSIONS_DIR,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.scripts.run_monitoring_review_reliability import (
    _observe_cycle,
    _progress_recorder,
    _verify_ollama_model_digest,
)
from codigo.scripts.run_nasa_monitoring_trigger_review_smoke import (
    run_full_session_review_cycle,
)


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(_parse_args(argv)))


async def _main(args: argparse.Namespace) -> int:
    plan = default_monitoring_evidence_campaign_plan(
        campaign_id=args.campaign_id,
        speed_multiplier=args.speed_multiplier,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
    )
    registration = preregister_monitoring_evidence_campaign_plan(
        plan,
        output_root=args.output_root,
    )
    state = start_monitoring_evidence_campaign_state(plan)
    publication = publish_monitoring_evidence_campaign(
        plan,
        state,
        preregistration=registration,
        output_root=args.output_root,
    )
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "plan_only",
                    "will_execute_ollama": False,
                    "campaign_id": plan.campaign_id,
                    "session_id": plan.session_id,
                    "plan_sha256": plan.plan_sha256,
                    "publication_sha256": publication.publication_sha256,
                    "pre_roll_ticks": plan.pre_roll_tick_count,
                    "agentic_window_ticks": plan.agentic_window_tick_count,
                    "agentic_window_source_seconds": (
                        plan.agentic_window_source_duration_seconds
                    ),
                    "expected_child_runs": plan.expected_child_run_count,
                    "expected_role_decisions": plan.expected_decision_count,
                    "speed_multiplier": plan.speed_multiplier,
                    "step_interval_seconds": plan.step_interval_seconds,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 0

    return await _execute_campaign(args, plan, registration, state)


def _exclusive_campaign_execution(function):
    @wraps(function)
    async def wrapped(args, plan, registration, state):
        with _campaign_execution_lock(args.output_root, plan.campaign_id):
            try:
                return await function(args, plan, registration, state)
            except Exception as exc:
                published = load_published_monitoring_evidence_campaign(
                    output_root=args.output_root,
                    campaign_id=plan.campaign_id,
                )
                if published.state.status == "planned":
                    failed_state = update_monitoring_evidence_campaign_state(
                        plan,
                        published.state,
                        {
                            "kind": "campaign_failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    publish_monitoring_evidence_campaign(
                        plan,
                        failed_state,
                        preregistration=registration,
                        output_root=args.output_root,
                    )
                raise

    return wrapped


@contextmanager
def _campaign_execution_lock(output_root: Path | str, campaign_id: str):
    lock_path = Path(output_root) / ".execution.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"campaign execution is already active: {campaign_id}"
            ) from exc
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@_exclusive_campaign_execution
async def _execute_campaign(args, plan, registration, state) -> int:

    published = load_published_monitoring_evidence_campaign(
        output_root=args.output_root,
        campaign_id=plan.campaign_id,
    )
    if published.result is not None or published.state.status != "planned":
        raise ValueError(
            "campaign_id already started or finished; use a new campaign_id "
            "for a complete auditable execution"
        )

    session_path = Path(args.sessions_dir) / plan.session_id
    if session_path.exists() or session_path.is_symlink():
        raise ValueError(
            "campaign session already exists; use a new campaign_id so every "
            "tick and child run starts after preregistration"
        )

    validate_monitoring_evidence_campaign_sources(plan)
    config = plan.llm_config
    await _verify_ollama_model_digest(
        host=args.ollama_host,
        model=config.model,
        expected_digest=plan.model_digest_sha256,
    )
    physical_attempts: list[AgentReliabilityAttempt] = []
    physical_by_child: dict[str, tuple[AgentReliabilityAttempt, ...]] = {}
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
    physical_progress = _progress_recorder(
        1,
        physical_attempts=physical_attempts,
        physical_by_child=physical_by_child,
    )

    async def progress(event: dict[str, object]) -> None:
        nonlocal state
        physical_progress(event)
        state = update_monitoring_evidence_campaign_state(
            plan,
            state,
            {**event, "physical_attempt_count": len(physical_attempts)},
        )
        publish_monitoring_evidence_campaign(
            plan,
            state,
            preregistration=registration,
            output_root=args.output_root,
        )

    state = update_monitoring_evidence_campaign_state(
        plan,
        state,
        {"kind": "campaign_started", "revision": 0},
    )
    publish_monitoring_evidence_campaign(
        plan,
        state,
        preregistration=registration,
        output_root=args.output_root,
    )
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://monitoring-evidence-campaign",
                timeout=30.0,
            ) as api_client:
                cycle = await run_full_session_review_cycle(
                    session_id=plan.session_id,
                    timeout_seconds=args.child_timeout_seconds,
                    use_llm=True,
                    client=api_client,
                    progress_callback=progress,
                    poll_interval_seconds=args.poll_interval_seconds,
                    step_interval_seconds=plan.step_interval_seconds,
                    heartbeat_interval_seconds=plan.heartbeat_interval_seconds,
                )
                replay_session = app.state.monitoring_replay_store.get_session(
                    plan.session_id
                )
                session = app.state.monitoring_review_store.decorate_session(
                    replay_session
                )
                cycle = {
                    **cycle,
                    "total_trigger_event_count": len(replay_session.triggers),
                    "suppressed_trigger_count": sum(
                        item.lifecycle_status == "suppressed"
                        for item in replay_session.triggers
                    ),
                    "variable_run_slots_reserved": (
                        session.state.activation_checkpoint.variable_run_slots_reserved
                        if session.state.activation_checkpoint is not None
                        else 0
                    ),
                }
                observations = _observe_cycle(
                    plan=_reliability_profile(plan),
                    repetition=1,
                    cycle=cycle,
                    session=session,
                    runs_dir=Path(args.runs_dir),
                    physical_by_child=physical_by_child,
                )
        result = finalize_monitoring_evidence_campaign(
            plan,
            state,
            preregistration=registration,
            cycle=cycle,
            observations=observations,
            physical_attempts=physical_attempts,
        )
        artifacts = write_monitoring_evidence_campaign_artifacts(
            result,
            registration,
            output_root=args.output_root,
        )
        publication = publish_monitoring_evidence_campaign(
            plan,
            result.final_state,
            preregistration=registration,
            result=result,
            output_root=args.output_root,
        )
    except Exception as exc:
        state = update_monitoring_evidence_campaign_state(
            plan,
            state,
            {"kind": "campaign_failed", "error": f"{type(exc).__name__}: {exc}"},
        )
        publish_monitoring_evidence_campaign(
            plan,
            state,
            preregistration=registration,
            output_root=args.output_root,
        )
        raise

    print(
        json.dumps(
            {
                "mode": "execute",
                "campaign_id": plan.campaign_id,
                "session_id": plan.session_id,
                "operational_verdict": result.operational_verdict,
                "agentic_verdict": result.agentic_verdict,
                "evidence_verdict": result.evidence_verdict,
                "blockers": result.blockers,
                "artifacts": artifacts.model_dump(mode="json"),
                "publication_sha256": publication.publication_sha256,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
    return 0 if result.evidence_verdict == "passed" else 2


def _reliability_profile(plan):
    """Reutiliza el observador de fiabilidad sin convertir una sesión en 3 réplicas."""

    from codigo.app.services.monitoring_review_reliability import (
        default_monitoring_review_reliability_plan,
    )

    return default_monitoring_review_reliability_plan(plan_id=plan.campaign_id)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ejecuta una campaña P3 acelerada con 55h50 de ventana agentiva NASA."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--campaign-id", default=DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID)
    parser.add_argument("--speed-multiplier", type=float, default=60.0)
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=5.0)
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--child-timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.25)
    parser.add_argument(
        "--output-root",
        default=DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR.as_posix(),
    )
    parser.add_argument("--runs-dir", default=DEFAULT_RUNS_DIR.as_posix())
    parser.add_argument(
        "--sessions-dir", default=DEFAULT_MONITORING_SESSIONS_DIR.as_posix()
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
