"""Indexacion de post-mortems y revisiones humanas en memoria agentica."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentMemoryTarget,
    AgentReasoningPostmortem,
    HumanReasoningReview,
    MemoryCandidate,
    MemoryUsageAudit,
    ReasoningMemoryRecord,
)
from codigo.app.services.vector_memory import (
    EmbeddingProvider,
    LocalJsonVectorMemoryStore,
    get_default_embedding_provider,
    memory_record_from_candidate,
    memory_record_from_memory_usage_audit,
    memory_record_from_postmortem,
)

DEFAULT_MEMORY_DIR = Path("codigo/reports/reasoning_memory")


class ReasoningMemoryIndexResult(StrictBaseModel):
    """Resultado trazable de una indexacion de memoria agentica."""

    memory_dir: str
    indexed_records: list[ReasoningMemoryRecord]
    skipped_postmortems: list[str]
    missing_reviews: list[str]
    indexed_memory_usage_audits: list[str] = []
    skipped_memory_usage_audits: list[str] = []
    indexed_memory_candidates: list[str] = []
    skipped_memory_candidates: list[str] = []
    index_report_path: str | None = None


def index_reasoning_memory(
    *,
    reports_root: str | Path,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    include_unreviewed: bool = False,
    include_memory_candidates: bool = True,
    include_memory_usage_audits: bool = False,
    dataset: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    clear_existing: bool = False,
    write_report: bool = True,
) -> ReasoningMemoryIndexResult:
    """Indexa razonamientos revisados en el store vectorial local."""

    root = Path(reports_root)
    output_dir = Path(memory_dir)
    provider = embedding_provider or get_default_embedding_provider()
    records: list[ReasoningMemoryRecord] = []
    skipped: list[str] = []
    missing_reviews: list[str] = []
    indexed_audits: list[str] = []
    skipped_audits: list[str] = []
    indexed_candidates: list[str] = []
    skipped_candidates: list[str] = []

    for postmortem_path in sorted(root.rglob("reasoning_postmortem.json")):
        postmortem = _load_postmortem(postmortem_path)
        review_path = postmortem_path.with_name("human_reasoning_review.json")
        review = _load_review(review_path) if review_path.exists() else None
        if review is None and not include_unreviewed:
            missing_reviews.append(postmortem_path.as_posix())
            continue
        record = memory_record_from_postmortem(
            postmortem,
            review=review,
            dataset=dataset or _infer_dataset_from_path(postmortem_path),
            source_path=postmortem_path.as_posix(),
            source_hash=_sha256_file(postmortem_path),
        )
        if record.exclude_from_context:
            skipped.append(postmortem_path.as_posix())
            continue
        records.append(record)

    if include_memory_usage_audits:
        for audit_path in sorted(root.rglob("memory_usage_audit.json")):
            audit = _load_memory_usage_audit(audit_path)
            record = memory_record_from_memory_usage_audit(
                audit,
                target_agent=_infer_target_agent_from_audit(audit),
                dataset=dataset or _infer_dataset_from_path(audit_path),
                source_path=audit_path.as_posix(),
                source_hash=_sha256_file(audit_path),
            )
            if record.exclude_from_context:
                skipped_audits.append(audit_path.as_posix())
                continue
            indexed_audits.append(audit_path.as_posix())
            records.append(record)

    if include_memory_candidates:
        for candidate_path in sorted(root.rglob("memory_candidate.json")):
            candidate = _load_memory_candidate(candidate_path)
            record = memory_record_from_candidate(
                candidate,
                source_path=candidate_path.as_posix(),
                source_hash=_sha256_file(candidate_path),
            )
            if record.exclude_from_context or not record.reusable_as_context:
                skipped_candidates.append(candidate_path.as_posix())
                continue
            indexed_candidates.append(candidate_path.as_posix())
            records.append(record)

    store = LocalJsonVectorMemoryStore(output_dir, embedding_model=provider)
    indexed = store.rebuild(records, clear_existing=clear_existing)
    report_path = None
    result = ReasoningMemoryIndexResult(
        memory_dir=output_dir.as_posix(),
        indexed_records=indexed,
        skipped_postmortems=skipped,
        missing_reviews=missing_reviews,
        indexed_memory_usage_audits=indexed_audits,
        skipped_memory_usage_audits=skipped_audits,
        indexed_memory_candidates=indexed_candidates,
        skipped_memory_candidates=skipped_candidates,
        index_report_path=None,
    )
    if write_report:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path_obj = output_dir / "reasoning_memory_index_report.json"
        result = result.model_copy(
            update={"index_report_path": report_path_obj.as_posix()}
        )
        report_path_obj.write_text(
            json.dumps(result.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        report_path = report_path_obj.as_posix()
    return result.model_copy(update={"index_report_path": report_path})


def _load_postmortem(path: Path) -> AgentReasoningPostmortem:
    return AgentReasoningPostmortem.model_validate_json(path.read_text(encoding="utf-8"))


def _load_review(path: Path) -> HumanReasoningReview:
    return HumanReasoningReview.model_validate_json(path.read_text(encoding="utf-8"))


def _load_memory_usage_audit(path: Path) -> MemoryUsageAudit:
    return MemoryUsageAudit.model_validate_json(path.read_text(encoding="utf-8"))


def _load_memory_candidate(path: Path) -> MemoryCandidate:
    return MemoryCandidate.model_validate_json(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _infer_target_agent_from_audit(audit: MemoryUsageAudit) -> AgentMemoryTarget:
    decision_id = audit.decision_id.lower()
    for target_agent in [
        "cleaner",
        "structurer",
        "modeler",
        "evaluator",
        "report_writer",
        "researcher",
    ]:
        if (
            decision_id.startswith(f"{target_agent}-")
            or f"{target_agent}_" in decision_id
        ):
            return target_agent  # type: ignore[return-value]
    return "shared_methodology"


def _infer_dataset_from_path(path: Path) -> str | None:
    parts = path.parts
    if "nasa_ims_bearing" in parts:
        return "nasa_ims_bearing"
    if "cwru_bearing" in parts or "cwru_local" in parts:
        return "cwru_bearing"
    return None
