import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import ArtifactRef, EvaluationResult, MetricsReport
from codigo.app.services.run_persistence import save_run_snapshot
from codigo.app.services.run_registry import (
    compare_runs,
    get_run,
    get_run_audit_report,
    get_run_artifacts,
    get_run_evidence_pack,
    get_run_report_debate,
    list_runs,
)


class RunRegistryTests(unittest.TestCase):
    def test_list_runs_filters_by_dataset_stage_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-a", f1_score=0.80, approved=True), runs_dir)
            save_run_snapshot(_state("run-b", f1_score=0.70, approved=False), runs_dir)

            approved_runs = list_runs(runs_dir, approved=True)
            completed_runs = list_runs(runs_dir, current_stage="completed")
            cwru_runs = list_runs(runs_dir, dataset="cwru_bearing")

        self.assertEqual([run.run_id for run in approved_runs], ["run-a"])
        self.assertEqual({run.run_id for run in completed_runs}, {"run-a", "run-b"})
        self.assertEqual({run.run_id for run in cwru_runs}, {"run-a", "run-b"})

    def test_get_run_and_artifacts_load_snapshot_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-artifacts", f1_score=0.88), runs_dir)

            snapshot = get_run("run-artifacts", runs_dir)
            artifacts = get_run_artifacts("run-artifacts", runs_dir)
            evidence_pack = get_run_evidence_pack("run-artifacts", runs_dir)
            audit_report = get_run_audit_report("run-artifacts", runs_dir)

        self.assertEqual(snapshot.run_id, "run-artifacts")
        self.assertEqual(artifacts[0]["artifact_type"], "metrics")
        self.assertEqual(evidence_pack.run_id, "run-artifacts")
        self.assertIn("# Auditoria de ejecucion run-artifacts", audit_report)
        self.assertIn("## Resultado tecnico", audit_report)

    def test_get_run_report_debate_returns_markdown_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state_with_debate("run-debate", base), runs_dir)

            report_debate = get_run_report_debate("run-debate", runs_dir)

        self.assertIn("# Debate controlado del informe run-debate", report_debate)
        self.assertIn("Conversacion resumida", report_debate)

    def test_compare_runs_summarizes_best_and_worst_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(
                _state(
                    "run-baseline",
                    precision=0.90,
                    recall=0.92,
                    f1_score=0.91,
                    false_positive_rate=0.08,
                ),
                runs_dir,
            )
            save_run_snapshot(
                _state(
                    "run-candidate",
                    precision=0.95,
                    recall=0.94,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ),
                runs_dir,
            )

            comparison = compare_runs(["run-baseline", "run-candidate"], runs_dir)

        metrics = {metric.metric: metric for metric in comparison.metrics}
        self.assertEqual(comparison.run_ids, ["run-baseline", "run-candidate"])
        self.assertEqual(metrics["f1_score"].best_run_id, "run-candidate")
        self.assertEqual(metrics["precision"].best_value, 0.95)
        self.assertEqual(metrics["false_positive_rate"].best_run_id, "run-candidate")
        self.assertFalse(metrics["false_positive_rate"].higher_is_better)

    def test_compare_runs_adds_run_to_failure_degradation_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(
                _state(
                    "pca-run",
                    f1_score=0.60,
                    model_name="pca_reconstruction_error",
                    supervision_profile="run_to_failure_degradation",
                    label_source="temporal_proxy",
                    label_granularity="proxy_temporal",
                    metric_extra={
                        "metric_families": (
                            "binary_classification, run_to_failure_degradation"
                        ),
                        "degradation_available": True,
                        "degradation_n_runs": 1,
                        "degradation_detected_before_failure_rate": 1.0,
                        "degradation_confirmed_degradation_before_failure_rate": 1.0,
                        "degradation_mean_lead_time_to_failure": 300.0,
                        "degradation_mean_persistent_lead_time_to_failure": 260.0,
                        "degradation_mean_false_alarm_rate_nominal": 0.05,
                        "degradation_mean_score_trend_spearman": 0.82,
                        "degradation_missed_runs": 0,
                        "degradation_missed_confirmed_degradation_runs": 0,
                        "degradation_mean_isolated_alert_points": 0.0,
                        "degradation_mean_health_index_drop": 70.0,
                        "degradation_mean_health_monotonicity": 0.95,
                        "degradation_mean_health_robustness": 0.90,
                        "degradation_mean_health_nominal_volatility": 3.0,
                    },
                ),
                runs_dir,
            )
            save_run_snapshot(
                _state(
                    "svm-run",
                    f1_score=0.71,
                    model_name="one_class_svm",
                    supervision_profile="run_to_failure_degradation",
                    label_source="temporal_proxy",
                    label_granularity="proxy_temporal",
                    metric_extra={
                        "metric_families": (
                            "binary_classification, run_to_failure_degradation"
                        ),
                        "degradation_available": True,
                        "degradation_n_runs": 1,
                        "degradation_detected_before_failure_rate": 1.0,
                        "degradation_confirmed_degradation_before_failure_rate": 0.0,
                        "degradation_mean_lead_time_to_failure": 220.0,
                        "degradation_mean_persistent_lead_time_to_failure": None,
                        "degradation_mean_false_alarm_rate_nominal": 0.01,
                        "degradation_mean_score_trend_spearman": 0.76,
                        "degradation_missed_runs": 0,
                        "degradation_missed_confirmed_degradation_runs": 1,
                        "degradation_mean_isolated_alert_points": 2.0,
                        "degradation_mean_health_index_drop": 45.0,
                        "degradation_mean_health_monotonicity": 0.70,
                        "degradation_mean_health_robustness": 0.80,
                        "degradation_mean_health_nominal_volatility": 9.0,
                    },
                ),
                runs_dir,
            )

            comparison = compare_runs(["pca-run", "svm-run"], runs_dir)

        temporal = {metric.metric: metric for metric in comparison.degradation_metrics}
        rows = {row.run_id: row for row in comparison.rows}
        self.assertEqual(rows["pca-run"].model_name, "pca_reconstruction_error")
        self.assertEqual(rows["svm-run"].label_source, "temporal_proxy")
        self.assertIn("run_to_failure_degradation", rows["pca-run"].metric_families)
        self.assertEqual(
            temporal[
                "degradation_confirmed_degradation_before_failure_rate"
            ].best_run_id,
            "pca-run",
        )
        self.assertEqual(
            temporal["degradation_mean_persistent_lead_time_to_failure"].best_run_id,
            "pca-run",
        )
        self.assertEqual(
            temporal["degradation_mean_health_index_drop"].best_run_id,
            "pca-run",
        )
        self.assertEqual(
            temporal["degradation_mean_health_nominal_volatility"].best_run_id,
            "pca-run",
        )
        self.assertEqual(
            temporal["degradation_mean_lead_time_to_failure"].best_run_id,
            "pca-run",
        )
        self.assertEqual(
            temporal["degradation_mean_false_alarm_rate_nominal"].best_run_id,
            "svm-run",
        )
        self.assertEqual(
            temporal["degradation_mean_score_trend_spearman"].metric_family,
            "run_to_failure_degradation",
        )

    def test_compare_runs_requires_at_least_two_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                compare_runs(["run-a"], Path(tmp) / "runs")

    def test_compare_runs_reports_missing_run_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-present", f1_score=0.80), runs_dir)

            with self.assertRaises(FileNotFoundError):
                compare_runs(["run-present", "run-missing"], runs_dir)


def _state(
    run_id: str,
    *,
    precision: float = 0.93,
    recall: float = 0.95,
    f1_score: float,
    false_positive_rate: float = 0.04,
    approved: bool = True,
    model_name: str = "isolation_forest",
    supervision_profile: str = "binary_fault_classification",
    label_source: str = "official",
    label_granularity: str = "file",
    metric_extra: dict[str, object] | None = None,
):
    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = f"codigo/reports/cwru_bearing/{run_id}.md"
    state_dict["project_context"]["supervision_profile"] = supervision_profile
    state_dict["project_context"]["label_source"] = label_source
    state_dict["project_context"]["label_granularity"] = label_granularity
    state_dict["modeling_config"] = {
        "model_name": model_name,
        "random_state": 42,
        "hyperparameters": {},
    }
    state_dict["metrics"] = MetricsReport(
        metrics_path=f"codigo/reports/cwru_bearing/{run_id}/metrics.json",
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        false_positive_rate=false_positive_rate,
        extra=metric_extra or {},
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=approved,
        summary="Ejecucion aprobada." if approved else "Ejecucion rechazada.",
        next_action="continue" if approved else "retry_with_new_config",
        limitations=[],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path=f"codigo/reports/cwru_bearing/{run_id}/metrics.json",
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    return validate_state(state_dict)


def _state_with_debate(run_id: str, base: Path):
    state = _state(run_id, f1_score=0.88)
    debate_dir = base / "reports" / run_id / "evidence"
    debate_dir.mkdir(parents=True, exist_ok=True)
    debate_json = debate_dir / "report_debate.json"
    debate_md = debate_dir / "report_debate.md"
    debate_json.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "approved_without_revision",
                "rounds_used": 0,
                "max_rounds": 1,
                "final_summary": "Informe aceptado.",
                "turns": [
                    {
                        "round_index": 0,
                        "speaker_agent": "report_verifier",
                        "human_summary": "Informe verificado.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    debate_md.write_text(
        f"# Debate controlado del informe {run_id}\n\n## Conversacion resumida\n",
        encoding="utf-8",
    )
    state_dict = state.to_langgraph_state()
    state_dict["artifacts"] = [
        *state_dict["artifacts"],
        ArtifactRef(
            name="report_debate",
            artifact_type="config",
            path=str(debate_json),
            producer="report_writer",
        ).model_dump(mode="json"),
        ArtifactRef(
            name="report_debate_report",
            artifact_type="report",
            path=str(debate_md),
            producer="report_writer",
        ).model_dump(mode="json"),
    ]
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
