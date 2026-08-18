"""Persistencia causal del puente entre un trigger y una revision multiagente.

El ledger de ticks/triggers de :mod:`monitoring_replay` es evidencia cientifica
inmutable. Este modulo no lo reescribe: materializa una vista por whitelist y
mantiene un segundo ledger append-only para el ciclo de vida de la run hija.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import fcntl

from codigo.app.schemas.api_monitoring import MonitoringSessionView
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceArtifact,
    CausalEvidenceCatalog,
    CausalEvidenceCatalogEntry,
    CausalInputView,
    MonitoringChildRunAttempt,
    MonitoringReviewDispatchCommand,
    MonitoringReviewDispatchReceipt,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringTriggerEvent,
)
from codigo.app.services.monitoring_replay import (
    MonitoringReplayConflictError,
    MonitoringReplayNotFoundError,
)


_EVIDENCE_FIELDS = (
    "record_id",
    "dataset_id",
    "trajectory_id",
    "asset_id",
    "channel_id",
    "snapshot_id",
    "source_time",
    "segment_id",
    "analysis_status",
    "signal_rms",
    "signal_peak_abs",
    "n_samples",
    "score",
    "threshold",
    "score_ratio",
    "health_index",
    "risk_index",
    "health_state",
    "gap_detected",
    "interval_seconds",
    "scoring_version",
    "activation_version",
)


@dataclass(frozen=True)
class MonitoringReviewSessionProjection:
    """Vista derivada del ledger hijo; no forma parte del commit del replay."""

    child_revision: int
    attempts: tuple[MonitoringChildRunAttempt, ...]
    lifecycle_events: tuple[MonitoringTriggerEvent, ...]
    active_child_run_id: str | None


class MonitoringReviewStore:
    """Autoridad local para vistas causales, reservas y lifecycle de hijas."""

    def __init__(
        self,
        sessions_root: str | Path,
        *,
        runs_root: str | Path = "codigo/reports/runs",
    ) -> None:
        self.sessions_root = Path(sessions_root)
        self.runs_root = Path(runs_root)
        self._process_lock = threading.RLock()
        self._local = threading.local()

    def build_causal_view(
        self,
        session: MonitoringSessionView,
        trigger_id: str,
    ) -> CausalInputView:
        """Proyecta solo frames confirmados hasta el cutoff del trigger."""

        trigger = _dispatchable_trigger(session, trigger_id)
        if trigger.cutoff_cursor is None or trigger.cutoff_source_time is None:
            raise MonitoringReplayConflictError(
                "monitoring review v1 requires a trigger with a causal cutoff"
            )
        if trigger.origin_tick_id is None or trigger.snapshot_end_id is None:
            raise MonitoringReplayConflictError(
                "monitoring trigger is not bound to an origin tick"
            )
        eligible_ticks = tuple(
            tick for tick in session.ticks if tick.cursor <= trigger.cutoff_cursor
        )
        if not eligible_ticks:
            raise MonitoringReplayConflictError(
                "monitoring trigger has no committed causal evidence"
            )
        origin = next(
            (tick for tick in eligible_ticks if tick.tick_id == trigger.origin_tick_id),
            None,
        )
        if origin is None or origin.cursor != trigger.cutoff_cursor:
            raise MonitoringReplayConflictError(
                "monitoring trigger cutoff does not match its committed origin tick"
            )

        session_dir = self._session_dir(session.state.session_id)
        view_dir = session_dir / "causal_views" / _safe_digest(trigger.trigger_id)
        with self._session_lock(session.state.session_id):
            existing = view_dir / "view.json"
            if existing.is_file():
                loaded = self._load_view_path(session_dir, existing)
                if loaded.trigger_id != trigger_id:
                    raise MonitoringReplayConflictError(
                        "persisted causal view belongs to another trigger"
                    )
                return loaded

            view_dir.mkdir(parents=True, exist_ok=True)
            records = _causal_records(session, eligible_ticks, trigger)
            evidence_path = view_dir / "evidence.json"
            manifest_path = view_dir / "manifest_projection.json"
            manifest = {
                "schema_version": "monitoring_manifest_projection_v1",
                "session_id": session.state.session_id,
                "dataset_id": session.config.dataset_id,
                "trajectory_id": session.config.trajectory_id,
                "partition_policy_id": session.config.partition_policy_id,
                "visible_partitions": ["monitoring"],
                "cutoff_cursor": trigger.cutoff_cursor,
                "cutoff_snapshot_id": origin.snapshot_id,
                "cutoff_source_time": trigger.cutoff_source_time.isoformat(),
                "active_policy_refs": origin.active_policy_refs.model_dump(mode="json"),
                "asset_specs": [
                    item.model_dump(mode="json") for item in session.config.asset_specs
                ],
                "future_hidden": True,
            }
            _write_json_atomic(evidence_path, records)
            _write_json_atomic(manifest_path, manifest)
            evidence_sha = _file_sha256(evidence_path)
            manifest_sha = _file_sha256(manifest_path)
            evidence_id = f"evidence:{session.state.session_id}:{trigger.trigger_id}"
            payload: dict[str, Any] = {
                "view_id": f"causal-view:{session.state.session_id}:{trigger.trigger_id}",
                "session_id": session.state.session_id,
                "trigger_id": trigger.trigger_id,
                "trigger_event_id": trigger.event_id,
                "origin_tick_id": origin.tick_id,
                "cutoff_snapshot_id": origin.snapshot_id,
                "cursor": trigger.cutoff_cursor,
                "cutoff_source_time": trigger.cutoff_source_time,
                "active_policy_refs": origin.active_policy_refs,
                "manifest_projection_ref": manifest_path.resolve().as_posix(),
                "manifest_projection_sha256": manifest_sha,
                "partition_policy_id": session.config.partition_policy_id,
                "visible_partitions": ("monitoring",),
                "whitelisted_fields": _EVIDENCE_FIELDS,
                "evidence": (
                    CausalEvidenceArtifact(
                        evidence_id=evidence_id,
                        artifact_ref=evidence_path.resolve().as_posix(),
                        artifact_sha256=evidence_sha,
                        available_at_cursor=trigger.cutoff_cursor,
                        max_source_time=trigger.cutoff_source_time,
                        record_count=len(records),
                        fields=_EVIDENCE_FIELDS,
                    ),
                ),
                # Derivado de la evidencia original; construir la misma vista mas
                # tarde no cambia su identidad ni aparenta un nuevo hecho causal.
                "created_at": trigger.recorded_at,
            }
            payload["view_sha256"] = CausalInputView.canonical_sha256(payload)
            view = CausalInputView.model_validate(payload)
            _write_json_atomic(existing, view.model_dump(mode="json"))
            catalog = build_causal_evidence_catalog(view, records)
            _write_json_atomic(
                view_dir / "evidence_catalog.json",
                catalog.model_dump(mode="json"),
            )
            return view

    def load_causal_view(
        self,
        session_id: str,
        view_sha256: str,
    ) -> CausalInputView:
        session_dir = self._session_dir(session_id)
        with self._session_lock(session_id):
            for path in sorted((session_dir / "causal_views").glob("*/view.json")):
                view = self._load_view_path(session_dir, path)
                if view.view_sha256 == view_sha256:
                    return view
        raise MonitoringReplayNotFoundError(
            f"causal monitoring view not found: {view_sha256}"
        )

    def load_evidence_records(
        self,
        session_id: str,
        view_sha256: str,
    ) -> list[dict[str, Any]]:
        view = self.load_causal_view(session_id, view_sha256)
        if len(view.evidence) != 1:
            raise MonitoringReplayConflictError(
                "monitoring review v1 expects one canonical evidence artifact"
            )
        session_dir = self._session_dir(session_id)
        path = self._contained_artifact(session_dir, view.evidence[0].artifact_ref)
        if _file_sha256(path) != view.evidence[0].artifact_sha256:
            raise MonitoringReplayConflictError(
                "causal evidence SHA-256 does not match its view"
            )
        payload = _read_json(path)
        if not isinstance(payload, list) or not payload:
            raise MonitoringReplayConflictError("causal evidence must be a non-empty list")
        records = [dict(item) for item in payload]
        validate_causal_evidence_records(view, records)
        return records

    def load_evidence_catalog(
        self,
        session_id: str,
        view_sha256: str,
    ) -> CausalEvidenceCatalog:
        """Carga el catalogo sellado o lo deriva sin reescribir una vista legacy."""

        view = self.load_causal_view(session_id, view_sha256)
        records = self.load_evidence_records(session_id, view_sha256)
        expected = build_causal_evidence_catalog(view, records)
        session_dir = self._session_dir(session_id)
        path = self._catalog_path_for_view(view)
        if not path.exists():
            return expected
        safe_path = self._contained_artifact(session_dir, path.as_posix())
        persisted = CausalEvidenceCatalog.model_validate(_read_json(safe_path))
        validate_causal_evidence_catalog(view, records, persisted)
        if persisted != expected:
            raise MonitoringReplayConflictError(
                "causal evidence catalog differs from its deterministic projection"
            )
        return persisted

    def build_review_request(
        self,
        session: MonitoringSessionView,
        trigger_id: str,
        *,
        child_run_id: str,
        prompt_template_id: str,
        prompt_template_sha256: str,
        response_schema_id: str,
        response_schema_sha256: str,
        allowed_options_id: str,
        allowed_options_sha256: str,
    ) -> MonitoringReviewRequest:
        view = self.build_causal_view(session, trigger_id)
        request_dir = (
            self._session_dir(session.state.session_id)
            / "review_requests"
            / _safe_digest(child_run_id)
        )
        request_path = request_dir / "request.json"
        with self._session_lock(session.state.session_id):
            if request_path.is_file():
                request = MonitoringReviewRequest.model_validate(_read_json(request_path))
                expected_binding = (
                    child_run_id,
                    session.state.session_id,
                    trigger_id,
                    view.trigger_event_id,
                    view.origin_tick_id,
                    view.cutoff_snapshot_id,
                    view.cursor,
                    view.cutoff_source_time,
                    view.active_policy_refs,
                    view.view_sha256,
                    prompt_template_id,
                    prompt_template_sha256,
                    response_schema_id,
                    response_schema_sha256,
                    allowed_options_id,
                    allowed_options_sha256,
                )
                persisted_binding = (
                    request.child_run_id,
                    request.session_id,
                    request.trigger_id,
                    request.trigger_event_id,
                    request.origin_tick_id,
                    request.cutoff_snapshot_id,
                    request.cutoff_cursor,
                    request.cutoff_source_time,
                    request.active_policy_refs,
                    request.causal_view_sha256,
                    request.prompt_template_id,
                    request.prompt_template_sha256,
                    request.response_schema_id,
                    request.response_schema_sha256,
                    request.allowed_options_id,
                    request.allowed_options_sha256,
                )
                if persisted_binding != expected_binding:
                    raise MonitoringReplayConflictError(
                        "persisted review request contract binding changed"
                    )
                return request
            request_dir.mkdir(parents=True, exist_ok=True)
            payload: dict[str, Any] = {
                "request_id": f"monitoring-review:{child_run_id}",
                "child_run_id": child_run_id,
                "session_id": session.state.session_id,
                "trigger_id": trigger_id,
                "trigger_event_id": view.trigger_event_id,
                "origin_tick_id": view.origin_tick_id,
                "cutoff_snapshot_id": view.cutoff_snapshot_id,
                "cutoff_cursor": view.cursor,
                "cutoff_source_time": view.cutoff_source_time,
                "active_policy_refs": view.active_policy_refs,
                "causal_view_ref": (
                    self._view_path(session.state.session_id, trigger_id)
                    .resolve()
                    .as_posix()
                ),
                "causal_view_sha256": view.view_sha256,
                "prompt_template_id": prompt_template_id,
                "prompt_template_sha256": prompt_template_sha256,
                "response_schema_id": response_schema_id,
                "response_schema_sha256": response_schema_sha256,
                "allowed_options_id": allowed_options_id,
                "allowed_options_sha256": allowed_options_sha256,
                "created_at": view.created_at,
            }
            payload["request_sha256"] = MonitoringReviewRequest.canonical_sha256(payload)
            request = MonitoringReviewRequest.model_validate(payload)
            _write_json_atomic(request_path, request.model_dump(mode="json"))
            return request

    def load_review_request(
        self,
        session_id: str,
        request_sha256: str,
    ) -> MonitoringReviewRequest:
        session_dir = self._session_dir(session_id)
        with self._session_lock(session_id):
            for path in sorted((session_dir / "review_requests").glob("*/request.json")):
                request = MonitoringReviewRequest.model_validate(_read_json(path))
                if request.request_sha256 == request_sha256:
                    view = self.load_causal_view(session_id, request.causal_view_sha256)
                    if request.causal_view_sha256 != view.view_sha256:
                        raise MonitoringReplayConflictError(
                            "review request causal view binding changed"
                        )
                    return request
        raise MonitoringReplayNotFoundError(
            f"monitoring review request not found: {request_sha256}"
        )

    def review_request_ref(self, session_id: str, child_run_id: str) -> str:
        """Ruta autoritativa del request; nunca procede del cliente HTTP."""

        path = (
            self._session_dir(session_id)
            / "review_requests"
            / _safe_digest(child_run_id)
            / "request.json"
        )
        if not path.is_file():
            raise MonitoringReplayNotFoundError(
                f"monitoring review request not found for child: {child_run_id}"
            )
        return path.resolve().as_posix()

    def reserve_dispatch(
        self,
        session: MonitoringSessionView,
        command: MonitoringReviewDispatchCommand,
    ) -> MonitoringReviewDispatchReceipt:
        """Reserva exactamente un intento, sin arrancar todavia el LLM."""

        if command.session_id != session.state.session_id:
            raise MonitoringReplayConflictError("dispatch command session mismatch")
        session_dir = self._session_dir(command.session_id)
        with self._session_lock(command.session_id):
            receipt_path = self._receipt_path(session_dir, command.command_id)
            if receipt_path.is_file():
                stored_payload = _read_json(receipt_path)
                stored_command = MonitoringReviewDispatchCommand.model_validate(
                    stored_payload["command"]
                )
                if stored_command.command_sha256 != command.command_sha256:
                    raise MonitoringReplayConflictError(
                        "dispatch command_id was reused with another payload"
                    )
                original = MonitoringReviewDispatchReceipt.model_validate(
                    stored_payload["receipt"]
                )
                replay_payload = original.model_dump(
                    mode="python",
                    exclude={"receipt_sha256"},
                )
                replay_payload["outcome"] = "idempotent_replay"
                replay_payload["receipt_sha256"] = (
                    MonitoringReviewDispatchReceipt.canonical_sha256(replay_payload)
                )
                return MonitoringReviewDispatchReceipt.model_validate(replay_payload)

            commits = self._read_child_commits(session_dir)
            prior_dispatch_commit = next(
                (
                    item
                    for item in commits
                    if item["attempt"].trigger_id == command.trigger_id
                    and item["attempt"].child_run_id == command.child_run_id
                    and item["attempt"].lifecycle_status == "dispatched"
                ),
                None,
            )
            prior_dispatch = (
                prior_dispatch_commit["attempt"]
                if prior_dispatch_commit is not None
                else None
            )
            if (
                prior_dispatch is not None
                and command.expected_child_revision
                == prior_dispatch.child_revision - 1
            ):
                prior_anchor = prior_dispatch_commit.get("anchor", {})
                if (
                    prior_anchor.get("command_id") != command.command_id
                    or prior_anchor.get("command_sha256")
                    != command.command_sha256
                ):
                    raise MonitoringReplayConflictError(
                        "dispatch receipt is missing and its command anchor differs"
                    )
                trigger = _dispatchable_trigger(session, command.trigger_id)
                request = self.load_review_request(
                    command.session_id,
                    command.request_sha256,
                )
                view = self.load_causal_view(
                    command.session_id,
                    command.causal_view_sha256,
                )
                _validate_command_bindings(
                    command,
                    request,
                    view,
                    trigger,
                    expected_request_ref=self.review_request_ref(
                        command.session_id,
                        command.child_run_id,
                    ),
                )
                recovered_payload: dict[str, Any] = {
                    "receipt_id": f"dispatch-receipt:{command.command_id}",
                    "command_id": command.command_id,
                    "command_sha256": command.command_sha256,
                    "session_id": command.session_id,
                    "trigger_id": command.trigger_id,
                    "trigger_event_id": command.trigger_event_id,
                    "child_run_id": command.child_run_id,
                    "job_id": command.job_id,
                    "run_id": command.run_id,
                    "attempt_no": command.attempt_no,
                    "expected_child_revision": command.expected_child_revision,
                    "child_revision": prior_dispatch.child_revision,
                    "request_ref": command.request_ref,
                    "request_sha256": command.request_sha256,
                    "causal_view_ref": command.causal_view_ref,
                    "causal_view_sha256": command.causal_view_sha256,
                    "outcome": "idempotent_replay",
                    "attempt": prior_dispatch,
                    "error": None,
                    "recorded_at": datetime.now(UTC),
                }
                recovered_payload["receipt_sha256"] = (
                    MonitoringReviewDispatchReceipt.canonical_sha256(
                        recovered_payload
                    )
                )
                recovered = MonitoringReviewDispatchReceipt.model_validate(
                    recovered_payload
                )
                _write_json_atomic(
                    receipt_path,
                    {
                        "schema_version": (
                            "monitoring_review_dispatch_receipt_record_v1"
                        ),
                        "command": command.model_dump(mode="json"),
                        "receipt": recovered.model_dump(mode="json"),
                    },
                )
                return recovered
            current_revision = len(commits)
            if command.expected_child_revision != current_revision:
                raise MonitoringReplayConflictError(
                    "monitoring child revision conflict"
                )
            if any(
                item["attempt"].lifecycle_status in {"dispatched", "running"}
                for item in commits[-1:]
            ):
                raise MonitoringReplayConflictError(
                    "another monitoring child run is active"
                )
            if any(
                item["attempt"].trigger_id == command.trigger_id
                for item in commits
            ):
                raise MonitoringReplayConflictError(
                    "trigger already has a monitoring review attempt"
                )
            trigger = _dispatchable_trigger(session, command.trigger_id)
            request = self.load_review_request(command.session_id, command.request_sha256)
            view = self.load_causal_view(command.session_id, command.causal_view_sha256)
            _validate_command_bindings(
                command,
                request,
                view,
                trigger,
                expected_request_ref=self.review_request_ref(
                    command.session_id,
                    command.child_run_id,
                ),
            )
            now = datetime.now(UTC)
            revision = current_revision + 1
            attempt = MonitoringChildRunAttempt(
                session_id=command.session_id,
                trigger_id=command.trigger_id,
                trigger_event_id=command.trigger_event_id,
                child_run_id=command.child_run_id,
                job_id=command.job_id,
                run_id=command.run_id,
                attempt_no=command.attempt_no,
                child_revision=revision,
                lifecycle_status="dispatched",
                request_ref=command.request_ref,
                request_sha256=command.request_sha256,
                causal_view_ref=command.causal_view_ref,
                causal_view_sha256=command.causal_view_sha256,
                dispatched_at=now,
                updated_at=now,
            )
            self._append_child_commit(
                session_dir,
                operation="dispatched",
                attempt=attempt,
                anchor={
                    "config_sha256": session.state.config_sha256,
                    "trigger_event_id": trigger.event_id,
                    "origin_tick_id": trigger.origin_tick_id,
                    "request_sha256": request.request_sha256,
                    "causal_view_sha256": view.view_sha256,
                    "command_id": command.command_id,
                    "command_sha256": command.command_sha256,
                    "command": command.model_dump(mode="json"),
                },
            )
            receipt_payload: dict[str, Any] = {
                "receipt_id": f"dispatch-receipt:{command.command_id}",
                "command_id": command.command_id,
                "command_sha256": command.command_sha256,
                "session_id": command.session_id,
                "trigger_id": command.trigger_id,
                "trigger_event_id": command.trigger_event_id,
                "child_run_id": command.child_run_id,
                "job_id": command.job_id,
                "run_id": command.run_id,
                "attempt_no": command.attempt_no,
                "expected_child_revision": command.expected_child_revision,
                "child_revision": revision,
                "request_ref": command.request_ref,
                "request_sha256": command.request_sha256,
                "causal_view_ref": command.causal_view_ref,
                "causal_view_sha256": command.causal_view_sha256,
                "outcome": "dispatched",
                "attempt": attempt,
                "error": None,
                "recorded_at": now,
            }
            receipt_payload["receipt_sha256"] = (
                MonitoringReviewDispatchReceipt.canonical_sha256(receipt_payload)
            )
            receipt = MonitoringReviewDispatchReceipt.model_validate(receipt_payload)
            _write_json_atomic(
                receipt_path,
                {
                    "schema_version": "monitoring_review_dispatch_receipt_record_v1",
                    "command": command.model_dump(mode="json"),
                    "receipt": receipt.model_dump(mode="json"),
                },
            )
            return receipt

    def get_dispatch_receipt(
        self,
        session_id: str,
        command_id: str,
    ) -> MonitoringReviewDispatchReceipt | None:
        """Lee el recibo original para reconstruir un retry HTTP byte-equivalente."""

        session_dir = self._session_dir(session_id)
        with self._session_lock(session_id):
            path = self._receipt_path(session_dir, command_id)
            if not path.is_file():
                return None
            payload = _read_json(path)
            command = MonitoringReviewDispatchCommand.model_validate(payload["command"])
            if command.command_id != command_id:
                raise MonitoringReplayConflictError("dispatch receipt identity changed")
            return MonitoringReviewDispatchReceipt.model_validate(payload["receipt"])

    def get_dispatch_command(
        self,
        session_id: str,
        command_id: str,
    ) -> MonitoringReviewDispatchCommand | None:
        """Recupera el comando sellado para un retry de transporte idempotente."""

        session_dir = self._session_dir(session_id)
        with self._session_lock(session_id):
            path = self._receipt_path(session_dir, command_id)
            if path.is_file():
                command = MonitoringReviewDispatchCommand.model_validate(
                    _read_json(path)["command"]
                )
                if command.command_id != command_id:
                    raise MonitoringReplayConflictError(
                        "dispatch receipt identity changed"
                    )
                return command
            commits = self._read_child_commits(session_dir)
            matches = [
                item["anchor"]
                for item in commits
                if item["operation"] == "dispatched"
                and item["anchor"].get("command_id") == command_id
            ]
            if not matches:
                return None
            if len(matches) != 1 or not isinstance(matches[0].get("command"), dict):
                raise MonitoringReplayConflictError(
                    "dispatch command anchor is ambiguous"
                )
            command = MonitoringReviewDispatchCommand.model_validate(
                matches[0]["command"]
            )
            if command.command_sha256 != matches[0].get("command_sha256"):
                raise MonitoringReplayConflictError(
                    "dispatch command anchor changed"
                )
            return command

    def mark_running(
        self,
        session_id: str,
        child_run_id: str,
    ) -> MonitoringChildRunAttempt:
        return self._transition(session_id, child_run_id, "running")

    def mark_terminal(
        self,
        session_id: str,
        child_run_id: str,
        result: MonitoringReviewResult,
    ) -> MonitoringChildRunAttempt:
        status = "resolved" if result.status == "completed" else "failed"
        return self._transition(
            session_id,
            child_run_id,
            status,
            result=result,
            error=result.failure_reason,
        )

    def mark_interrupted(
        self,
        session_id: str,
        child_run_id: str,
        error: str,
    ) -> MonitoringChildRunAttempt:
        return self._transition(
            session_id,
            child_run_id,
            "interrupted",
            error=error,
        )

    def get_attempt(
        self,
        session_id: str,
        child_run_id: str,
    ) -> MonitoringChildRunAttempt:
        attempts = self.list_attempts(session_id)
        found = next((item for item in attempts if item.child_run_id == child_run_id), None)
        if found is None:
            raise MonitoringReplayNotFoundError(f"child run not found: {child_run_id}")
        return found

    def list_attempts(self, session_id: str) -> tuple[MonitoringChildRunAttempt, ...]:
        with self._session_lock(session_id):
            commits = self._read_child_commits(self._session_dir(session_id))
            return self._latest_attempts_from_commits(commits)

    @staticmethod
    def _latest_attempts_from_commits(
        commits: list[dict[str, Any]],
    ) -> tuple[MonitoringChildRunAttempt, ...]:
        latest: dict[str, MonitoringChildRunAttempt] = {}
        order: list[str] = []
        for commit in commits:
            attempt = commit["attempt"]
            if attempt.child_run_id not in latest:
                order.append(attempt.child_run_id)
            latest[attempt.child_run_id] = attempt
        return tuple(latest[item] for item in order)

    def active_child_run_id(self, session_id: str) -> str | None:
        active = [
            item.child_run_id
            for item in self.list_attempts(session_id)
            if item.lifecycle_status in {"dispatched", "running"}
        ]
        if len(active) > 1:
            raise MonitoringReplayConflictError(
                "monitoring child ledger contains multiple active runs"
            )
        return active[0] if active else None

    def reconcile_orphaned_attempts(
        self,
        session_id: str,
        *,
        job_exists: Callable[[str], bool],
    ) -> tuple[MonitoringChildRunAttempt, ...]:
        """Cierra intentos activos cuyo lanzador local desaparecio.

        El ledger hijo es durable, pero los hilos de ``ApiRunJobStore`` no lo
        son. Tras reiniciar la API no se relanza automaticamente una llamada
        LLM incierta: si existe un resultado completo se recupera su terminal;
        en otro caso el intento queda ``interrupted`` y deja de bloquear el
        replay. Un retry explicito posterior pertenecera a otro incremento.
        """

        for attempt in self.list_attempts(session_id):
            if attempt.lifecycle_status not in {"dispatched", "running"}:
                continue
            if job_exists(attempt.job_id):
                continue
            result_path = (
                self.runs_root
                / attempt.child_run_id
                / "monitoring_review_result.json"
            )
            snapshot_path = self.runs_root / attempt.child_run_id / "snapshot.json"
            if result_path.is_file() and snapshot_path.is_file():
                result = MonitoringReviewResult.model_validate(
                    _read_json(result_path)
                )
                self._validate_result_binding(attempt, result)
                self.mark_terminal(session_id, attempt.child_run_id, result)
                continue
            self.mark_interrupted(
                session_id,
                attempt.child_run_id,
                "the local background job was lost before a complete result was persisted",
            )
        return self.list_attempts(session_id)

    def reconcile_orphaned_sessions(
        self,
        *,
        job_exists: Callable[[str], bool],
    ) -> dict[str, str]:
        """Reconcilia una vez los intentos locales al arrancar la API."""

        errors: dict[str, str] = {}
        if not self.sessions_root.is_dir():
            return errors
        for session_dir in sorted(self.sessions_root.iterdir()):
            if not session_dir.is_dir() or not (
                session_dir / "child_run_commits"
            ).is_dir():
                continue
            try:
                self.reconcile_orphaned_attempts(
                    session_dir.name,
                    job_exists=job_exists,
                )
            except (
                MonitoringReplayConflictError,
                MonitoringReplayNotFoundError,
                OSError,
                ValueError,
            ) as exc:
                errors[session_dir.name] = str(exc)
        return errors

    def project_session(
        self,
        session: MonitoringSessionView,
    ) -> MonitoringReviewSessionProjection:
        with self._session_lock(session.state.session_id):
            commits = self._read_child_commits(self._session_dir(session.state.session_id))
            self._validate_ledger_anchors(session, commits)
            attempts = self._latest_attempts_from_commits(commits)
            return MonitoringReviewSessionProjection(
                child_revision=len(commits),
                attempts=attempts,
                lifecycle_events=_project_lifecycle_events(session, commits),
                active_child_run_id=next(
                    (
                        item.child_run_id
                        for item in attempts
                        if item.lifecycle_status in {"dispatched", "running"}
                    ),
                    None,
                ),
            )

    def decorate_session(self, session: MonitoringSessionView) -> MonitoringSessionView:
        projection = self.project_session(session)
        return session.model_copy(
            update={
                "triggers": (*session.triggers, *projection.lifecycle_events),
                "child_revision": projection.child_revision,
                "child_runs": projection.attempts,
                "active_child_run_id": projection.active_child_run_id,
            }
        )

    def assert_step_allowed(self, session: MonitoringSessionView) -> None:
        with self._session_lock(session.state.session_id):
            commits = self._read_child_commits(
                self._session_dir(session.state.session_id)
            )
            self._validate_ledger_anchors(session, commits)
            self._assert_step_allowed_from_commits(session, commits)

    def assert_step_allowed_while_session_locked(
        self,
        session: MonitoringSessionView,
    ) -> None:
        """Valida el avance cuando el replay ya posee ``.session.lock``.

        ``MonitoringReplayStore.step`` invoca este guard dentro de la misma
        seccion critica que confirma el tick. Reabrir aqui el flock compartido
        bloquearia el propio proceso, por lo que se lee el ledger hijo bajo el
        lock que ya posee el llamador.
        """

        commits = self._read_child_commits(
            self._session_dir(session.state.session_id)
        )
        self._validate_ledger_anchors(
            session,
            commits,
            session_lock_already_held=True,
        )
        self._assert_step_allowed_from_commits(session, commits)

    @staticmethod
    def _assert_step_allowed_from_commits(
        session: MonitoringSessionView,
        commits: list[dict[str, Any]],
    ) -> None:
        latest_by_child: dict[str, MonitoringChildRunAttempt] = {}
        for commit in commits:
            attempt = commit["attempt"]
            latest_by_child[attempt.child_run_id] = attempt
        attempts = {
            item.trigger_id: item for item in latest_by_child.values()
        }
        pending = [
            event
            for event in session.triggers
            if event.lifecycle_status == "emitted"
            and event.trigger_id not in attempts
            and event.trigger_type != "session_close"
        ]
        if pending:
            raise MonitoringReplayConflictError(
                "an emitted monitoring trigger awaits its guided review"
            )
        if any(
            item.lifecycle_status in {"dispatched", "running"}
            for item in attempts.values()
        ):
            raise MonitoringReplayConflictError(
                "a monitoring child run is still active"
            )

    def _transition(
        self,
        session_id: str,
        child_run_id: str,
        status: str,
        *,
        result: MonitoringReviewResult | None = None,
        error: str | None = None,
    ) -> MonitoringChildRunAttempt:
        session_dir = self._session_dir(session_id)
        with self._session_lock(session_id):
            commits = self._read_child_commits(session_dir)
            current = next(
                (
                    item["attempt"]
                    for item in reversed(commits)
                    if item["attempt"].child_run_id == child_run_id
                ),
                None,
            )
            if current is None:
                raise MonitoringReplayNotFoundError(f"child run not found: {child_run_id}")
            expected = {
                "running": {"dispatched"},
                "resolved": {"running"},
                "failed": {"running"},
                "interrupted": {"running", "dispatched"},
            }[status]
            if current.lifecycle_status not in expected:
                if current.lifecycle_status == status:
                    return current
                raise MonitoringReplayConflictError(
                    f"invalid child transition {current.lifecycle_status}->{status}"
                )
            if result is not None:
                self._validate_result_binding(current, result)
                result_ref = (
                    self.runs_root / child_run_id / "monitoring_review_result.json"
                ).resolve().as_posix()
                result_sha = result.result_sha256
            else:
                result_ref = None
                result_sha = None
            now = datetime.now(UTC)
            started = current.started_at or now
            updated = MonitoringChildRunAttempt.model_validate(
                {
                    **current.model_dump(mode="python"),
                    "child_revision": len(commits) + 1,
                    "lifecycle_status": status,
                    "started_at": started,
                    "completed_at": now if status != "running" else None,
                    "updated_at": now,
                    "result_ref": result_ref,
                    "result_sha256": result_sha,
                    "error": error,
                }
            )
            self._append_child_commit(
                session_dir,
                operation=status,
                attempt=updated,
                anchor=next(
                    item["anchor"]
                    for item in commits
                    if item["attempt"].child_run_id == child_run_id
                ),
            )
            return updated

    @staticmethod
    def _validate_result_binding(
        attempt: MonitoringChildRunAttempt,
        result: MonitoringReviewResult,
    ) -> None:
        if (
            result.child_run_id != attempt.child_run_id
            or result.session_id != attempt.session_id
            or result.trigger_id != attempt.trigger_id
            or result.trigger_event_id != attempt.trigger_event_id
            or result.request_sha256 != attempt.request_sha256
            or result.causal_view_sha256 != attempt.causal_view_sha256
        ):
            raise MonitoringReplayConflictError(
                "review result does not bind the child attempt"
            )

    def _append_child_commit(
        self,
        session_dir: Path,
        *,
        operation: str,
        attempt: MonitoringChildRunAttempt,
        anchor: dict[str, Any],
    ) -> None:
        commits = self._read_child_commits(session_dir)
        previous = commits[-1]["commit_sha256"] if commits else None
        core = {
            "schema_version": "monitoring_child_run_commit_v1",
            "revision": len(commits) + 1,
            "previous_commit_sha256": previous,
            "operation": operation,
            "anchor": anchor,
            "attempt": attempt.model_dump(mode="json"),
        }
        payload = {**core, "commit_sha256": _canonical_sha256(core)}
        path = session_dir / "child_run_commits" / f"{len(commits) + 1:06d}.json"
        _write_json_atomic(path, payload)

    def _read_child_commits(self, session_dir: Path) -> list[dict[str, Any]]:
        root = session_dir / "child_run_commits"
        if not root.exists():
            return []
        payloads: list[dict[str, Any]] = []
        previous: str | None = None
        latest_by_child: dict[str, MonitoringChildRunAttempt] = {}
        anchor_by_child: dict[str, dict[str, Any]] = {}
        for revision, path in enumerate(sorted(root.glob("*.json")), start=1):
            payload = _read_json(path)
            core = {key: value for key, value in payload.items() if key != "commit_sha256"}
            if (
                payload.get("revision") != revision
                or payload.get("previous_commit_sha256") != previous
                or payload.get("commit_sha256") != _canonical_sha256(core)
            ):
                raise MonitoringReplayConflictError("monitoring child ledger chain is invalid")
            attempt = MonitoringChildRunAttempt.model_validate(payload["attempt"])
            if attempt.child_revision != revision:
                raise MonitoringReplayConflictError("monitoring child revision is invalid")
            prior = latest_by_child.get(attempt.child_run_id)
            if prior is None:
                if attempt.lifecycle_status != "dispatched" or attempt.attempt_no != 1:
                    raise MonitoringReplayConflictError("child attempt must start as dispatched")
                anchor_by_child[attempt.child_run_id] = payload.get("anchor")
            else:
                if payload.get("anchor") != anchor_by_child[attempt.child_run_id]:
                    raise MonitoringReplayConflictError("monitoring child ledger anchor changed")
                allowed = {
                    "dispatched": {"running", "interrupted"},
                    "running": {"resolved", "failed", "interrupted"},
                    "resolved": set(),
                    "failed": set(),
                    "interrupted": set(),
                }[prior.lifecycle_status]
                if attempt.lifecycle_status not in allowed:
                    raise MonitoringReplayConflictError("invalid persisted child lifecycle transition")
                for field in (
                    "session_id",
                    "trigger_id",
                    "trigger_event_id",
                    "child_run_id",
                    "job_id",
                    "run_id",
                    "attempt_no",
                    "request_ref",
                    "request_sha256",
                    "causal_view_ref",
                    "causal_view_sha256",
                    "dispatched_at",
                ):
                    if getattr(attempt, field) != getattr(prior, field):
                        raise MonitoringReplayConflictError("persisted child identity changed")
            latest_by_child[attempt.child_run_id] = attempt
            previous = payload["commit_sha256"]
            payloads.append({**payload, "attempt": attempt})
        for attempt in latest_by_child.values():
            if attempt.lifecycle_status in {"resolved", "failed"}:
                self._validate_persisted_terminal_result(attempt)
        active = [
            item for item in latest_by_child.values()
            if item.lifecycle_status in {"dispatched", "running"}
        ]
        if len(active) > 1:
            raise MonitoringReplayConflictError("multiple child runs are active")
        return payloads

    def _validate_persisted_terminal_result(
        self,
        attempt: MonitoringChildRunAttempt,
    ) -> None:
        expected = (
            self.runs_root
            / attempt.child_run_id
            / "monitoring_review_result.json"
        )
        if expected.is_symlink() or not expected.is_file():
            raise MonitoringReplayConflictError(
                "terminal monitoring review result is unavailable"
            )
        resolved = expected.resolve()
        if attempt.result_ref != resolved.as_posix():
            raise MonitoringReplayConflictError(
                "terminal monitoring review result reference changed"
            )
        raw_result = _read_json(resolved)
        claimed_sha256 = raw_result.get("result_sha256")
        canonical_raw = {
            key: value
            for key, value in raw_result.items()
            if key != "result_sha256"
        }
        if (
            claimed_sha256 != attempt.result_sha256
            or _canonical_sha256(canonical_raw) != claimed_sha256
        ):
            raise MonitoringReplayConflictError(
                "terminal monitoring review result SHA-256 changed"
            )
        raw_binding = (
            raw_result.get("child_run_id"),
            raw_result.get("session_id"),
            raw_result.get("trigger_id"),
            raw_result.get("trigger_event_id"),
            raw_result.get("request_sha256"),
            raw_result.get("causal_view_sha256"),
        )
        attempt_binding = (
            attempt.child_run_id,
            attempt.session_id,
            attempt.trigger_id,
            attempt.trigger_event_id,
            attempt.request_sha256,
            attempt.causal_view_sha256,
        )
        if raw_binding != attempt_binding:
            raise MonitoringReplayConflictError(
                "terminal monitoring review result binding changed"
            )
        events_ref = Path(str(raw_result.get("runtime_events_ref", "")))
        expected_events = (
            self.runs_root
            / attempt.child_run_id
            / "monitoring_review_events.json"
        ).resolve()
        if (
            events_ref.is_symlink()
            or not events_ref.is_file()
            or events_ref.resolve() != expected_events
        ):
            raise MonitoringReplayConflictError(
                "terminal monitoring review runtime events are unavailable"
            )
        if _file_sha256(expected_events) != raw_result.get("runtime_events_sha256"):
            raise MonitoringReplayConflictError(
                "terminal monitoring review runtime events SHA-256 changed"
            )

    def _validate_ledger_anchors(
        self,
        session: MonitoringSessionView,
        commits: list[dict[str, Any]],
        *,
        session_lock_already_held: bool = False,
    ) -> None:
        if not commits:
            return
        seen_children: set[str] = set()
        for commit in commits:
            attempt = commit["attempt"]
            if attempt.child_run_id in seen_children:
                continue
            seen_children.add(attempt.child_run_id)
            anchor = commit["anchor"]
            if anchor.get("config_sha256") != session.state.config_sha256:
                raise MonitoringReplayConflictError("child ledger config anchor changed")
            trigger = next(
                (
                    event
                    for event in session.triggers
                    if event.event_id == anchor.get("trigger_event_id")
                    and event.lifecycle_status == "emitted"
                ),
                None,
            )
            if trigger is None or trigger.origin_tick_id != anchor.get("origin_tick_id"):
                raise MonitoringReplayConflictError("child ledger trigger anchor changed")
            if session_lock_already_held:
                request = self._load_review_request_while_locked(
                    session.state.session_id,
                    str(anchor.get("request_sha256")),
                )
                view = self._load_causal_view_while_locked(
                    session.state.session_id,
                    str(anchor.get("causal_view_sha256")),
                )
            else:
                request = self.load_review_request(
                    session.state.session_id,
                    str(anchor.get("request_sha256")),
                )
                view = self.load_causal_view(
                    session.state.session_id,
                    str(anchor.get("causal_view_sha256")),
                )
            if (
                request.trigger_event_id != trigger.event_id
                or view.origin_tick_id != trigger.origin_tick_id
                or request.child_run_id != attempt.child_run_id
            ):
                raise MonitoringReplayConflictError("child ledger causal anchor changed")

    def _load_causal_view_while_locked(
        self,
        session_id: str,
        view_sha256: str,
    ) -> CausalInputView:
        session_dir = self._session_dir(session_id)
        for path in sorted((session_dir / "causal_views").glob("*/view.json")):
            view = self._load_view_path(session_dir, path)
            if view.view_sha256 == view_sha256:
                return view
        raise MonitoringReplayNotFoundError(
            f"causal input view not found: {view_sha256}"
        )

    def _load_review_request_while_locked(
        self,
        session_id: str,
        request_sha256: str,
    ) -> MonitoringReviewRequest:
        session_dir = self._session_dir(session_id)
        for path in sorted((session_dir / "review_requests").glob("*/request.json")):
            request = MonitoringReviewRequest.model_validate(_read_json(path))
            if request.request_sha256 != request_sha256:
                continue
            view = self._load_causal_view_while_locked(
                session_id,
                request.causal_view_sha256,
            )
            if request.causal_view_sha256 != view.view_sha256:
                raise MonitoringReplayConflictError(
                    "review request causal view binding changed"
                )
            return request
        raise MonitoringReplayNotFoundError(
            f"monitoring review request not found: {request_sha256}"
        )

    def _load_view_path(self, session_dir: Path, path: Path) -> CausalInputView:
        safe_path = self._contained_artifact(session_dir, path.as_posix())
        view = CausalInputView.model_validate(_read_json(safe_path))
        manifest = self._contained_artifact(session_dir, view.manifest_projection_ref)
        if _file_sha256(manifest) != view.manifest_projection_sha256:
            raise MonitoringReplayConflictError("causal manifest SHA-256 changed")
        for item in view.evidence:
            evidence = self._contained_artifact(session_dir, item.artifact_ref)
            if _file_sha256(evidence) != item.artifact_sha256:
                raise MonitoringReplayConflictError("causal evidence SHA-256 changed")
        catalog_path = self._catalog_path_for_view(view)
        if catalog_path.exists():
            safe_catalog = self._contained_artifact(
                session_dir,
                catalog_path.as_posix(),
            )
            evidence_path = self._contained_artifact(
                session_dir,
                view.evidence[0].artifact_ref,
            )
            records_payload = _read_json(evidence_path)
            if not isinstance(records_payload, list):
                raise MonitoringReplayConflictError(
                    "causal evidence must remain a list"
                )
            records = [dict(item) for item in records_payload]
            catalog = CausalEvidenceCatalog.model_validate(
                _read_json(safe_catalog)
            )
            validate_causal_evidence_catalog(view, records, catalog)
        return view

    @staticmethod
    def _catalog_path_for_view(view: CausalInputView) -> Path:
        return Path(view.evidence[0].artifact_ref).parent / "evidence_catalog.json"

    def _contained_artifact(self, session_dir: Path, value: str) -> Path:
        path = Path(value)
        if path.is_symlink():
            raise MonitoringReplayConflictError("monitoring artifacts cannot be symlinks")
        resolved = path.resolve()
        root = session_dir.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise MonitoringReplayConflictError("monitoring artifact escapes its session")
        return resolved

    def _view_path(self, session_id: str, trigger_id: str) -> Path:
        return self._session_dir(session_id) / "causal_views" / _safe_digest(trigger_id) / "view.json"

    def _receipt_path(self, session_dir: Path, command_id: str) -> Path:
        return session_dir / "child_run_receipts" / f"{_safe_digest(command_id)}.json"

    def _session_dir(self, session_id: str) -> Path:
        if (
            not session_id
            or len(session_id) > 160
            or not session_id[0].isalnum()
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-" for character in session_id)
        ):
            raise MonitoringReplayConflictError("invalid monitoring session_id")
        root = self.sessions_root.resolve()
        session_dir = (root / session_id).resolve()
        if session_dir.parent != root or not session_dir.is_dir():
            raise MonitoringReplayNotFoundError(f"unknown monitoring session: {session_id}")
        return session_dir

    @contextmanager
    def _session_lock(self, session_id: str):
        session_dir = self._session_dir(session_id)
        with self._process_lock:
            depths = getattr(self._local, "session_lock_depths", {})
            depth = depths.get(session_id, 0)
            if depth:
                depths[session_id] = depth + 1
                self._local.session_lock_depths = depths
                try:
                    yield
                finally:
                    depths[session_id] -= 1
                return
            depths[session_id] = 1
            self._local.session_lock_depths = depths
            with (session_dir / ".session.lock").open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    depths.pop(session_id, None)


def _dispatchable_trigger(
    session: MonitoringSessionView,
    trigger_id: str,
) -> MonitoringTriggerEvent:
    matches = [event for event in session.triggers if event.trigger_id == trigger_id]
    emitted = [event for event in matches if event.lifecycle_status == "emitted"]
    if len(emitted) != 1:
        raise MonitoringReplayConflictError(
            "only one primary emitted trigger can launch a monitoring review"
        )
    if any(event.lifecycle_status in {"suppressed", "coalesced"} for event in matches):
        raise MonitoringReplayConflictError("suppressed or coalesced triggers cannot dispatch")
    return emitted[0]


def _causal_records(
    session: MonitoringSessionView,
    ticks: tuple,
    trigger: MonitoringTriggerEvent,
) -> list[dict[str, Any]]:
    """Selecciona evidencia causal compacta sin resumirla con otro LLM.

    Se conserva el frame modelado inicial, el inicio de la condicion, los ocho
    frames modelados mas recientes y, en el tick origen, las cuatro coordenadas
    sensoriales. Asi todos los roles ven contexto temporal y calidad actual sin
    introducir cientos de filas repetidas en cada prompt.
    """

    selected_tick_ids = {ticks[0].tick_id}
    selected_tick_ids.update(tick.tick_id for tick in ticks[-8:])
    if trigger.condition_start_cursor is not None:
        selected_tick_ids.update(
            tick.tick_id
            for tick in ticks
            if tick.cursor == trigger.condition_start_cursor
        )
    origin_tick_id = trigger.origin_tick_id
    records: list[dict[str, Any]] = []
    for tick in ticks:
        if tick.tick_id not in selected_tick_ids and tick.tick_id != origin_tick_id:
            continue
        for frame in tick.frames:
            if tick.tick_id != origin_tick_id and frame.analysis_status != "modeled":
                continue
            telemetry = frame.telemetry
            records.append(
                {
                    "record_id": frame.frame_id,
                    "dataset_id": session.config.dataset_id,
                    "trajectory_id": session.config.trajectory_id,
                    "asset_id": frame.asset_id,
                    "channel_id": frame.channel_id,
                    "snapshot_id": tick.snapshot_id,
                    "source_time": tick.source_time.isoformat(),
                    "segment_id": frame.segment_id,
                    "analysis_status": frame.analysis_status,
                    "signal_rms": None if telemetry is None else telemetry.signal_rms,
                    "signal_peak_abs": None if telemetry is None else telemetry.signal_peak_abs,
                    "n_samples": None if telemetry is None else telemetry.n_samples,
                    "score": frame.score,
                    "threshold": frame.threshold,
                    "score_ratio": frame.score_ratio,
                    "health_index": frame.health_index,
                    "risk_index": frame.risk_index,
                    "health_state": frame.health_state,
                    "gap_detected": frame.gap_detected,
                    "interval_seconds": frame.interval_seconds,
                    "scoring_version": frame.scoring_version,
                    "activation_version": tick.active_policy_refs.activation_version,
                }
            )
    return records


def _validate_command_bindings(
    command: MonitoringReviewDispatchCommand,
    request: MonitoringReviewRequest,
    view: CausalInputView,
    trigger: MonitoringTriggerEvent,
    *,
    expected_request_ref: str,
) -> None:
    bindings = (
        command.session_id == request.session_id == view.session_id == trigger.session_id,
        command.trigger_id == request.trigger_id == view.trigger_id == trigger.trigger_id,
        command.trigger_event_id == request.trigger_event_id == view.trigger_event_id == trigger.event_id,
        command.child_run_id == request.child_run_id,
        command.request_ref == expected_request_ref,
        command.request_sha256 == request.request_sha256,
        command.causal_view_sha256 == view.view_sha256,
        command.causal_view_ref == request.causal_view_ref,
    )
    if not all(bindings):
        raise MonitoringReplayConflictError("dispatch command causal bindings mismatch")


def _project_lifecycle_events(
    session: MonitoringSessionView,
    commits: list[dict[str, Any]],
) -> tuple[MonitoringTriggerEvent, ...]:
    bases = {
        event.trigger_id: event
        for event in session.triggers
        if event.lifecycle_status == "emitted"
    }
    prior_event: dict[str, str] = {}
    revisions: dict[str, int] = {}
    projected: list[MonitoringTriggerEvent] = []
    labels = {
        "dispatched": "Revision multiagente reservada.",
        "running": "Los siete agentes estan revisando la evidencia causal.",
        "resolved": "Revision multiagente completada; la politica no se aplico.",
        "failed": "La revision multiagente finalizo con error.",
        "interrupted": "La revision fue interrumpida por la infraestructura.",
    }
    for commit in commits:
        attempt = commit["attempt"]
        base = bases.get(attempt.trigger_id)
        if base is None:
            raise MonitoringReplayConflictError("child ledger references an unknown trigger")
        revision = revisions.get(base.trigger_id, base.lifecycle_revision) + 1
        revisions[base.trigger_id] = revision
        lifecycle = "failed" if attempt.lifecycle_status == "interrupted" else attempt.lifecycle_status
        event_id = f"child-event:{_safe_digest(attempt.child_run_id + ':' + str(attempt.child_revision))}"
        projected.append(
            MonitoringTriggerEvent.model_validate(
                {
                    **base.model_dump(mode="python"),
                    "event_id": event_id,
                    "sequence": 1_000_000 + attempt.child_revision,
                    "lifecycle_revision": revision,
                    "previous_event_id": prior_event.get(base.trigger_id, base.event_id),
                    "lifecycle_status": lifecycle,
                    "reason": labels[attempt.lifecycle_status],
                    "budget_reservation_index": None,
                    "child_run_id": attempt.child_run_id,
                    "recorded_at": attempt.updated_at,
                }
            )
        )
        prior_event[base.trigger_id] = event_id
    return tuple(projected)


def _safe_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_causal_evidence_records(
    causal_view: CausalInputView,
    records: list[dict[str, Any]],
) -> None:
    """Liga los registros entregados al unico artefacto sellado de la vista v1.

    El runner recibe objetos Python ya cargados para no volver a abrir rutas en
    cada nodo. Esta comprobacion evita que un caller conserve el mismo
    ``CausalInputView`` pero sustituya, vacie o mutile los registros antes de
    construir el prompt.
    """

    if len(causal_view.evidence) != 1:
        raise MonitoringReplayConflictError(
            "monitoring review v1 expects one canonical evidence artifact"
        )
    artifact = causal_view.evidence[0]
    if not records or len(records) != artifact.record_count:
        raise MonitoringReplayConflictError(
            "causal evidence record count does not match its sealed artifact"
        )
    serialized = json.dumps(
        records,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if hashlib.sha256(serialized).hexdigest() != artifact.artifact_sha256:
        raise MonitoringReplayConflictError(
            "causal evidence records do not match the sealed artifact SHA-256"
        )

    expected_fields = set(artifact.fields)
    record_ids: list[str] = []
    for record in records:
        if set(record) != expected_fields:
            raise MonitoringReplayConflictError(
                "causal evidence record fields do not match the sealed catalog"
            )
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise MonitoringReplayConflictError(
                "causal evidence record_id must be a non-empty string"
            )
        record_ids.append(record_id)
        source_time = record.get("source_time")
        if not isinstance(source_time, str):
            raise MonitoringReplayConflictError(
                "causal evidence source_time must be an ISO-8601 string"
            )
        try:
            observed_at = datetime.fromisoformat(source_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MonitoringReplayConflictError(
                "causal evidence source_time must be an ISO-8601 string"
            ) from exc
        try:
            exceeds_artifact = observed_at > artifact.max_source_time
            exceeds_view = observed_at > causal_view.cutoff_source_time
        except TypeError as exc:
            raise MonitoringReplayConflictError(
                "causal evidence and cutoff times use incompatible timezones"
            ) from exc
        if exceeds_artifact or exceeds_view:
            raise MonitoringReplayConflictError(
                "causal evidence record exceeds its sealed cutoff"
            )
    if len(record_ids) != len(set(record_ids)):
        raise MonitoringReplayConflictError(
            "causal evidence records must have unique record_id values"
        )


def build_causal_evidence_catalog(
    causal_view: CausalInputView,
    records: list[dict[str, Any]],
) -> CausalEvidenceCatalog:
    """Proyecta E01..EN de forma estable sobre registros ya sellados."""

    validate_causal_evidence_records(causal_view, records)
    if len(causal_view.evidence) != 1:
        raise MonitoringReplayConflictError(
            "causal evidence catalog v1 requires one source artifact"
        )
    if len(records) > 99:
        raise MonitoringReplayConflictError(
            "causal evidence catalog v1 supports at most 99 records"
        )
    artifact = causal_view.evidence[0]
    entries: list[CausalEvidenceCatalogEntry] = []
    for index, record in enumerate(records):
        record_sha256 = _canonical_sha256(record)
        handle = f"E{index + 1:02d}"
        display_projection = _causal_evidence_display_projection_payload(
            handle=handle,
            record_sha256=record_sha256,
            record=record,
        )
        entries.append(
            CausalEvidenceCatalogEntry(
                handle=handle,
                record_index=index,
                causal_scope_ref=artifact.evidence_id,
                support_ref=(
                    "causal-record:"
                    f"{artifact.artifact_sha256}:{record_sha256}"
                ),
                record_id=str(record["record_id"]),
                record_sha256=record_sha256,
                display_projection_sha256=_canonical_sha256(
                    display_projection
                ),
            )
        )
    payload: dict[str, Any] = {
        "catalog_id": f"causal-evidence-catalog:{causal_view.view_sha256}",
        "causal_view_sha256": causal_view.view_sha256,
        "source_artifact_sha256": artifact.artifact_sha256,
        "causal_scope_refs": tuple(
            item.evidence_id for item in causal_view.evidence
        ),
        "entries": tuple(entries),
    }
    payload["catalog_sha256"] = CausalEvidenceCatalog.canonical_sha256(payload)
    return CausalEvidenceCatalog.model_validate(payload)


def validate_causal_evidence_catalog(
    causal_view: CausalInputView,
    records: list[dict[str, Any]],
    catalog: CausalEvidenceCatalog,
) -> None:
    """Comprueba mapping, orden, refs y hash contra vista y registros reales."""

    expected = build_causal_evidence_catalog(causal_view, records)
    if catalog != expected:
        raise MonitoringReplayConflictError(
            "causal evidence catalog does not match its sealed view and records"
        )


def causal_evidence_display_projection(
    entry: CausalEvidenceCatalogEntry,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Proyecta solo los hechos compactos cuya identidad sella el catalogo."""

    if _canonical_sha256(record) != entry.record_sha256:
        raise MonitoringReplayConflictError(
            "causal evidence display record does not match its catalog entry"
        )
    projection = _causal_evidence_display_projection_payload(
        handle=entry.handle,
        record_sha256=entry.record_sha256,
        record=record,
    )
    if _canonical_sha256(projection) != entry.display_projection_sha256:
        raise MonitoringReplayConflictError(
            "causal evidence display projection does not match its catalog entry"
        )
    return projection


def _causal_evidence_display_projection_payload(
    *,
    handle: str,
    record_sha256: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "handle": handle,
        "record_sha256": record_sha256,
        "snapshot_id": record.get("snapshot_id"),
        "source_time": record.get("source_time"),
        "asset_id": record.get("asset_id"),
        "channel_id": record.get("channel_id"),
        "analysis_status": record.get("analysis_status"),
        "score_ratio": record.get("score_ratio"),
        "health_state": record.get("health_state"),
        "gap_detected": record.get("gap_detected"),
    }


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitoringReplayConflictError(f"invalid monitoring artifact: {path.name}") from exc


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
