import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codigo.app.services import dataset_adapters
from codigo.app.services.dataset_adapters import (
    NASA_IMS_OFFICIAL_EVIDENCE_FILENAME,
    NASA_IMS_OFFICIAL_SOURCE_URL,
    describe_dataset,
    get_dataset_adapter,
    prepare_nasa_ims_official_provenance,
)
from codigo.scripts.prepare_nasa_ims_official_provenance import main


class NASAIMSOfficialProvenanceTests(unittest.TestCase):
    def test_matching_fixture_is_official_and_propagates_scalar_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, subset, trusted, trusted_subset = _official_fixture(Path(tmp))
            with patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SOURCES,
                {NASA_IMS_OFFICIAL_SOURCE_URL: trusted},
                clear=True,
            ), patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SUBSET_INVENTORIES,
                {"set_2": trusted_subset},
                clear=True,
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "prepare",
                            "--archive",
                            archive.as_posix(),
                            "--subset",
                            subset.as_posix(),
                        ]
                    )
                descriptor = describe_dataset(
                    subset,
                    adapter_id="nasa_ims_bearing",
                )
                result = get_dataset_adapter("nasa_ims_bearing").build_manifest(
                    subset,
                    Path(tmp) / "interim",
                )

            summary = json.loads(stdout.getvalue())
            evidence_path = archive.parent / NASA_IMS_OFFICIAL_EVIDENCE_FILENAME
            row = _read_manifest_rows(Path(result.manifest_path))[0]
            row_metadata = json.loads(row["metadata_json"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "verified")
        self.assertEqual(summary["snapshot_count"], 3)
        self.assertEqual(descriptor.data_provenance, "official")
        self.assertEqual(
            descriptor.provenance_detection_method,
            "official_dataset_provenance",
        )
        self.assertEqual(descriptor.provenance_evidence_path, evidence_path.as_posix())
        self.assertEqual(descriptor.metadata["official_subset_id"], "set_2")
        self.assertEqual(descriptor.metadata["official_snapshot_count"], 3)
        self.assertEqual(
            descriptor.metadata["official_archive_sha256"],
            trusted["archive_sha256"],
        )
        self.assertEqual(row["data_provenance"], "official")
        self.assertTrue(row_metadata["official_nasa_measurements"])
        self.assertEqual(
            row_metadata["official_subset_tree_sha256"],
            descriptor.metadata["official_subset_tree_sha256"],
        )
        self.assertEqual(
            result.artifacts[0].metadata["official_snapshot_count"],
            3,
        )

    def test_changed_archive_hash_is_rejected_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, subset, trusted, trusted_subset = _official_fixture(Path(tmp))
            with patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SOURCES,
                {NASA_IMS_OFFICIAL_SOURCE_URL: trusted},
                clear=True,
            ), patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SUBSET_INVENTORIES,
                {"set_2": trusted_subset},
                clear=True,
            ):
                prepare_nasa_ims_official_provenance(archive, subset)
                archive.write_bytes(b"B" * archive.stat().st_size)

                with self.assertRaisesRegex(ValueError, "archive SHA-256 mismatch"):
                    describe_dataset(subset, adapter_id="nasa_ims_bearing")

    def test_changed_snapshot_is_rejected_by_tree_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, subset, trusted, trusted_subset = _official_fixture(Path(tmp))
            with patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SOURCES,
                {NASA_IMS_OFFICIAL_SOURCE_URL: trusted},
                clear=True,
            ), patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SUBSET_INVENTORIES,
                {"set_2": trusted_subset},
                clear=True,
            ):
                prepare_nasa_ims_official_provenance(archive, subset)
                snapshot = subset / "2004.02.12.10.42.39"
                content = snapshot.read_text(encoding="utf-8")
                snapshot.write_text(f"9{content[1:]}", encoding="utf-8")

                with self.assertRaisesRegex(
                    ValueError,
                    r"subset inventory mismatch.*tree_sha256",
                ):
                    describe_dataset(subset, adapter_id="nasa_ims_bearing")

    def test_non_official_source_url_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, subset, _, _ = _official_fixture(Path(tmp))

            with self.assertRaisesRegex(ValueError, "not an allowed NASA IMS"):
                prepare_nasa_ims_official_provenance(
                    archive,
                    subset,
                    source_url="https://example.invalid/bearings.zip",
                )

    def test_path_traversal_in_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, subset, trusted, trusted_subset = _official_fixture(Path(tmp))
            with patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SOURCES,
                {NASA_IMS_OFFICIAL_SOURCE_URL: trusted},
                clear=True,
            ), patch.dict(
                dataset_adapters.NASA_IMS_OFFICIAL_SUBSET_INVENTORIES,
                {"set_2": trusted_subset},
                clear=True,
            ):
                evidence_path = prepare_nasa_ims_official_provenance(archive, subset)
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                payload["subset"]["relative_path"] = "../escape/2nd_test"
                evidence_path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "invalid NASA IMS official provenance evidence",
                ):
                    describe_dataset(subset, adapter_id="nasa_ims_bearing")


def _official_fixture(
    root: Path,
) -> tuple[
    Path,
    Path,
    dict[str, str | int],
    dict[str, str | int],
]:
    archive = root / "4.+Bearings.zip"
    archive.write_bytes(b"fixture-official-archive-content")
    subset = root / "official" / "2nd_test"
    subset.mkdir(parents=True)
    for timestamp, offset in (
        ("2004.02.12.10.32.39", 0.0),
        ("2004.02.12.10.42.39", 0.1),
        ("2004.02.12.10.52.39", 0.2),
    ):
        (subset / timestamp).write_text(
            f"{0.1 + offset}\t0.2\t0.3\t0.4\n"
            f"{0.2 + offset}\t0.3\t0.4\t0.5\n",
            encoding="utf-8",
        )
    trusted_source = {
        "archive_file_name": archive.name,
        "archive_size_bytes": archive.stat().st_size,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    tree_digest = hashlib.sha256()
    total_bytes = 0
    snapshots = sorted(subset.iterdir(), key=lambda path: path.name)
    for snapshot in snapshots:
        size = snapshot.stat().st_size
        snapshot_sha256 = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        total_bytes += size
        tree_digest.update(
            f"{snapshot.name}\0{size}\0{snapshot_sha256}\n".encode("utf-8")
        )
    trusted_subset = {
        "snapshot_count": len(snapshots),
        "expected_n_channels": 4,
        "first_snapshot": snapshots[0].name,
        "last_snapshot": snapshots[-1].name,
        "total_bytes": total_bytes,
        "tree_sha256": tree_digest.hexdigest(),
    }
    return archive, subset, trusted_source, trusted_subset


def _read_manifest_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


if __name__ == "__main__":
    unittest.main()
