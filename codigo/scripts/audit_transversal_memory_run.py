"""Audita una run persistida con memoria transversal structurer/evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.transversal_memory_audit import (
    TransversalMemoryAuditArtifacts,
    audit_transversal_memory_run,
)


def main() -> None:
    args = _parse_args()
    artifacts = audit_transversal_memory_run(
        run_id=args.run_id,
        runs_dir=args.runs_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(_summary(artifacts), indent=2, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def _summary(artifacts: TransversalMemoryAuditArtifacts) -> dict[str, Any]:
    audit = artifacts.audit
    return {
        "run_id": audit.run_id,
        "dataset": audit.dataset,
        "overall_outcome": audit.overall_outcome,
        "approved": audit.approved,
        "audit_path": artifacts.audit_path,
        "report_path": artifacts.report_path,
        "agent_audits": [
            {
                "agent_name": item.agent_name,
                "outcome": item.outcome,
                "context_reuse_allowed": item.context_reuse_allowed,
                "principal_evidence_requires_human_review": (
                    item.principal_evidence_requires_human_review
                ),
                "cited_memory_record_ids": item.cited_memory_record_ids,
            }
            for item in audit.agent_audits
        ],
    }


if __name__ == "__main__":
    main()
