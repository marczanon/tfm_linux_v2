"""Motor puro de activacion determinista para el replay de monitorizacion.

El modulo no persiste sesiones, no ejecuta agentes y no conoce FastAPI. Recibe
un ``ReplayTick`` ya cerrado, la politica activa y su checkpoint anterior, y
devuelve las transiciones que deben co-persistirse con ese tick.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from codigo.app.schemas.monitoring_replay import (
    AgentActivationPolicy,
    AgentActivationTriggerRule,
    MonitoringFrame,
    MonitoringTriggerEvent,
    MonitoringTriggerType,
    ReplayActivationCheckpoint,
    ReplayActivationRuleCheckpoint,
    ReplayAssetCheckpoint,
    ReplayTick,
)


_ALERT_STATES = {"warning", "critical"}
_STATE_RANK = {"nominal": 0, "watch": 1, "warning": 2, "critical": 3}


@dataclass(frozen=True)
class TriggerEngineResult:
    """Salida atomica del evaluador para un unico tick."""

    events: tuple[MonitoringTriggerEvent, ...]
    checkpoint: ReplayActivationCheckpoint


@dataclass(frozen=True)
class _TriggerCandidate:
    trigger_type: MonitoringTriggerType
    rule: AgentActivationTriggerRule
    reason_code: str
    reason: str
    episode_id: str | None
    asset_id: str | None
    condition_start_cursor: int
    snapshot_start_id: str
    snapshot_end_id: str
    previous_state: str | None
    new_state: str | None
    frame_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    dedupe_key: str
    forced_suppression: str | None = None
    forced_by_trigger_id: str | None = None


@dataclass(frozen=True)
class _TriggerDecision:
    candidate: _TriggerCandidate
    lifecycle_status: str
    suppression_reason: str | None = None
    suppressed_by_trigger_id: str | None = None
    coalesced_into_trigger_id: str | None = None
    budget_reservation_index: int | None = None
    requested_roles: tuple[str, ...] | None = None


def initial_activation_checkpoint(
    policy: AgentActivationPolicy,
) -> ReplayActivationCheckpoint:
    """Crea el seed congelado de la maquina de activacion."""

    return ReplayActivationCheckpoint(
        activation_version=policy.policy_version,
    )


def evaluate_monitoring_triggers(
    *,
    session_id: str,
    tick: ReplayTick,
    previous_asset_checkpoints: tuple[ReplayAssetCheckpoint, ...],
    current_asset_checkpoints: tuple[ReplayAssetCheckpoint, ...],
    prior_events: tuple[MonitoringTriggerEvent, ...],
    policy: AgentActivationPolicy,
    checkpoint: ReplayActivationCheckpoint,
    session_completed: bool,
) -> TriggerEngineResult:
    """Evalua P0/P2/P3 sin mirar ningun snapshot posterior al tick."""

    _validate_engine_input(policy, checkpoint, prior_events, tick)
    if policy.policy_kind in {"P0", "P1"}:
        return TriggerEngineResult(events=(), checkpoint=checkpoint)

    modeled_frames = tuple(
        frame for frame in tick.frames if frame.analysis_status == "modeled"
    )
    if len(modeled_frames) != 1:
        raise ValueError("trigger engine requires exactly one modeled frame")
    modeled_frame = modeled_frames[0]
    previous = _checkpoint_by_asset(
        previous_asset_checkpoints,
        modeled_frame.asset_id,
    )
    current = _checkpoint_by_asset(
        current_asset_checkpoints,
        modeled_frame.asset_id,
    )

    armed = checkpoint.persistent_alert_armed
    episode_cursor = checkpoint.alert_episode_start_cursor
    episode_snapshot = checkpoint.alert_episode_start_snapshot_id
    episode_id = checkpoint.alert_episode_id
    handled_episode_trigger_id = checkpoint.alert_episode_handled_trigger_id
    persistence_episode_trigger_id = (
        checkpoint.alert_episode_persistence_trigger_id
    )
    is_alert = current.last_health_state in _ALERT_STATES
    if modeled_frame.gap_detected:
        armed = True
        episode_cursor = None
        episode_snapshot = None
        episode_id = None
        handled_episode_trigger_id = None
        persistence_episode_trigger_id = None
        if is_alert and current.alert_persistence_count == 1:
            episode_cursor = tick.cursor
            episode_snapshot = tick.snapshot_id
            episode_id = _stable_episode_id(
                tick.session_id,
                modeled_frame.asset_id,
                current.segment_id,
                tick.cursor,
            )
    elif not is_alert:
        if armed or (
            current.recovery_persistence_count
            >= policy.alert_recovery_persistence_ticks
        ):
            armed = True
            episode_cursor = None
            episode_snapshot = None
            episode_id = None
            handled_episode_trigger_id = None
            persistence_episode_trigger_id = None
    elif current.alert_persistence_count == 1 and episode_id is None:
        episode_cursor = tick.cursor
        episode_snapshot = tick.snapshot_id
        episode_id = _stable_episode_id(
            tick.session_id,
            modeled_frame.asset_id,
            current.segment_id,
            tick.cursor,
        )
        handled_episode_trigger_id = None
        persistence_episode_trigger_id = None

    candidates = _trigger_candidates(
        tick=tick,
        modeled_frame=modeled_frame,
        previous=previous,
        current=current,
        policy=policy,
        checkpoint=checkpoint,
        episode_cursor=episode_cursor,
        episode_snapshot=episode_snapshot,
        episode_id=episode_id,
        handled_episode_trigger_id=handled_episode_trigger_id,
        persistence_episode_trigger_id=persistence_episode_trigger_id,
        armed=armed,
        session_completed=session_completed,
    )
    existing_dedupe = {event.dedupe_key for event in prior_events}
    duplicates = [
        candidate.dedupe_key
        for candidate in candidates
        if candidate.dedupe_key in existing_dedupe
    ]
    if duplicates:
        raise ValueError("trigger engine received an already persisted dedupe key")

    rule_state = {
        item.trigger_type: item for item in checkpoint.rule_checkpoints
    }
    decisions: list[_TriggerDecision] = []
    ready: list[_TriggerCandidate] = []
    next_sequence = checkpoint.next_event_sequence
    slots = checkpoint.variable_run_slots_reserved

    ordered_candidates = sorted(
        candidates,
        key=lambda item: _candidate_order(item, policy),
    )
    for candidate in ordered_candidates:
        if candidate.trigger_type == "persistent_alert":
            armed = False
        if candidate.forced_suppression is not None:
            decisions.append(
                _TriggerDecision(
                    candidate=candidate,
                lifecycle_status="suppressed",
                suppression_reason=candidate.forced_suppression,
                suppressed_by_trigger_id=candidate.forced_by_trigger_id,
                )
            )
            continue
        last_effective = rule_state.get(candidate.trigger_type)
        if (
            last_effective is not None
            and candidate.rule.cooldown_source_seconds > 0.0
            and (
                tick.source_time - last_effective.last_effective_source_time
            ).total_seconds()
            < candidate.rule.cooldown_source_seconds
        ):
            decisions.append(
                _TriggerDecision(
                    candidate=candidate,
                    lifecycle_status="suppressed",
                    suppression_reason="cooldown",
                    suppressed_by_trigger_id=(
                        last_effective.last_effective_trigger_id
                    ),
                )
            )
            continue
        ready.append(candidate)

    groups: dict[str, list[_TriggerCandidate]] = {}
    group_order: list[str] = []
    for candidate in ready:
        group = candidate.rule.coalescing_group or candidate.trigger_type
        if group not in groups:
            groups[group] = []
            group_order.append(group)
        groups[group].append(candidate)

    for group in group_order:
        grouped = groups[group]
        primary = grouped[0]
        consumes_budget = primary.rule.counts_toward_variable_budget
        if consumes_budget and slots >= policy.max_variable_child_runs:
            for candidate in grouped:
                decisions.append(
                    _TriggerDecision(
                        candidate=candidate,
                        lifecycle_status="suppressed",
                        suppression_reason="budget",
                    )
                )
            continue

        primary_trigger_id = _stable_trigger_id(
            session_id,
            primary.dedupe_key,
        )
        merged_roles = tuple(
            dict.fromkeys(
                role
                for candidate in grouped
                for role in candidate.rule.requested_roles
            )
        )
        decisions.append(
            _TriggerDecision(
                candidate=primary,
                lifecycle_status="emitted",
                budget_reservation_index=(
                    slots + 1 if consumes_budget else None
                ),
                requested_roles=merged_roles,
            )
        )
        if consumes_budget:
            slots += 1
        if primary.episode_id is not None and consumes_budget:
            handled_episode_trigger_id = primary_trigger_id
            armed = False
        rule_state[primary.trigger_type] = ReplayActivationRuleCheckpoint(
            trigger_type=primary.trigger_type,
            last_effective_trigger_id=primary_trigger_id,
            last_effective_source_time=tick.source_time,
        )

        for candidate in grouped[1:]:
            decisions.append(
                _TriggerDecision(
                    candidate=candidate,
                    lifecycle_status="coalesced",
                    coalesced_into_trigger_id=primary_trigger_id,
                )
            )
            rule_state[candidate.trigger_type] = ReplayActivationRuleCheckpoint(
                trigger_type=candidate.trigger_type,
                last_effective_trigger_id=primary_trigger_id,
                last_effective_source_time=tick.source_time,
            )
            if candidate.episode_id is not None and consumes_budget:
                handled_episode_trigger_id = primary_trigger_id
                armed = False

    events: list[MonitoringTriggerEvent] = []
    for decision in sorted(
        decisions,
        key=lambda item: _candidate_order(item.candidate, policy),
    ):
        event = _event_from_candidate(
            decision.candidate,
            session_id=session_id,
            tick=tick,
            policy=policy,
            sequence=next_sequence,
            lifecycle_status=decision.lifecycle_status,
            suppression_reason=decision.suppression_reason,
            suppressed_by_trigger_id=decision.suppressed_by_trigger_id,
            coalesced_into_trigger_id=decision.coalesced_into_trigger_id,
            budget_reservation_index=decision.budget_reservation_index,
            requested_roles=decision.requested_roles,
        )
        events.append(event)
        if decision.candidate.trigger_type == "persistent_alert":
            persistence_episode_trigger_id = event.trigger_id
        next_sequence += 1

    ordered_rule_state = tuple(
        rule_state[rule.trigger_type]
        for rule in policy.trigger_rules
        if rule.trigger_type in rule_state
    )
    return TriggerEngineResult(
        events=tuple(events),
        checkpoint=ReplayActivationCheckpoint(
            activation_version=policy.policy_version,
            next_event_sequence=next_sequence,
            variable_run_slots_reserved=slots,
            persistent_alert_armed=armed,
            alert_episode_start_cursor=episode_cursor,
            alert_episode_start_snapshot_id=episode_snapshot,
            alert_episode_id=episode_id,
            alert_episode_handled_trigger_id=handled_episode_trigger_id,
            alert_episode_persistence_trigger_id=(
                persistence_episode_trigger_id
            ),
            last_evaluated_cursor=tick.cursor,
            last_evaluated_tick_id=tick.tick_id,
            rule_checkpoints=ordered_rule_state,
        ),
    )


def _trigger_candidates(
    *,
    tick: ReplayTick,
    modeled_frame: MonitoringFrame,
    previous: ReplayAssetCheckpoint,
    current: ReplayAssetCheckpoint,
    policy: AgentActivationPolicy,
    checkpoint: ReplayActivationCheckpoint,
    episode_cursor: int | None,
    episode_snapshot: str | None,
    episode_id: str | None,
    handled_episode_trigger_id: str | None,
    persistence_episode_trigger_id: str | None,
    armed: bool,
    session_completed: bool,
) -> tuple[_TriggerCandidate, ...]:
    rules = {
        rule.trigger_type: rule
        for rule in policy.trigger_rules
        if rule.enabled
    }
    candidates: list[_TriggerCandidate] = []
    all_frames = tuple(frame.frame_id for frame in tick.frames)
    all_evidence = _evidence_refs(tick.frames, tick.tick_id)
    modeled_evidence = _evidence_refs((modeled_frame,), tick.tick_id)

    periodic = rules.get("periodic_review")
    if periodic is not None and tick.cursor in policy.periodic_cursors:
        candidates.append(
            _TriggerCandidate(
                trigger_type="periodic_review",
                rule=periodic,
                reason_code="periodic_schedule",
                reason="Revisión periódica alcanzada en el calendario congelado.",
                episode_id=None,
                asset_id=modeled_frame.asset_id,
                condition_start_cursor=tick.cursor,
                snapshot_start_id=tick.snapshot_id,
                snapshot_end_id=tick.snapshot_id,
                previous_state=None,
                new_state=None,
                frame_ids=all_frames,
                evidence_refs=all_evidence,
                dedupe_key=_dedupe_key(
                    "periodic",
                    tick.session_id,
                    policy.policy_version,
                    tick.cursor,
                ),
            )
        )

    persistent = rules.get("persistent_alert")
    if (
        persistent is not None
        and current.last_health_state in _ALERT_STATES
        and current.alert_persistence_count
        == policy.alert_entry_persistence_ticks
        and episode_cursor is not None
        and episode_snapshot is not None
        and episode_id is not None
        and persistence_episode_trigger_id is None
    ):
        previous_persistent = next(
            (
                item
                for item in checkpoint.rule_checkpoints
                if item.trigger_type == "persistent_alert"
            ),
            None,
        )
        if handled_episode_trigger_id is not None:
            forced = "episode_already_covered"
            forced_by = handled_episode_trigger_id
        elif not armed:
            forced = "not_rearmed"
            forced_by = (
                previous_persistent.last_effective_trigger_id
                if previous_persistent is not None
                else None
            )
            if forced_by is None:
                raise ValueError(
                    "non-rearmed persistent alert lacks its prior trigger"
                )
        else:
            forced = None
            forced_by = None
        candidates.append(
            _TriggerCandidate(
                trigger_type="persistent_alert",
                rule=persistent,
                reason_code="persistent_confirmation",
                reason=(
                    "Alerta algorítmica persistente confirmada tras "
                    f"{policy.alert_entry_persistence_ticks} snapshots; "
                    "el inicio de la racha y su confirmación se conservan "
                    "por separado."
                ),
                episode_id=episode_id,
                asset_id=modeled_frame.asset_id,
                condition_start_cursor=episode_cursor,
                snapshot_start_id=episode_snapshot,
                snapshot_end_id=tick.snapshot_id,
                previous_state=None,
                new_state=None,
                frame_ids=(modeled_frame.frame_id,),
                evidence_refs=modeled_evidence,
                dedupe_key=_dedupe_key(
                    "persistent",
                    tick.session_id,
                    modeled_frame.asset_id,
                    current.segment_id,
                    episode_cursor,
                    tick.cursor,
                ),
                forced_suppression=forced,
                forced_by_trigger_id=forced_by,
            )
        )

    transition = rules.get("state_transition")
    if (
        transition is not None
        and not modeled_frame.gap_detected
        and previous.last_health_state is not None
        and current.last_health_state in transition.state_transition_targets
        and _STATE_RANK[current.last_health_state]
        > _STATE_RANK[previous.last_health_state]
    ):
        candidates.append(
            _TriggerCandidate(
                trigger_type="state_transition",
                rule=transition,
                reason_code="health_state_escalation",
                reason=(
                    "La política de salud cambia de "
                    f"{previous.last_health_state} a {current.last_health_state}."
                ),
                episode_id=episode_id,
                asset_id=modeled_frame.asset_id,
                condition_start_cursor=tick.cursor,
                snapshot_start_id=tick.snapshot_id,
                snapshot_end_id=tick.snapshot_id,
                previous_state=previous.last_health_state,
                new_state=current.last_health_state,
                frame_ids=(modeled_frame.frame_id,),
                evidence_refs=modeled_evidence,
                dedupe_key=_dedupe_key(
                    "state",
                    tick.session_id,
                    modeled_frame.asset_id,
                    previous.last_health_state,
                    current.last_health_state,
                    tick.cursor,
                ),
            )
        )

    gap = rules.get("continuity_gap")
    if gap is not None and modeled_frame.gap_detected:
        candidates.append(
            _TriggerCandidate(
                trigger_type="continuity_gap",
                rule=gap,
                reason_code="continuity_gap",
                reason=(
                    "El intervalo supera la continuidad permitida y reinicia "
                    "el estado temporal causal."
                ),
                episode_id=None,
                asset_id=modeled_frame.asset_id,
                condition_start_cursor=tick.cursor,
                snapshot_start_id=tick.snapshot_id,
                snapshot_end_id=tick.snapshot_id,
                previous_state=None,
                new_state=None,
                frame_ids=all_frames,
                evidence_refs=all_evidence,
                dedupe_key=_dedupe_key(
                    "gap",
                    tick.session_id,
                    modeled_frame.asset_id,
                    current.segment_id,
                    tick.cursor,
                ),
            )
        )

    close = rules.get("session_close")
    if close is not None and session_completed:
        candidates.append(
            _TriggerCandidate(
                trigger_type="session_close",
                rule=close,
                reason_code="session_completed",
                reason="La sesión alcanza el último snapshot de monitorización.",
                episode_id=episode_id,
                asset_id=modeled_frame.asset_id,
                condition_start_cursor=tick.cursor,
                snapshot_start_id=tick.snapshot_id,
                snapshot_end_id=tick.snapshot_id,
                previous_state=None,
                new_state=None,
                frame_ids=all_frames,
                evidence_refs=all_evidence,
                dedupe_key=_dedupe_key(
                    "close",
                    tick.session_id,
                    policy.policy_version,
                    tick.cursor,
                ),
            )
        )
    return tuple(candidates)


def _event_from_candidate(
    candidate: _TriggerCandidate,
    *,
    session_id: str,
    tick: ReplayTick,
    policy: AgentActivationPolicy,
    sequence: int,
    lifecycle_status: str,
    suppression_reason: str | None = None,
    suppressed_by_trigger_id: str | None = None,
    coalesced_into_trigger_id: str | None = None,
    budget_reservation_index: int | None = None,
    requested_roles: tuple[str, ...] | None = None,
) -> MonitoringTriggerEvent:
    trigger_id = _stable_trigger_id(session_id, candidate.dedupe_key)
    return MonitoringTriggerEvent(
        event_id=f"{trigger_id}:event:{sequence:06d}",
        trigger_id=trigger_id,
        session_id=session_id,
        sequence=sequence,
        trigger_type=candidate.trigger_type,
        lifecycle_status=lifecycle_status,
        priority=candidate.rule.priority,
        reason_code=candidate.reason_code,
        reason=candidate.reason,
        episode_id=candidate.episode_id,
        asset_id=candidate.asset_id,
        snapshot_start_id=candidate.snapshot_start_id,
        snapshot_end_id=candidate.snapshot_end_id,
        condition_start_cursor=candidate.condition_start_cursor,
        cutoff_cursor=tick.cursor,
        cutoff_source_time=tick.source_time,
        previous_state=candidate.previous_state,
        new_state=candidate.new_state,
        cooldown_source_seconds=candidate.rule.cooldown_source_seconds,
        coalescing_group=candidate.rule.coalescing_group,
        rearm_policy=candidate.rule.rearm_policy,
        requested_roles=(
            candidate.rule.requested_roles
            if requested_roles is None
            else requested_roles
        ),
        counts_toward_variable_budget=(
            candidate.rule.counts_toward_variable_budget
        ),
        budget_reservation_index=budget_reservation_index,
        dedupe_key=candidate.dedupe_key,
        activation_version=policy.policy_version,
        activation_policy_sha256=policy.policy_sha256,
        origin_tick_id=tick.tick_id,
        frame_ids=candidate.frame_ids,
        evidence_refs=candidate.evidence_refs,
        suppressed_by_trigger_id=suppressed_by_trigger_id,
        suppression_reason=suppression_reason,
        coalesced_into_trigger_id=coalesced_into_trigger_id,
        child_run_id=None,
        recorded_at=tick.committed_at,
    )


def _validate_engine_input(
    policy: AgentActivationPolicy,
    checkpoint: ReplayActivationCheckpoint,
    prior_events: tuple[MonitoringTriggerEvent, ...],
    tick: ReplayTick,
) -> None:
    if checkpoint.activation_version != policy.policy_version:
        raise ValueError("activation checkpoint does not match policy version")
    if checkpoint.next_event_sequence != len(prior_events) + 1:
        raise ValueError("activation event sequence does not match prior ledger")
    if checkpoint.variable_run_slots_reserved > policy.max_variable_child_runs:
        raise ValueError("activation checkpoint exceeds its variable-run budget")
    expected_sequence = tuple(range(1, len(prior_events) + 1))
    if tuple(event.sequence for event in prior_events) != expected_sequence:
        raise ValueError("prior trigger events are not contiguous")
    if policy.policy_kind in {"P2", "P3"}:
        expected_cursor = None if tick.cursor == 0 else tick.cursor - 1
        if checkpoint.last_evaluated_cursor != expected_cursor:
            raise ValueError(
                "activation checkpoint does not precede the evaluated tick"
            )


def _checkpoint_by_asset(
    values: tuple[ReplayAssetCheckpoint, ...],
    asset_id: str,
) -> ReplayAssetCheckpoint:
    matches = tuple(item for item in values if item.asset_id == asset_id)
    if len(matches) != 1:
        raise ValueError("trigger engine requires one checkpoint for modeled asset")
    return matches[0]


def _candidate_order(
    candidate: _TriggerCandidate,
    policy: AgentActivationPolicy,
) -> tuple[int, int, str]:
    try:
        precedence = policy.precedence.index(candidate.trigger_type)
    except ValueError:
        precedence = len(policy.precedence)
    return (precedence, -candidate.rule.priority, candidate.trigger_type)


def _evidence_refs(
    frames: tuple[MonitoringFrame, ...],
    tick_id: str,
) -> tuple[str, ...]:
    values = [f"tick:{tick_id}"]
    for frame in frames:
        values.extend(frame.evidence_refs)
    return tuple(dict.fromkeys(values))


def _stable_trigger_id(session_id: str, dedupe_key: str) -> str:
    digest = hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:20]
    prefix = session_id[:80]
    return f"{prefix}:trigger:{digest}"


def _dedupe_key(kind: str, *parts: object) -> str:
    """Conserva una identidad estable sin concatenar IDs HTTP sin limite."""

    canonical = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


def _stable_episode_id(
    session_id: str,
    asset_id: str,
    segment_id: int,
    cursor: int,
) -> str:
    raw = f"{session_id}:{asset_id}:{segment_id}:{cursor}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"episode:{digest}"
