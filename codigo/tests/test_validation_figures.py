import contextlib
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from codigo.app.services.reasoning_memory_index import ReasoningMemoryIndexResult
from codigo.app.services.validation_figures import (
    AGENT_RELIABILITY_INTERPRETATION_LIMIT,
    MONITORING_REVIEW_RELIABILITY_INTERPRETATION_LIMIT,
    RunTrajectoryValidationProfile,
    classify_memory_corpus_records,
    classify_run_trajectory_figure_input,
    render_agent_reliability_figure,
    render_memory_corpus_governance_figure,
    render_monitoring_review_reliability_figure,
    render_run_trajectory_figure,
)
from codigo.scripts.generate_validation_figures import main as figures_cli_main


class ValidationFiguresTests(unittest.TestCase):
    def test_renders_vector_pdf_and_manifest_from_canonical_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_path = base / "reasoning_memory_index_report.json"
            source_bytes = _write_report(source_path, _complete_report_payload(base))

            artifacts = render_memory_corpus_governance_figure(
                source_report_path=source_path,
                output_dir=base / "figures",
            )

            pdf_bytes = Path(artifacts.pdf_path).read_bytes()
            manifest_payload = json.loads(
                Path(artifacts.manifest_path).read_text(encoding="utf-8")
            )

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(manifest_payload["output_format"], "pdf")
        self.assertEqual(
            manifest_payload["source_sha256"],
            hashlib.sha256(source_bytes).hexdigest(),
        )
        self.assertEqual(manifest_payload["source_record_count"], 3)
        self.assertEqual(manifest_payload["classified_record_count"], 3)
        self.assertEqual(
            {
                item["category_id"]: item["count"]
                for item in manifest_payload["categories"]
            },
            {
                "reviewed_reusable": 1,
                "quarantined_candidates": 1,
                "non_retrievable_audits": 1,
            },
        )
        self.assertEqual(
            manifest_payload["output_sha256"],
            hashlib.sha256(pdf_bytes).hexdigest(),
        )

    def test_fails_when_an_indexed_record_has_no_canonical_category(self):
        payload = _complete_report_payload(Path("/tmp/validation-figures"))
        payload["indexed_records"].append(
            _record(
                "unclassified-record",
                source_type="technical_documentation",
                source_path="unclassified.json",
                reusable=False,
            )
        )
        report = ReasoningMemoryIndexResult.model_validate(payload)

        with self.assertRaisesRegex(ValueError, "unclassified memory records"):
            classify_memory_corpus_records(report)

    def test_fails_when_quarantine_and_audit_sources_overlap(self):
        base = Path("/tmp/validation-figures-overlap")
        payload = _complete_report_payload(base)
        payload["quarantined_memory_candidates"].append(
            payload["indexed_memory_usage_audits"][0]
        )
        report = ReasoningMemoryIndexResult.model_validate(payload)

        with self.assertRaisesRegex(ValueError, "source lists overlap"):
            classify_memory_corpus_records(report)

    def test_cli_generates_the_same_artifact_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_path = base / "reasoning_memory_index_report.json"
            _write_report(source_path, _complete_report_payload(base))
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                figures_cli_main(
                    [
                        "--source-report",
                        str(source_path),
                        "--output-dir",
                        str(base / "cli-figures"),
                        "--figure-name",
                        "governance-test",
                    ]
                )

            output = json.loads(stdout.getvalue())

        self.assertEqual(output["source_record_count"], 3)
        self.assertEqual(output["categories"]["quarantined_candidates"], 1)
        self.assertTrue(output["pdf_path"].endswith("governance-test.pdf"))
        self.assertTrue(
            output["manifest_path"].endswith("governance-test.manifest.json")
        )

    def test_pdf_is_byte_reproducible_for_the_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_path = base / "reasoning_memory_index_report.json"
            _write_report(source_path, _complete_report_payload(base))

            first = render_memory_corpus_governance_figure(
                source_report_path=source_path,
                output_dir=base / "first",
            )
            second = render_memory_corpus_governance_figure(
                source_report_path=source_path,
                output_dir=base / "second",
            )

            first_pdf = Path(first.pdf_path).read_bytes()
            second_pdf = Path(second.pdf_path).read_bytes()

        self.assertEqual(first_pdf, second_pdf)
        self.assertEqual(
            first.manifest.output_sha256,
            second.manifest.output_sha256,
        )

    def test_renders_run_trajectory_from_two_classified_canonical_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, trajectory_bytes = _write_trajectory_fixture(base)
            metrics_path, metrics_bytes = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
            )

            artifacts = render_run_trajectory_figure(
                snapshot_trajectory_path=trajectory_path,
                metrics_path=metrics_path,
                output_dir=base / "figures",
                validation_profile=_small_run_profile(),
            )
            pdf_bytes = Path(artifacts.pdf_path).read_bytes()
            manifest = artifacts.manifest

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(
            [item.input_role for item in manifest.inputs],
            ["snapshot_trajectory", "evaluation_metrics"],
        )
        self.assertEqual(
            manifest.inputs[0].sha256,
            hashlib.sha256(trajectory_bytes).hexdigest(),
        )
        self.assertEqual(
            manifest.inputs[1].sha256,
            hashlib.sha256(metrics_bytes).hexdigest(),
        )
        self.assertEqual(manifest.validation_summary.snapshot_count, 6)
        self.assertEqual(
            manifest.validation_summary.partition_counts,
            {"baseline_train": 2, "calibration": 1, "monitoring": 3},
        )
        self.assertEqual(manifest.validation_summary.first_persistent_alert_index, 4)
        self.assertEqual(
            manifest.output_sha256,
            hashlib.sha256(pdf_bytes).hexdigest(),
        )

    def test_run_trajectory_input_classification_uses_internal_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, trajectory_bytes = _write_trajectory_fixture(base)
            _, metrics_bytes = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
            )

        self.assertEqual(
            classify_run_trajectory_figure_input(trajectory_bytes),
            "snapshot_trajectory",
        )
        self.assertEqual(
            classify_run_trajectory_figure_input(metrics_bytes),
            "evaluation_metrics",
        )
        with self.assertRaisesRegex(ValueError, "canonical run trajectory contract"):
            classify_run_trajectory_figure_input(b'{"unrelated": true}')

    def test_run_trajectory_pdf_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, _ = _write_trajectory_fixture(base)
            metrics_path, _ = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
            )

            first = render_run_trajectory_figure(
                snapshot_trajectory_path=trajectory_path,
                metrics_path=metrics_path,
                output_dir=base / "first",
                validation_profile=_small_run_profile(),
            )
            second = render_run_trajectory_figure(
                snapshot_trajectory_path=trajectory_path,
                metrics_path=metrics_path,
                output_dir=base / "second",
                validation_profile=_small_run_profile(),
            )
            first_pdf = Path(first.pdf_path).read_bytes()
            second_pdf = Path(second.pdf_path).read_bytes()

        self.assertEqual(first_pdf, second_pdf)
        self.assertEqual(
            first.manifest.output_sha256,
            second.manifest.output_sha256,
        )

    def test_run_trajectory_rejects_non_v2_monitoring_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, _ = _write_trajectory_fixture(
                base,
                monitoring_target="1.0",
            )
            metrics_path, _ = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
            )

            with self.assertRaisesRegex(
                ValueError,
                "v2 partition classification mismatch",
            ):
                render_run_trajectory_figure(
                    snapshot_trajectory_path=trajectory_path,
                    metrics_path=metrics_path,
                    output_dir=base / "figures",
                    validation_profile=_small_run_profile(),
                )

    def test_run_trajectory_rejects_available_binary_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, _ = _write_trajectory_fixture(base)
            metrics_path, _ = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
                binary_metrics_available=True,
            )

            with self.assertRaisesRegex(
                ValueError,
                "binary metrics must be explicitly unavailable",
            ):
                render_run_trajectory_figure(
                    snapshot_trajectory_path=trajectory_path,
                    metrics_path=metrics_path,
                    output_dir=base / "figures",
                    validation_profile=_small_run_profile(),
                )

    def test_cli_run_trajectory_mode_preserves_memory_mode_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            trajectory_path, _ = _write_trajectory_fixture(base)
            metrics_path, _ = _write_metrics_fixture(
                base,
                trajectory_path=trajectory_path,
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                figures_cli_main(
                    [
                        "--figure-type",
                        "run-trajectory",
                        "--snapshot-trajectory",
                        str(trajectory_path),
                        "--metrics-report",
                        str(metrics_path),
                        "--output-dir",
                        str(base / "cli-figures"),
                    ],
                    run_trajectory_profile=_small_run_profile(),
                )
            output = json.loads(stdout.getvalue())

        self.assertEqual(output["figure_type"], "run-trajectory")
        self.assertEqual(output["snapshot_count"], 6)
        self.assertEqual(output["partition_counts"]["monitoring"], 3)

    def test_renders_agent_reliability_pdf_png_and_hashed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_dir, summary_bytes, observations_bytes = (
                _write_agent_reliability_figure_fixture(base)
            )

            artifacts = render_agent_reliability_figure(
                plan_dir=plan_dir,
                output_dir=base / "figures",
                figure_name="agent-reliability-test",
            )
            pdf_bytes = Path(artifacts.pdf_path).read_bytes()
            png_bytes = Path(artifacts.png_path).read_bytes()
            manifest = artifacts.manifest

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(manifest.benchmark_scope, "closed_decision_only")
        self.assertEqual(
            manifest.interpretation_limit,
            AGENT_RELIABILITY_INTERPRETATION_LIMIT,
        )
        self.assertEqual(manifest.metrics.observation_count, 8)
        self.assertEqual(
            manifest.rendered_outcomes,
            [
                "first_pass",
                "llm_repaired",
                "fallback",
                "semantic_failure",
                "non_agentic",
                "error",
            ],
        )
        self.assertEqual(
            manifest.inputs[0].sha256,
            hashlib.sha256(summary_bytes).hexdigest(),
        )
        self.assertEqual(
            manifest.inputs[1].sha256,
            hashlib.sha256(observations_bytes).hexdigest(),
        )
        self.assertEqual(
            manifest.outputs[0].sha256,
            hashlib.sha256(pdf_bytes).hexdigest(),
        )
        self.assertEqual(
            manifest.outputs[1].sha256,
            hashlib.sha256(png_bytes).hexdigest(),
        )

    def test_agent_reliability_figure_rejects_summary_jsonl_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_dir, _, _ = _write_agent_reliability_figure_fixture(base)
            summary_path = plan_dir / "summary.json"
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            payload["summary"]["fallback_count"] = 0
            payload["summary"]["semantic_failure_count"] = 2
            summary_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "outcome count mismatch for fallback",
            ):
                render_agent_reliability_figure(
                    plan_dir=plan_dir,
                    output_dir=base / "figures",
                )

    def test_cli_agent_reliability_uses_parameterized_plan_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan_dir, _, _ = _write_agent_reliability_figure_fixture(base)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                figures_cli_main(
                    [
                        "--figure-type",
                        "agent-reliability",
                        "--plan-dir",
                        str(plan_dir),
                        "--output-dir",
                        str(base / "cli-figures"),
                    ]
                )
            output = json.loads(stdout.getvalue())

        self.assertEqual(output["figure_type"], "agent-reliability")
        self.assertEqual(output["benchmark_scope"], "closed_decision_only")
        self.assertEqual(output["observation_count"], 8)
        self.assertEqual(output["outcomes"]["fallback"], 1)
        self.assertTrue(output["pdf_path"].endswith(".pdf"))
        self.assertTrue(output["png_path"].endswith(".png"))

    def test_renders_published_monitoring_review_gate_without_hiding_blocker(self):
        source_root = Path(
            "codigo/reports/validation/monitoring_review_reliability"
        )
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = render_monitoring_review_reliability_figure(
                publication_root=source_root,
                output_dir=Path(tmp),
                figure_name="monitoring-review-gate-test",
            )
            pdf_bytes = Path(artifacts.pdf_path).read_bytes()
            png_bytes = Path(artifacts.png_path).read_bytes()
            manifest = artifacts.manifest

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(manifest.metrics.verdict, "blocked")
        self.assertEqual(
            manifest.metrics.blockers,
            (
                "resolved_child_run_count:11!=12",
                "fallback_count:2",
                "llm_origin_rate:0.976190<1.000000",
            ),
        )
        self.assertEqual(manifest.metrics.observation_count, 84)
        self.assertEqual(len(manifest.metrics.roles), 7)
        self.assertEqual(
            [item.first_pass_count for item in manifest.metrics.roles],
            [11, 11, 12, 12, 12, 12, 12],
        )
        self.assertEqual(
            [item.fallback_count for item in manifest.metrics.roles],
            [1, 1, 0, 0, 0, 0, 0],
        )
        self.assertEqual(len(manifest.metrics.matrix), 12)
        self.assertEqual(
            sum(item.claims_scope_failure_count for item in manifest.metrics.matrix),
            0,
        )
        self.assertEqual(
            [item.rate for item in manifest.metrics.coverages],
            [1.0, 1.0, 1.0],
        )
        self.assertEqual(
            manifest.interpretation_limit,
            MONITORING_REVIEW_RELIABILITY_INTERPRETATION_LIMIT,
        )
        self.assertEqual(
            manifest.outputs[0].sha256,
            hashlib.sha256(pdf_bytes).hexdigest(),
        )
        self.assertEqual(
            manifest.outputs[1].sha256,
            hashlib.sha256(png_bytes).hexdigest(),
        )

    def test_cli_monitoring_review_gate_uses_validated_current_pointer(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(stdout):
                figures_cli_main(
                    [
                        "--figure-type",
                        "monitoring-review-reliability",
                        "--publication-root",
                        "codigo/reports/validation/monitoring_review_reliability",
                        "--output-dir",
                        tmp,
                        "--figure-name",
                        "monitoring-review-gate-cli-test",
                    ]
                )
            output = json.loads(stdout.getvalue())

        self.assertEqual(output["verdict"], "blocked")
        self.assertEqual(output["observation_count"], 84)
        self.assertEqual(output["role_count"], 7)
        self.assertEqual(output["matrix_cell_count"], 12)
        self.assertEqual(output["coverages"]["trace_binding"], 1.0)


def _write_agent_reliability_figure_fixture(
    base: Path,
) -> tuple[Path, bytes, bytes]:
    plan_dir = base / "agent-reliability-fixture"
    plan_dir.mkdir(parents=True)
    specifications = [
        ("supervisor", "first_pass"),
        ("supervisor", "first_pass"),
        ("supervisor", "llm_repaired"),
        ("cleaner", "first_pass"),
        ("cleaner", "fallback"),
        ("report_verifier", "semantic_failure"),
        ("report_verifier", "non_agentic"),
        ("report_verifier", "error"),
    ]
    observations = [
        {
            "observation_id": f"fixture:{entrypoint}:{index}",
            "scenario_id": f"scenario-{index}",
            "entrypoint": entrypoint,
            "dataset": "cwru_bearing",
            "repetition": 1,
            "outcome": outcome,
            "elapsed_ms": float(index * 10),
            "trace_available": True,
        }
        for index, (entrypoint, outcome) in enumerate(specifications, start=1)
    ]
    observations_bytes = "".join(
        json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n"
        for item in observations
    ).encode("utf-8")
    (plan_dir / "observations.jsonl").write_bytes(observations_bytes)
    summary_payload = {
        "gate": {
            "verdict": "blocked",
            "blockers": ["fixture"],
            "detail": "Fixture con resultados excepcionales deliberados.",
        },
        "summary": {
            "observation_count": 8,
            "repetition_count": 1,
            "scenario_count": 8,
            "first_pass_count": 3,
            "repaired_count": 1,
            "fallback_count": 1,
            "non_agentic_count": 1,
            "semantic_failure_count": 1,
            "error_count": 1,
            "trace_coverage_rate": 1.0,
            "agentic_success_rate": 0.5,
            "first_pass_rate": 0.375,
            "flow_success_count": 0,
            "flow_success_rate": 0.0,
            "logical_call_count": 0,
            "physical_call_count": 0,
            "entrypoints": [
                {
                    "entrypoint": "cleaner",
                    "observation_count": 2,
                    "first_pass_count": 1,
                    "repaired_count": 0,
                    "fallback_count": 1,
                    "non_agentic_count": 0,
                    "semantic_failure_count": 0,
                    "error_count": 0,
                    "agentic_success_rate": 0.5,
                    "first_pass_rate": 0.5,
                },
                {
                    "entrypoint": "report_verifier",
                    "observation_count": 3,
                    "first_pass_count": 0,
                    "repaired_count": 0,
                    "fallback_count": 0,
                    "non_agentic_count": 1,
                    "semantic_failure_count": 1,
                    "error_count": 1,
                    "agentic_success_rate": 0.0,
                    "first_pass_rate": 0.0,
                },
                {
                    "entrypoint": "supervisor",
                    "observation_count": 3,
                    "first_pass_count": 2,
                    "repaired_count": 1,
                    "fallback_count": 0,
                    "non_agentic_count": 0,
                    "semantic_failure_count": 0,
                    "error_count": 0,
                    "agentic_success_rate": 1.0,
                    "first_pass_rate": 2 / 3,
                },
            ],
        },
    }
    summary_bytes = (
        json.dumps(summary_payload, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    (plan_dir / "summary.json").write_bytes(summary_bytes)
    return plan_dir, summary_bytes, observations_bytes


def _small_run_profile() -> RunTrajectoryValidationProfile:
    return RunTrajectoryValidationProfile(
        profile_id="small_run_trajectory_fixture",
        expected_run_id="fixture_run",
        expected_snapshot_count=6,
        expected_partition_counts={
            "baseline_train": 2,
            "calibration": 1,
            "monitoring": 3,
        },
        expected_detected_gaps=0,
        expected_cadence_intervals=5,
        expected_cadence_matches=5,
    )


def _write_trajectory_fixture(
    base: Path,
    *,
    monitoring_target: str = "",
) -> tuple[Path, bytes]:
    trajectory_path = base / "snapshot_trajectory.csv"
    partitions = [
        "baseline_train",
        "baseline_train",
        "calibration",
        "monitoring",
        "monitoring",
        "monitoring",
    ]
    scores = [0.50, 0.60, 0.70, 1.20, 2.00, 3.00]
    p90_scores = [0.80, 0.90, 1.00, 1.50, 2.50, 4.00]
    alerted_windows = [0, 0, 0, 1, 2, 2]
    health_values = [95.0, 94.0, 92.0, 75.0, 50.0, 20.0]
    fieldnames = [
        "run_id",
        "split",
        "label",
        "target",
        "label_source",
        "label_granularity",
        "relative_life",
        "temporal_partition",
        "threshold",
        "predicted_anomaly",
        "snapshot_id",
        "temporal_unit",
        "snapshot_aggregation_policy_id",
        "n_windows",
        "n_alerted_windows",
        "window_alert_fraction",
        "anomaly_score_median",
        "anomaly_score_p90",
        "temporal_gap_policy_id",
        "gap_detected",
        "cadence_matches_expected",
        "health_index_smoothed",
        "health_policy_id",
        "alert_policy_id",
        "health_indicator_policy_id",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for index, partition in enumerate(partitions):
        if partition == "baseline_train":
            split = "train"
            label = "normal"
            target = "0.0"
            label_source = "temporal_proxy"
            label_granularity = "proxy_temporal"
        else:
            split = "validation" if partition == "calibration" else "test"
            label = "unknown"
            target = monitoring_target if partition == "monitoring" else ""
            label_source = "none"
            label_granularity = "none"
        alert_fraction = alerted_windows[index] / 2
        writer.writerow(
            {
                "run_id": "fixture_run",
                "split": split,
                "label": label,
                "target": target,
                "label_source": label_source,
                "label_granularity": label_granularity,
                "relative_life": index / 5,
                "temporal_partition": partition,
                "threshold": 1.0,
                "predicted_anomaly": int(alert_fraction >= 0.5),
                "snapshot_id": f"snapshot-{index}",
                "temporal_unit": "snapshot",
                "snapshot_aggregation_policy_id": "snapshot_aggregation_v1",
                "n_windows": 2,
                "n_alerted_windows": alerted_windows[index],
                "window_alert_fraction": alert_fraction,
                "anomaly_score_median": scores[index],
                "anomaly_score_p90": p90_scores[index],
                "temporal_gap_policy_id": "temporal_gap_v1",
                "gap_detected": "False",
                "cadence_matches_expected": "" if index == 0 else "True",
                "health_index_smoothed": health_values[index],
                "health_policy_id": "temporal_health_policy_v1",
                "alert_policy_id": "alert_persistence_v1",
                "health_indicator_policy_id": "health_indicator_policy_v1",
            }
        )
    content = stream.getvalue().encode("utf-8")
    trajectory_path.write_bytes(content)
    return trajectory_path, content


def _write_metrics_fixture(
    base: Path,
    *,
    trajectory_path: Path,
    binary_metrics_available: bool = False,
) -> tuple[Path, bytes]:
    metrics_path = base / "metrics.json"
    split_metrics = {
        split_name: {"binary_metrics_available": False}
        for split_name in ("train", "validation", "test")
    }
    payload = {
        "metrics_path": metrics_path.as_posix(),
        "metric_families": ["run_to_failure_degradation"],
        "binary_metric_context": {
            "available": binary_metrics_available,
            "temporal_partitions": [
                "baseline_train",
                "calibration",
                "monitoring",
            ],
            "target_interpretation": "not_ground_truth",
        },
        "primary_metrics": {"binary_metrics_available": False},
        "metrics_by_split": split_metrics,
        "degradation_metrics": {
            "available": True,
            "metric_type": "run_to_failure_degradation",
            "temporal_unit": "snapshot",
            "binary_metrics_unit": "window",
            "snapshot_aggregation_policy_id": "snapshot_aggregation_v1",
            "snapshot_aggregation_policy": {
                "score_aggregation": "median",
                "score_p90_quantile": 0.9,
                "alert_fraction_threshold": 0.5,
                "alert_threshold_operator": "greater_than_or_equal",
            },
            "snapshot_alert_fraction_threshold": 0.5,
            "temporal_gap_policy_id": "temporal_gap_v1",
            "health_policy_id": "temporal_health_policy_v1",
            "alert_policy_id": "alert_persistence_v1",
            "health_indicator_policy_id": "health_indicator_policy_v1",
            "n_snapshots": 6,
            "n_windows": 12,
            "n_detected_gaps": 0,
            "n_cadence_intervals": 5,
            "n_cadence_matches": 5,
            "snapshot_trajectory_path": trajectory_path.as_posix(),
            "run_metrics": [
                {
                    "run_id": "fixture_run",
                    "temporal_unit": "snapshot",
                    "n_snapshots": 6,
                    "n_detected_gaps": 0,
                    "first_persistent_alert_snapshot_id": "snapshot-4",
                    "first_persistent_alert_relative_life": 0.8,
                    "false_alarm_reference": (
                        "causal_v2_pre_monitoring_partitions"
                    ),
                    "false_alarm_reference_snapshots": 3,
                }
            ],
        },
        "n_predictions": 12,
    }
    content = json.dumps(payload, indent=2).encode("utf-8")
    metrics_path.write_bytes(content)
    return metrics_path, content


def _complete_report_payload(base: Path) -> dict[str, Any]:
    candidate_path = (base / "candidate.json").as_posix()
    audit_path = (base / "audit.json").as_posix()
    return {
        "memory_dir": (base / "memory").as_posix(),
        "memory_backend": "local_json_vector_memory_store",
        "destructive_rebuild": False,
        "indexed_records": [
            _record(
                "reviewed-reusable",
                source_type="human_review",
                source_path=(base / "review.json").as_posix(),
                reusable=True,
            ),
            _record(
                "candidate-quarantined",
                source_type="decision_episode",
                source_path=candidate_path,
                reusable=False,
            ),
            _record(
                "audit-non-retrievable",
                source_type="memory_usage_audit",
                source_path=audit_path,
                reusable=False,
            ),
        ],
        "skipped_postmortems": [],
        "missing_reviews": [],
        "indexed_memory_usage_audits": [audit_path],
        "skipped_memory_usage_audits": [],
        "indexed_memory_candidates": [candidate_path],
        "skipped_memory_candidates": [],
        "quarantined_memory_candidates": [candidate_path],
        "governance_ledger_path": (base / "governance.json").as_posix(),
        "governance_overrides_loaded": 0,
        "applied_governance_actions": [],
        "active_tombstones": [],
        "index_report_path": None,
    }


def _record(
    memory_record_id: str,
    *,
    source_type: str,
    source_path: str,
    reusable: bool,
) -> dict[str, Any]:
    return {
        "memory_record_id": memory_record_id,
        "collection_name": "modeler_memory",
        "target_agent": "modeler",
        "source_type": source_type,
        "source_path": source_path,
        "run_id": "validation-run",
        "decision_id": f"validation-run:{memory_record_id}",
        "dataset": "nasa_ims_bearing",
        "data_provenance": "unknown",
        "source_agent_name": "modeler",
        "outcome": "partially_supported",
        "human_verdict": "partially_correct" if reusable else None,
        "memory_role": "boundary_case" if reusable else "evidence",
        "reusable_as_context": reusable,
        "exclude_from_context": False,
        "summary": f"Summary for {memory_record_id}.",
        "content": f"Content for {memory_record_id}.",
        "metrics": {},
        "tags": [],
    }


def _write_report(path: Path, payload: dict[str, Any]) -> bytes:
    content = json.dumps(payload, indent=2).encode("utf-8")
    path.write_bytes(content)
    return content


if __name__ == "__main__":
    unittest.main()
