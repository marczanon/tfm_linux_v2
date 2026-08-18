import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    StateMessage,
)
from codigo.app.services.run_persistence import (
    extract_decisions,
    load_run_index,
    load_run_snapshot,
    save_run_snapshot,
)


class RunPersistenceTests(unittest.TestCase):
    def test_save_run_snapshot_writes_expected_files_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            state = _completed_state("run-persist-001")

            snapshot = save_run_snapshot(state, runs_dir)
            loaded = load_run_snapshot("run-persist-001", runs_dir)
            index = load_run_index(runs_dir)

            run_dir = runs_dir / "run-persist-001"
            state_payload = _read_json(run_dir / "state_final.json")
            decisions = _read_json(run_dir / "decisions.json")
            artifacts = _read_json(run_dir / "artifacts.json")
            metrics = _read_json(run_dir / "metrics.json")
            evaluation = _read_json(run_dir / "evaluation.json")
            evidence_pack = _read_json(run_dir / "evidence_pack.json")
            evidence_markdown = (run_dir / "evidence_pack.md").read_text(
                encoding="utf-8"
            )
            audit_report = (run_dir / "execution_audit.md").read_text(
                encoding="utf-8"
            )
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(snapshot.run_id, "run-persist-001")
        self.assertEqual(loaded.run_id, snapshot.run_id)
        self.assertEqual(state_payload["current_stage"], "completed")
        self.assertEqual([item["agent_name"] for item in decisions], ["supervisor", "cleaner"])
        self.assertEqual(artifacts[0]["artifact_type"], "metrics")
        self.assertEqual(metrics["f1_score"], 0.94)
        self.assertTrue(evaluation["approved"])
        self.assertTrue(snapshot.evidence_pack_path.endswith("evidence_pack.json"))
        self.assertTrue(
            snapshot.evidence_pack_markdown_path.endswith("evidence_pack.md")
        )
        self.assertTrue(snapshot.audit_report_path.endswith("execution_audit.md"))
        self.assertEqual(evidence_pack["schema_version"], "tfm.run_evidence_pack.v1")
        self.assertEqual(evidence_pack["run_id"], "run-persist-001")
        self.assertIn(
            evidence_pack["artifacts"][0]["checksum_status"],
            {"computed", "missing"},
        )
        if evidence_pack["artifacts"][0]["checksum_status"] == "computed":
            self.assertTrue(evidence_pack["artifacts"][0]["sha256"])
        self.assertEqual(
            [item["agent_name"] for item in evidence_pack["decisions"]],
            ["supervisor", "cleaner"],
        )
        self.assertIn("# Evidence pack run-persist-001", evidence_markdown)
        self.assertIn("# Auditoria de ejecucion run-persist-001", audit_report)
        self.assertIn("## Estado operativo y estado agentico", audit_report)
        self.assertIn("## Cronologia de agentes", audit_report)
        self.assertIn("## Verificacion del informe", audit_report)
        self.assertIn("## Debate del informe", audit_report)
        self.assertIn("## Lectura para evaluador humano", audit_report)
        self.assertIn("# Run run-persist-001", summary)
        self.assertIn("Evidence pack JSON", summary)
        self.assertIn("Auditoria de ejecucion", summary)
        self.assertEqual(len(index.runs), 1)
        self.assertEqual(index.runs[0].run_id, "run-persist-001")
        self.assertEqual(index.runs[0].f1_score, 0.94)

    def test_save_run_snapshot_replaces_existing_index_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            state = _completed_state("run-persist-dup")

            first = save_run_snapshot(state, runs_dir)
            second = save_run_snapshot(state, runs_dir)
            index = load_run_index(runs_dir)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(len(index.runs), 1)
        self.assertEqual(index.runs[0].run_id, "run-persist-dup")

    def test_save_run_snapshot_rejects_path_like_run_id(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-persistence-test",
            run_id="../bad",
        )
        state = validate_state(state_dict)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_run_snapshot(state, Path(tmp) / "runs")

    def test_extract_decisions_ignores_tool_messages(self):
        state = _completed_state("run-persist-decisions")

        decisions = extract_decisions(state)

        self.assertEqual(len(decisions), 2)
        self.assertEqual([item["role"] for item in decisions], ["supervisor", "agent"])

    def test_evidence_pack_preserves_generation_hypothesis_and_protocol_trace(self):
        state = _completed_state("run-persist-agent-audit")
        state_dict = state.to_langgraph_state()
        decision_id = "run-persist-agent-audit:modeler:001"
        state_dict["messages"].append(
            StateMessage(
                role="agent",
                name="modeler",
                content=json.dumps(
                    {
                        "agent_name": "modeler",
                        "decision_id": decision_id,
                        "rationale": "El protocolo conserva una propuesta auditable.",
                        "confidence": 1.0,
                        "hypothesis": {
                            "kind": "model_performance",
                            "statement": "PCA puede estabilizar la tendencia temporal.",
                            "scope": "Comparacion temporal controlada.",
                            "evidence_cutoff": "Train y validation antes de monitoring.",
                            "expected_observation": "Tendencia mas estable que el baseline.",
                            "falsification_criterion": "La tendencia empeora bajo el mismo protocolo.",
                            "evidence_refs": ["metric:trend_spearman"],
                            "risk_notes": ["Un caso no demuestra generalizacion."],
                            "assumptions": [],
                        },
                        "generation_trace": {
                            "origin": "protocol_restricted",
                            "attempt_id": f"{decision_id}:attempt:003",
                            "attempt_index": 3,
                            "validation_status": "validated",
                            "fallback_cause": None,
                            "fallback_from_attempt_id": None,
                        },
                        "decision_strategy": {
                            "hypothesis": "PCA puede estabilizar la tendencia temporal.",
                            "evidence_refs": ["metric:trend_spearman"],
                        },
                        "comparison_candidates": [
                            {"alternative_id": "isolation_forest_candidate"}
                        ],
                        "protocol_trace": {
                            "constraint_kind": "fixed_experiment_protocol",
                            "restriction_reason": "Comparacion controlada.",
                            "agent_proposal": {
                                "decision_strategy": {
                                    "hypothesis": "Comparar dos familias sin mirar monitoring.",
                                    "evidence_refs": ["policy:online_blind"],
                                },
                                "comparison_candidates": [
                                    {"alternative_id": "one_class_svm_candidate"}
                                ],
                                "generation_trace": {
                                    "origin": "guardrail_fallback",
                                    "attempt_id": f"{decision_id}:attempt:002",
                                    "attempt_index": 2,
                                    "validation_status": "fallback_applied",
                                    "fallback_cause": "ValueError: retrospective evidence",
                                    "fallback_from_attempt_id": f"{decision_id}:attempt:001",
                                },
                            },
                        },
                    }
                ),
            ).model_dump(mode="json")
        )

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(validate_state(state_dict), runs_dir)
            run_dir = runs_dir / "run-persist-agent-audit"
            evidence_pack = _read_json(run_dir / "evidence_pack.json")
            audit_report = (run_dir / "execution_audit.md").read_text(
                encoding="utf-8"
            )

        modeler = evidence_pack["decisions"][-1]
        self.assertEqual(modeler["generation_origin"], "protocol_restricted")
        self.assertEqual(modeler["generation_attempt_index"], 3)
        self.assertEqual(modeler["proposal_generation_origin"], "guardrail_fallback")
        self.assertIn("PCA puede estabilizar", modeler["hypothesis"])
        self.assertEqual(modeler["hypothesis_kind"], "model_performance")
        self.assertIn("tendencia empeora", modeler["hypothesis_falsification_criterion"])
        self.assertEqual(
            modeler["hypothesis_evidence_refs"],
            ["metric:trend_spearman"],
        )
        self.assertEqual(
            modeler["alternatives"],
            ["isolation_forest_candidate", "one_class_svm_candidate"],
        )
        self.assertEqual(
            modeler["evidence_refs"],
            ["metric:trend_spearman", "policy:online_blind"],
        )
        self.assertIn("protocolo fijo=`1`", audit_report)
        self.assertIn("Causa del fallback: ValueError", audit_report)

    def test_evidence_pack_normalizes_report_section_sources_and_refs(self):
        state = _completed_state("run-persist-report-evidence")
        state_dict = state.to_langgraph_state()
        state_dict["messages"].append(
            StateMessage(
                role="agent",
                name="report_writer",
                content=json.dumps(
                    {
                        "agent_name": "report_writer",
                        "decision_id": "run-persist-report-evidence:report_writer:001",
                        "rationale": "Redactar cada afirmacion desde evidencia trazable.",
                        "confidence": 0.9,
                        "output_path": "reports/final_report.md",
                        "sections": [
                            {
                                "title": "Resultados",
                                "source_paths": ["reports/metrics.json"],
                                "evidence_refs": [
                                    "artifact:metrics",
                                    "metric:f1_score",
                                ],
                            }
                        ],
                    }
                ),
            ).model_dump(mode="json")
        )

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(validate_state(state_dict), runs_dir)
            evidence_pack = _read_json(
                runs_dir
                / "run-persist-report-evidence"
                / "evidence_pack.json"
            )

        report_decision = evidence_pack["decisions"][-1]
        self.assertIn("reports/metrics.json", report_decision["source_paths"])
        self.assertEqual(
            report_decision["evidence_refs"],
            ["artifact:metrics", "metric:f1_score"],
        )


def _completed_state(run_id: str):
    state_dict = create_initial_cwru_state(
        thread_id="cwru-persistence-test",
        run_id=run_id,
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = "codigo/reports/cwru_bearing/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        precision=0.93,
        recall=0.95,
        f1_score=0.94,
        roc_auc=0.97,
        pr_auc=0.96,
        false_positive_rate=0.04,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada.",
        next_action="continue",
        limitations=["Validacion limitada a CWRU."],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path="codigo/reports/cwru_bearing/evaluation/metrics.json",
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    state_dict["messages"] = [
        StateMessage(
            role="supervisor",
            name="supervisor",
            content=json.dumps(
                {
                    "agent_name": "supervisor",
                    "decision_id": f"{run_id}:supervisor:001",
                    "next_stage": "completed",
                }
            ),
        ).model_dump(mode="json"),
        StateMessage(
            role="tool",
            name="evaluation",
            content="evaluation: ok",
        ).model_dump(mode="json"),
        StateMessage(
            role="agent",
            name="cleaner",
            content=json.dumps(
                {
                    "agent_name": "cleaner",
                    "decision_id": f"{run_id}:cleaner:001",
                }
            ),
        ).model_dump(mode="json"),
    ]
    return validate_state(state_dict)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
