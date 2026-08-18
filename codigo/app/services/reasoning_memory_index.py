"""Indexacion de post-mortems y revisiones humanas en memoria agentica."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codigo.app.schemas.api_memory import MemoryGovernanceApplication
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentMemoryTarget,
    AgentReasoningPostmortem,
    HumanReasoningReview,
    MemoryUsageAudit,
    ReasoningMemoryRecord,
)
from codigo.app.services.memory_registry import (
    apply_memory_governance_override,
    load_memory_candidate_artifacts,
    load_memory_governance_ledger,
    memory_governance_ledger_path,
)
from codigo.app.services.vector_memory import (
    EmbeddingProvider,
    LocalJsonVectorMemoryStore,
    VectorMemoryStore,
    get_default_embedding_provider,
    memory_record_from_candidate,
    memory_record_from_memory_usage_audit,
    memory_record_from_postmortem,
)

DEFAULT_MEMORY_DIR = Path("codigo/reports/reasoning_memory")
DEFAULT_REPORTS_ROOT = Path("codigo/reports")


class ReasoningMemoryIndexResult(StrictBaseModel):
    """Resultado trazable de una indexacion de memoria agentica."""

    memory_dir: str
    memory_backend: str | None = None
    destructive_rebuild: bool = False
    indexed_records: list[ReasoningMemoryRecord]
    skipped_postmortems: list[str]
    missing_reviews: list[str]
    indexed_memory_usage_audits: list[str] = []
    skipped_memory_usage_audits: list[str] = []
    indexed_memory_candidates: list[str] = []
    skipped_memory_candidates: list[str] = []
    quarantined_memory_candidates: list[str] = []
    governance_ledger_path: str
    governance_overrides_loaded: int = 0
    applied_governance_actions: list[MemoryGovernanceApplication] = []
    active_tombstones: list[str] = []
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
    memory_store: VectorMemoryStore | None = None,
    clear_existing: bool = False,
    write_report: bool = True,
) -> ReasoningMemoryIndexResult:
    """Indexa razonamientos revisados en el backend vectorial seleccionado.

    ``memory_store`` permite reutilizar el backend ya configurado por la API o
    el runner. Si se omite, se conserva la compatibilidad historica con el
    indice JSON local y ``embedding_provider`` configura sus embeddings.
    """

    root = Path(reports_root)
    output_dir = Path(memory_dir)
    records: list[ReasoningMemoryRecord] = []
    skipped: list[str] = []
    missing_reviews: list[str] = []
    indexed_audits: list[str] = []
    skipped_audits: list[str] = []
    indexed_candidates: list[str] = []
    skipped_candidates: list[str] = []
    quarantined_candidates: list[str] = []
    governance_ledger = load_memory_governance_ledger(output_dir)
    applied_governance_actions: list[MemoryGovernanceApplication] = []
    active_tombstones = sorted(
        override.memory_record_id
        for override in governance_ledger.overrides
        if override.current_action == "delete"
    )

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
        record, governance_application = apply_memory_governance_override(
            record,
            governance_ledger,
        )
        if governance_application is not None:
            applied_governance_actions.append(governance_application)
        if record is None:
            skipped.append(postmortem_path.as_posix())
            continue
        if record.exclude_from_context:
            if (
                governance_application is not None
                and governance_application.effect == "excluded"
            ):
                records.append(record)
                continue
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
            record, governance_application = apply_memory_governance_override(
                record,
                governance_ledger,
            )
            if governance_application is not None:
                applied_governance_actions.append(governance_application)
            if record is None:
                skipped_audits.append(audit_path.as_posix())
                continue
            if record.exclude_from_context:
                if (
                    governance_application is not None
                    and governance_application.effect == "excluded"
                ):
                    indexed_audits.append(audit_path.as_posix())
                    records.append(record)
                    continue
                skipped_audits.append(audit_path.as_posix())
                continue
            if not record.reusable_as_context:
                # Se persiste para trazabilidad y para sobrescribir indices
                # historicos, pero el filtro de retrieval nunca la inyecta.
                indexed_audits.append(audit_path.as_posix())
                records.append(record)
                continue
            indexed_audits.append(audit_path.as_posix())
            records.append(record)

    if include_memory_candidates:
        for artifact in load_memory_candidate_artifacts(root):
            candidate_path = artifact.path
            candidate = artifact.candidate
            record = memory_record_from_candidate(
                candidate,
                source_path=candidate_path.as_posix(),
                source_hash=artifact.source_hash,
            )
            record, governance_application = apply_memory_governance_override(
                record,
                governance_ledger,
            )
            if governance_application is not None:
                applied_governance_actions.append(governance_application)
            if record is None:
                skipped_candidates.append(candidate_path.as_posix())
                continue
            if governance_application is None:
                # Compatibilidad segura con artefactos historicos: el campo
                # reusable_as_context del candidato nunca equivale por si solo
                # a una promocion humana ligada al contenido revisado.
                record = record.model_copy(
                    update={
                        "reusable_as_context": False,
                        "exclude_from_context": record.exclude_from_context,
                        "tags": sorted(
                            dict.fromkeys(
                                [*record.tags, "pending_manual_promotion"]
                            )
                        ),
                    }
                )
                quarantined_candidates.append(candidate_path.as_posix())
                indexed_candidates.append(candidate_path.as_posix())
                records.append(record)
                continue
            if record.exclude_from_context or not record.reusable_as_context:
                if (
                    governance_application is not None
                    and governance_application.effect
                    in {"excluded", "source_hash_mismatch"}
                ):
                    indexed_candidates.append(candidate_path.as_posix())
                    records.append(record)
                    continue
                skipped_candidates.append(candidate_path.as_posix())
                continue
            indexed_candidates.append(candidate_path.as_posix())
            records.append(record)

    store = memory_store
    if store is None:
        store = LocalJsonVectorMemoryStore(
            output_dir,
            embedding_model=embedding_provider or get_default_embedding_provider(),
        )
    indexed = _index_records(
        store,
        records,
        clear_existing=clear_existing,
        tombstoned_record_ids=active_tombstones,
    )
    report_path = None
    result = ReasoningMemoryIndexResult(
        memory_dir=output_dir.as_posix(),
        memory_backend=_memory_backend_name(store),
        destructive_rebuild=clear_existing,
        indexed_records=indexed,
        skipped_postmortems=skipped,
        missing_reviews=missing_reviews,
        indexed_memory_usage_audits=indexed_audits,
        skipped_memory_usage_audits=skipped_audits,
        indexed_memory_candidates=indexed_candidates,
        skipped_memory_candidates=skipped_candidates,
        quarantined_memory_candidates=quarantined_candidates,
        governance_ledger_path=memory_governance_ledger_path(output_dir).as_posix(),
        governance_overrides_loaded=len(governance_ledger.overrides),
        applied_governance_actions=applied_governance_actions,
        active_tombstones=active_tombstones,
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


def _index_records(
    store: VectorMemoryStore,
    records: list[ReasoningMemoryRecord],
    *,
    clear_existing: bool,
    tombstoned_record_ids: list[str],
) -> list[ReasoningMemoryRecord]:
    """Actualiza por ID salvo que se solicite borrar y reconstruir el indice."""

    if clear_existing:
        return store.rebuild(records, clear_existing=True)
    for memory_record_id in tombstoned_record_ids:
        try:
            store.delete(memory_record_id)
        except FileNotFoundError:
            pass
    return [store.upsert(record) for record in records]


def _memory_backend_name(store: VectorMemoryStore) -> str:
    backend_name = getattr(store, "backend_name", None)
    if isinstance(backend_name, str) and backend_name:
        return backend_name
    return type(store).__name__


def _load_postmortem(path: Path) -> AgentReasoningPostmortem:
    return AgentReasoningPostmortem.model_validate_json(path.read_text(encoding="utf-8"))


def _load_review(path: Path) -> HumanReasoningReview:
    return HumanReasoningReview.model_validate_json(path.read_text(encoding="utf-8"))


def _load_memory_usage_audit(path: Path) -> MemoryUsageAudit:
    return MemoryUsageAudit.model_validate_json(path.read_text(encoding="utf-8"))


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
