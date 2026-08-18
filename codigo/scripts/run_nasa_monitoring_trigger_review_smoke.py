"""Smoke reproducible del puente NASA P3 -> siete agentes -> run persistida.

No usa el grafo batch, no lee rutas aportadas por el usuario y no activa RAG.
Avanza el replay oficial hasta el primer trigger primario y llama al mismo
endpoint ASGI que consume la web.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import Callable
import inspect
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from codigo.app.api import create_app
from codigo.app.services.monitoring_replay import DEFAULT_SCENARIO_ID


TERMINAL_CHILD_LIFECYCLES = {"resolved", "failed", "interrupted"}


async def run_full_session_review_cycle(
    *,
    session_id: str,
    timeout_seconds: float,
    use_llm: bool,
    app: Any | None = None,
    client: Any | None = None,
    progress_callback: Callable[[dict[str, object]], object] | None = None,
    poll_interval_seconds: float = 0.25,
) -> dict[str, object]:
    """Recorre una sesion P3 completa y revisa una vez cada trigger emitido.

    Las revisiones se despachan estrictamente en orden causal y el replay no
    avanza hasta observar el lifecycle terminal de la hija anterior. Incluye
    ``session_close`` y nunca reintenta una hija fallida o interrumpida.

    Un ``client`` inyectado conserva su lifecycle externo. Si la funcion crea
    el cliente (con una app nueva o inyectada), entra tambien en el lifespan de
    FastAPI para reconciliar intentos huerfanos antes de reanudar.
    """

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if poll_interval_seconds < 0:
        raise ValueError("poll_interval_seconds cannot be negative")
    if client is not None and app is not None:
        raise ValueError("inject either app or client, not both")

    if client is not None:
        return await _run_full_session_review_cycle_with_client(
            client=client,
            session_id=session_id,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
            poll_interval_seconds=poll_interval_seconds,
        )

    owned_app = app or create_app(monitoring_review_use_llm=use_llm)
    async with owned_app.router.lifespan_context(owned_app):
        transport = httpx.ASGITransport(app=owned_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://monitoring-full-cycle",
            timeout=30.0,
        ) as owned_client:
            return await _run_full_session_review_cycle_with_client(
                client=owned_client,
                session_id=session_id,
                timeout_seconds=timeout_seconds,
                progress_callback=progress_callback,
                poll_interval_seconds=poll_interval_seconds,
            )


async def _run_full_session_review_cycle_with_client(
    *,
    client: Any,
    session_id: str,
    timeout_seconds: float,
    progress_callback: Callable[[dict[str, object]], object] | None,
    poll_interval_seconds: float,
) -> dict[str, object]:
    response = await client.get(f"/monitoring/sessions/{session_id}")
    if response.status_code == 404:
        response = await client.post(
            "/monitoring/sessions",
            json={
                "scenario_id": DEFAULT_SCENARIO_ID,
                "session_id": session_id,
                "activation_policy_kind": "P3",
                "experiment_mode": "frozen_benchmark",
            },
        )
    response.raise_for_status()
    session = response.json()
    if session.get("config", {}).get("activation_policy_kind") not in {None, "P3"}:
        raise RuntimeError("full monitoring review cycle requires a P3 session")

    reviews_by_trigger: dict[str, dict[str, object]] = {}
    steps_applied = 0

    while True:
        await _collect_existing_terminal_reviews(
            client=client,
            session=session,
            reviews_by_trigger=reviews_by_trigger,
        )
        active = _active_child_attempt(session)
        if active is not None:
            trigger = _emitted_trigger(session, str(active["trigger_id"]))
            attempt, job = await _wait_for_child_terminal(
                client=client,
                session_id=session_id,
                child_run_id=str(active["child_run_id"]),
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            _update_session_children(session, attempt["child_runs_response"])
            record = _review_record(trigger, attempt["attempt"], job, resumed=True)
            reviews_by_trigger[str(trigger["trigger_id"])] = record
            await _emit_progress(
                progress_callback,
                _review_progress_event("review_terminal", session_id, record),
            )
            continue

        trigger = _first_unattempted_emitted_trigger(session)
        if trigger is not None:
            dispatched = await client.post(
                (
                    f"/monitoring/sessions/{session_id}/triggers/"
                    f"{trigger['trigger_id']}/dispatch"
                ),
                json={
                    "command_id": _dispatch_command_id(trigger),
                    "expected_child_revision": int(session.get("child_revision", 0)),
                },
            )
            dispatched.raise_for_status()
            dispatch_payload = dispatched.json()
            session = dispatch_payload["session"]
            child_run_id = str(dispatch_payload["receipt"]["child_run_id"])
            dispatch_event = {
                "kind": "review_dispatching",
                "session_id": session_id,
                "trigger_id": str(trigger["trigger_id"]),
                "trigger_type": str(trigger["trigger_type"]),
                "cutoff_cursor": trigger.get("cutoff_cursor"),
                "child_run_id": child_run_id,
            }
            await _emit_progress(progress_callback, dispatch_event)

            attempt, job = await _wait_for_child_terminal(
                client=client,
                session_id=session_id,
                child_run_id=child_run_id,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            _update_session_children(session, attempt["child_runs_response"])
            record = _review_record(trigger, attempt["attempt"], job, resumed=False)
            reviews_by_trigger[str(trigger["trigger_id"])] = record
            await _emit_progress(
                progress_callback,
                _review_progress_event("review_terminal", session_id, record),
            )
            continue

        state = session["state"]
        if (
            state.get("status") == "completed"
            or int(state["revision"]) >= int(session["total_monitoring_ticks"])
        ):
            break

        revision = int(state["revision"])
        stepped = await client.post(
            f"/monitoring/sessions/{session_id}/step",
            json={
                "command_id": f"full-cycle-step-{revision:06d}",
                "expected_revision": revision,
            },
        )
        stepped.raise_for_status()
        step_payload = stepped.json()
        session["state"] = step_payload["state"]
        _merge_triggers(session, step_payload.get("triggers", []))
        steps_applied += 1
        if steps_applied % 100 == 0:
            await _emit_progress(
                progress_callback,
                {
                    "kind": "replay_progress",
                    "session_id": session_id,
                    "revision": int(session["state"]["revision"]),
                },
            )

    reviews = sorted(
        reviews_by_trigger.values(),
        key=lambda item: int(item["trigger_sequence"]),
    )
    lifecycle_counts = Counter(str(item["child_lifecycle"]) for item in reviews)
    return {
        "session_id": session_id,
        "session_status": str(session["state"]["status"]),
        "final_revision": int(session["state"]["revision"]),
        "steps_applied": steps_applied,
        "review_count": len(reviews),
        "reviews": reviews,
        "terminal_counts": dict(sorted(lifecycle_counts.items())),
        "memory_mode": "off",
        "policy_application_status": "not_applied",
    }


async def _wait_for_child_terminal(
    *,
    client: Any,
    session_id: str,
    child_run_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = await client.get(
            f"/monitoring/sessions/{session_id}/child-runs"
        )
        response.raise_for_status()
        payload = response.json()
        attempt = next(
            (
                item
                for item in payload.get("child_runs", [])
                if item.get("child_run_id") == child_run_id
            ),
            None,
        )
        if attempt is not None and attempt.get("lifecycle_status") in (
            TERMINAL_CHILD_LIFECYCLES
        ):
            job_response = await client.get(f"/run-jobs/{child_run_id}")
            job = job_response.json() if job_response.status_code == 200 else None
            return {
                "attempt": attempt,
                "child_runs_response": payload,
            }, job
        await asyncio.sleep(poll_interval_seconds)
    raise TimeoutError(f"child run did not finish: {child_run_id}")


async def _collect_existing_terminal_reviews(
    *,
    client: Any,
    session: dict[str, Any],
    reviews_by_trigger: dict[str, dict[str, object]],
) -> None:
    triggers = {
        str(item["trigger_id"]): item
        for item in session.get("triggers", [])
        if item.get("lifecycle_status") == "emitted"
    }
    for attempt in session.get("child_runs", []):
        trigger_id = str(attempt["trigger_id"])
        if (
            trigger_id in reviews_by_trigger
            or attempt.get("lifecycle_status") not in TERMINAL_CHILD_LIFECYCLES
            or trigger_id not in triggers
        ):
            continue
        job_response = await client.get(f"/run-jobs/{attempt['child_run_id']}")
        job = job_response.json() if job_response.status_code == 200 else None
        reviews_by_trigger[trigger_id] = _review_record(
            triggers[trigger_id],
            attempt,
            job,
            resumed=True,
        )


def _review_record(
    trigger: dict[str, Any],
    attempt: dict[str, Any],
    job: dict[str, Any] | None,
    *,
    resumed: bool,
) -> dict[str, object]:
    events = job.get("events", []) if job is not None else []
    decision_events = [
        event
        for event in events
        if event.get("kind") in {"supervisor_decision", "agent_decision"}
    ]
    origins = [
        event.get("payload", {})
        .get("decision", {})
        .get("generation_trace", {})
        .get("origin")
        for event in decision_events
    ]
    child_run_id = str(attempt["child_run_id"])
    return {
        "trigger_id": str(trigger["trigger_id"]),
        "trigger_event_id": str(trigger["event_id"]),
        "trigger_sequence": int(trigger["sequence"]),
        "trigger_type": str(trigger["trigger_type"]),
        "cutoff_cursor": trigger.get("cutoff_cursor"),
        "child_run_id": child_run_id,
        "child_lifecycle": str(attempt["lifecycle_status"]),
        "job_status": None if job is None else job.get("status"),
        "decision_count": len(decision_events),
        "decision_origins": origins,
        "fallback_count": sum(
            origin == "guardrail_fallback" for origin in origins
        ),
        "error": attempt.get("error"),
        "resumed": resumed,
        "run_dir": (Path("codigo/reports/runs") / child_run_id).as_posix(),
    }


def _review_progress_event(
    kind: str,
    session_id: str,
    record: dict[str, object],
) -> dict[str, object]:
    return {
        "kind": kind,
        "session_id": session_id,
        "trigger_id": record["trigger_id"],
        "trigger_type": record["trigger_type"],
        "cutoff_cursor": record["cutoff_cursor"],
        "child_run_id": record["child_run_id"],
        "child_lifecycle": record["child_lifecycle"],
        "job_status": record["job_status"],
    }


async def _emit_progress(
    callback: Callable[[dict[str, object]], object] | None,
    event: dict[str, object],
) -> None:
    if callback is None:
        return
    outcome = callback(event)
    if inspect.isawaitable(outcome):
        await outcome


def _merge_triggers(
    session: dict[str, Any],
    new_triggers: list[dict[str, Any]],
) -> None:
    current = list(session.get("triggers", []))
    event_ids = {item.get("event_id") for item in current}
    current.extend(
        item for item in new_triggers if item.get("event_id") not in event_ids
    )
    session["triggers"] = current


def _first_unattempted_emitted_trigger(
    session: dict[str, Any],
) -> dict[str, Any] | None:
    attempted = {
        str(item["trigger_id"])
        for item in session.get("child_runs", [])
        if isinstance(item, dict)
    }
    candidates = [
        item
        for item in session.get("triggers", [])
        if item.get("lifecycle_status") == "emitted"
        and str(item["trigger_id"]) not in attempted
    ]
    return min(candidates, key=lambda item: int(item["sequence"]), default=None)


def _active_child_attempt(session: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in session.get("child_runs", [])
            if item.get("lifecycle_status") in {"dispatched", "running"}
        ),
        None,
    )


def _emitted_trigger(
    session: dict[str, Any],
    trigger_id: str,
) -> dict[str, Any]:
    trigger = next(
        (
            item
            for item in session.get("triggers", [])
            if item.get("trigger_id") == trigger_id
            and item.get("lifecycle_status") == "emitted"
        ),
        None,
    )
    if trigger is None:
        raise RuntimeError(f"emitted trigger not found for child: {trigger_id}")
    return trigger


def _update_session_children(
    session: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    session["child_revision"] = payload["child_revision"]
    session["child_runs"] = payload.get("child_runs", [])
    session["active_child_run_id"] = next(
        (
            item["child_run_id"]
            for item in session["child_runs"]
            if item.get("lifecycle_status") in {"dispatched", "running"}
        ),
        None,
    )


def _dispatch_command_id(trigger: dict[str, Any]) -> str:
    return f"full-cycle-dispatch-{int(trigger['sequence']):06d}"


async def run_smoke(
    *,
    session_id: str,
    max_steps: int,
    timeout_seconds: float,
    use_llm: bool,
) -> dict[str, object]:
    app = create_app(monitoring_review_use_llm=use_llm)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://monitoring-smoke",
        timeout=30.0,
    ) as client:
        response = await client.get(f"/monitoring/sessions/{session_id}")
        if response.status_code == 404:
            response = await client.post(
                "/monitoring/sessions",
                json={
                    "scenario_id": DEFAULT_SCENARIO_ID,
                    "session_id": session_id,
                    "activation_policy_kind": "P3",
                    "experiment_mode": "frozen_benchmark",
                },
            )
        response.raise_for_status()
        session = response.json()

        trigger = _first_dispatchable_trigger(session)
        while trigger is None and session["state"]["revision"] < max_steps:
            revision = int(session["state"]["revision"])
            stepped = await client.post(
                f"/monitoring/sessions/{session_id}/step",
                json={
                    "command_id": f"qwen-smoke-step-{revision:04d}",
                    "expected_revision": revision,
                },
            )
            stepped.raise_for_status()
            if (revision + 1) % 100 == 0:
                print(f"replay progress: {revision + 1}", flush=True)
            response = await client.get(f"/monitoring/sessions/{session_id}")
            response.raise_for_status()
            session = response.json()
            trigger = _first_dispatchable_trigger(session)

        if trigger is None:
            raise RuntimeError(
                f"no dispatchable trigger before revision {session['state']['revision']}"
            )

        command_id = f"qwen-smoke-dispatch-{session_id}"
        dispatched = await client.post(
            (
                f"/monitoring/sessions/{session_id}/triggers/"
                f"{trigger['trigger_id']}/dispatch"
            ),
            json={
                "command_id": command_id,
                "expected_child_revision": int(session["child_revision"]),
            },
        )
        dispatched.raise_for_status()
        dispatch_payload = dispatched.json()
        child_run_id = str(dispatch_payload["receipt"]["child_run_id"])

        deadline = time.monotonic() + timeout_seconds
        job_payload: dict[str, object] | None = None
        while time.monotonic() < deadline:
            job = await client.get(f"/run-jobs/{child_run_id}")
            if job.status_code == 200:
                job_payload = job.json()
                if job_payload["status"] in {"completed", "failed"}:
                    break
            await asyncio.sleep(0.25)
        if job_payload is None or job_payload.get("status") not in {
            "completed",
            "failed",
        }:
            raise TimeoutError(f"child run did not finish: {child_run_id}")

        final_session_response = await client.get(
            f"/monitoring/sessions/{session_id}"
        )
        final_session_response.raise_for_status()
        final_session = final_session_response.json()
        events_response = await client.get(f"/runs/{child_run_id}/events")
        if job_payload["status"] == "completed":
            events_response.raise_for_status()
            events = events_response.json()
        else:
            events = job_payload.get("events", [])

        decision_events = [
            event
            for event in events
            if event.get("kind") in {"supervisor_decision", "agent_decision"}
        ]
        origins = [
            event.get("payload", {})
            .get("decision", {})
            .get("generation_trace", {})
            .get("origin")
            for event in decision_events
        ]
        fallbacks = [origin for origin in origins if origin == "guardrail_fallback"]
        attempts = final_session.get("child_runs", [])
        attempt = next(
            item for item in attempts if item["child_run_id"] == child_run_id
        )
        return {
            "session_id": session_id,
            "trigger_id": trigger["trigger_id"],
            "trigger_type": trigger["trigger_type"],
            "cutoff_cursor": trigger["cutoff_cursor"],
            "child_run_id": child_run_id,
            "job_status": job_payload["status"],
            "child_lifecycle": attempt["lifecycle_status"],
            "decision_count": len(decision_events),
            "decision_origins": origins,
            "fallback_count": len(fallbacks),
            "memory_mode": "off",
            "policy_application_status": "not_applied",
            "run_dir": Path("codigo/reports/runs") / child_run_id,
        }


def _first_dispatchable_trigger(session: dict[str, object]):
    attempts = {
        item["trigger_id"]
        for item in session.get("child_runs", [])
        if isinstance(item, dict)
    }
    for event in session.get("triggers", []):
        if (
            event["lifecycle_status"] == "emitted"
            and event["trigger_id"] not in attempts
            and event["trigger_type"] != "session_close"
        ):
            return event
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session-id",
        default=f"nasa-p3-qwen35-smoke-{uuid4().hex[:8]}",
    )
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--protocol-restricted",
        action="store_true",
        help="Usa decisiones deterministas solo para probar transporte/persistencia.",
    )
    args = parser.parse_args()
    result = asyncio.run(
        run_smoke(
            session_id=args.session_id,
            max_steps=args.max_steps,
            timeout_seconds=args.timeout_seconds,
            use_llm=not args.protocol_restricted,
        )
    )
    printable = {
        **result,
        "run_dir": Path(result["run_dir"]).as_posix(),
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
