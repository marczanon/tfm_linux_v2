"""Create reasoning postmortem and optional human review request for a saved run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.state import ArtifactRef, HumanApproval, TFMStateModel
from codigo.app.services.reasoning_audit import (
    build_modeling_retry_postmortem,
    write_reasoning_postmortem,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    load_run_snapshot,
    save_run_snapshot,
)


def main() -> None:
    args = _parse_args()
    result = create_reasoning_audit_for_saved_retry(
        source_run_id=args.source_run_id,
        retry_run_id=args.retry_run_id,
        runs_dir=Path(args.runs_dir),
        request_human_review=args.request_human_review,
        reviewer_hint=args.reviewer,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


def create_reasoning_audit_for_saved_retry(
    *,
    source_run_id: str,
    retry_run_id: str,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    request_human_review: bool = False,
    reviewer_hint: str | None = None,
) -> dict[str, Any]:
    """Builds reasoning artifacts from two persisted snapshots."""

    source_state = _load_state(source_run_id, runs_dir)
    retry_state = _load_state(retry_run_id, runs_dir)
    decision = _retry_decision_from_state(retry_state)
    output_dir = _iteration_dir(retry_state)
    postmortem = build_modeling_retry_postmortem(
        source_run_id=source_state.run_id,
        run_id=retry_state.run_id,
        decision=decision,
        before_metrics=source_state.metrics,
        after_metrics=retry_state.metrics,
        evaluation=retry_state.evaluation,
        request_human_review=request_human_review,
    )
    artifacts = write_reasoning_postmortem(
        postmortem,
        output_dir,
        request_human_review=request_human_review,
        reviewer_hint=reviewer_hint,
    )
    _append_reasoning_links_to_report(
        retry_state.report_path,
        reasoning_report_path=artifacts.report_path,
        review_report_path=artifacts.review_report_path,
    )
    updated_state = _state_with_reasoning_artifacts(
        retry_state,
        source_run_id=source_state.run_id,
        postmortem_id=postmortem.postmortem_id,
        postmortem_path=artifacts.postmortem_path,
        report_path=artifacts.report_path,
        request_path=artifacts.review_request_path,
        request_report_path=artifacts.review_report_path,
        template_path=artifacts.review_template_path,
        request_human_review=request_human_review,
        reviewer_hint=reviewer_hint,
    )
    snapshot = save_run_snapshot(updated_state, runs_dir)
    return {
        "source_run_id": source_run_id,
        "retry_run_id": retry_run_id,
        "postmortem_path": artifacts.postmortem_path,
        "report_path": artifacts.report_path,
        "review_request_path": artifacts.review_request_path,
        "review_report_path": artifacts.review_report_path,
        "review_template_path": artifacts.review_template_path,
        "snapshot_path": snapshot.snapshot_dir,
        "outcome": postmortem.outcome,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--retry-run-id", required=True)
    parser.add_argument("--runs-dir", default="codigo/reports/runs")
    parser.add_argument("--request-human-review", action="store_true")
    parser.add_argument("--reviewer", default=None)
    return parser.parse_args()


def _load_state(run_id: str, runs_dir: Path) -> TFMStateModel:
    snapshot = load_run_snapshot(run_id, runs_dir)
    return TFMStateModel.model_validate(_read_json(snapshot.state_path))


def _retry_decision_from_state(state: TFMStateModel) -> ModelingRetryDecision:
    for message in state.messages:
        if message.name != "modeler":
            continue
        payload = _safe_json(message.content)
        if payload.get("attempt_number") is not None:
            return ModelingRetryDecision.model_validate(payload)
    raise ValueError(f"run {state.run_id} has no ModelingRetryDecision message")


def _iteration_dir(state: TFMStateModel) -> Path:
    if state.report_path:
        return Path(state.report_path).parent
    return Path("codigo/reports") / state.project_context.dataset / state.run_id / "iteration"


def _state_with_reasoning_artifacts(
    state: TFMStateModel,
    *,
    source_run_id: str,
    postmortem_id: str,
    postmortem_path: str,
    report_path: str,
    request_path: str | None,
    request_report_path: str | None,
    template_path: str | None,
    request_human_review: bool,
    reviewer_hint: str | None,
) -> TFMStateModel:
    artifacts = [
        *state.artifacts,
        ArtifactRef(
            name="agentic_reasoning_postmortem",
            artifact_type="log",
            path=postmortem_path,
            producer="modeler",
            metadata={"source_run_id": source_run_id},
        ),
        ArtifactRef(
            name="agentic_reasoning_postmortem_report",
            artifact_type="report",
            path=report_path,
            producer="modeler",
            metadata={"source_run_id": source_run_id},
        ),
    ]
    if request_human_review and request_path and request_report_path and template_path:
        artifacts.extend(
            [
                ArtifactRef(
                    name="human_reasoning_review_request",
                    artifact_type="log",
                    path=request_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem_id},
                ),
                ArtifactRef(
                    name="human_reasoning_review_request_report",
                    artifact_type="report",
                    path=request_report_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem_id},
                ),
                ArtifactRef(
                    name="human_reasoning_review_template",
                    artifact_type="config",
                    path=template_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem_id},
                ),
            ]
        )

    payload = state.model_dump(mode="json")
    payload["artifacts"] = [
        artifact.model_dump(mode="json")
        for artifact in _dedupe_artifacts(artifacts)
    ]
    if request_human_review:
        payload["human_approval"] = HumanApproval(
            required=True,
            approved=None,
            reviewer=reviewer_hint,
            reason=(
                "Human review requested for agent reasoning postmortem before "
                "reusing this decision as memory or RAG context."
            ),
        ).model_dump(mode="json")
    return TFMStateModel.model_validate(payload)


def _append_reasoning_links_to_report(
    report_path: str | None,
    *,
    reasoning_report_path: str,
    review_report_path: str | None,
) -> None:
    if report_path is None:
        return
    path = Path(report_path)
    if not path.exists():
        return
    marker = "## Auditoria de razonamiento"
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    lines = [
        "",
        marker,
        "",
        f"- Post-mortem: `{reasoning_report_path}`",
        f"- Revision humana: `{review_report_path or 'no solicitada'}`",
        "",
    ]
    path.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")


def _dedupe_artifacts(artifacts: list[ArtifactRef]) -> list[ArtifactRef]:
    by_key: dict[tuple[str, str], ArtifactRef] = {}
    for artifact in artifacts:
        by_key[(artifact.name, artifact.path)] = artifact
    return list(by_key.values())


def _safe_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
