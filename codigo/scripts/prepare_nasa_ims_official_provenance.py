"""Prepara o verifica la evidencia de procedencia oficial de NASA IMS."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from codigo.app.services.dataset_adapters import (
    NASA_IMS_OFFICIAL_EVIDENCE_FILENAME,
    NASA_IMS_OFFICIAL_SOURCE_URL,
    prepare_nasa_ims_official_provenance,
    verify_nasa_ims_official_provenance,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Genera o verifica un sidecar reproducible para un subconjunto "
            "NASA IMS ya extraido. No descarga ni extrae datos."
        )
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    prepare = subparsers.add_parser(
        "prepare",
        help="crea el sidecar sin sobrescribir uno existente",
    )
    prepare.add_argument("--archive", type=Path, required=True)
    prepare.add_argument("--subset", type=Path, required=True)
    prepare.add_argument(
        "--source-url",
        default=NASA_IMS_OFFICIAL_SOURCE_URL,
    )
    prepare.add_argument(
        "--evidence-path",
        type=Path,
        default=None,
        help=(
            "ruta opcional; por defecto se crea "
            f"{NASA_IMS_OFFICIAL_EVIDENCE_FILENAME} junto al archivo fuente"
        ),
    )

    verify = subparsers.add_parser(
        "verify",
        help="verifica contrato, ZIP e inventario sin escribir",
    )
    verify.add_argument("--evidence-path", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "prepare":
        evidence_path = prepare_nasa_ims_official_provenance(
            args.archive,
            args.subset,
            source_url=args.source_url,
            evidence_path=args.evidence_path,
        )
    else:
        evidence_path = args.evidence_path

    evidence = verify_nasa_ims_official_provenance(evidence_path)
    raw_evidence = evidence_path.read_bytes()
    print(
        json.dumps(
            {
                "status": "verified",
                "data_provenance": evidence.data_provenance,
                "detection_method": "official_dataset_provenance",
                "evidence_path": evidence_path.as_posix(),
                "evidence_sha256": hashlib.sha256(raw_evidence).hexdigest(),
                "source_url": evidence.source.source_url,
                "archive_sha256": evidence.source.archive_sha256,
                "subset_id": evidence.subset.set_id,
                "snapshot_count": evidence.subset.snapshot_count,
                "first_snapshot": evidence.subset.first_snapshot,
                "last_snapshot": evidence.subset.last_snapshot,
                "tree_sha256": evidence.subset.tree_sha256,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
